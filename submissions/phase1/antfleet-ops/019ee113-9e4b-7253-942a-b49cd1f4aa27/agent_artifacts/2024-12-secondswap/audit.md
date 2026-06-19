# Audit: 2024-12-secondswap

## Incorrect Release Rate Calculation in `transferVesting` (Critical Accounting Error)
- Location: `SecondSwap_StepVesting.sol` : `transferVesting`
- Mechanism: After transferring part of the grantor's vesting to a beneficiary, the grantor's `releaseRate` is recomputed as `grantorVesting.totalAmount / numOfSteps`, ignoring both the tokens already claimed (`amountClaimed`) and the steps already elapsed (`stepsClaimed`). The correct formula should be `(totalAmount - amountClaimed) / (numOfSteps - stepsClaimed)`. The beneficiary's `_createVesting` call uses the correct formula, creating a mismatch that inflates the grantor's per-step claim.
- Impact: The grantor can claim more tokens than they are entitled to. For example, with `totalAmount=1000`, `numOfSteps=10`, `stepsClaimed=3`, `amountClaimed=300`, after transferring 200 tokens the grantor's `releaseRate` becomes `80` (800/10) instead of the correct ~71 (500/7). Over the remaining 7 steps, the grantor can extract ~60 extra tokens, while the beneficiary receives less than their fair share (28 per step × 7 = 196 instead of 200). If the contract holds the exact total supply, the beneficiary may be unable to claim all their tokens once the grantor drains the excess, leading to permanent loss of user funds.

## Referral Fee Not Paid to Referrer
- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: The function calculates `referralFeeCost` as the portion of `buyerFeeTotal` that should be paid to the referrer (based on `referralFee` setting), and emits it in the `Purchased` event. However, no `safeTransfer` is ever made to the `_referral` address. The full `buyerFeeTotal + sellerFeeTotal` is sent to the `feeCollector` via `feeCollectorTotal = (buyerFeeTotal + sellerFeeTotal)`. There is no other function that allows the referrer to claim these funds.
- Impact: Referrers are defrauded of their promised rewards. The event falsely advertises a `referralReward` was paid, but the tokens are retained by (or transferred to) the fee collector. Users who bring referrals to the platform receive nothing, and the protocol gains a hidden windfall at the referrer's expense.

## Reentrancy in `spotPurchase` via ERC777-style Token Callbacks
- Location: `SecondSwap_Marketplace.sol` : `spotPurchase`
- Mechanism: The function performs external calls (`safeTransferFrom`, `safeTransfer`) inside `_handleTransfers` before updating the listing state (`listing.balance -= _amount; listing.status = ...`). If the currency token implements callback hooks (e.g., ERC777 `tokensToSend`/`tokensReceived`, or any token with transfer hooks), an attacker contract can re-enter `spotPurchase` during the transfer. Since the listing's `balance` and `status` have not yet been decremented, the re-entered call passes `_validatePurchase` and allows purchasing the same listing repeatedly.
- Impact: A malicious or hook-enabled currency token (if ever whitelisted via `addCoin`, or if a legitimate token like an ERC777 variant is added) can be used to drain a listing's entire balance in a single transaction, effectively buying tokens without paying or over-paying the seller. The marketplace's accounting would also be corrupted in `VestingManager.completePurchase`.

## Public Mint Function in TestToken1 (USDT)
- Location: `TestToken1.sol` (referred to as USDT) : `mint`
- Mechanism: The `mint` function has no access control (`public` with no modifier), allowing any address to mint arbitrary amounts of the token. If this contract is used as the `usdt` payment token (referenced in `MarketplaceSetting` and used for penalty fees in `unlistVesting`), any user can mint unlimited USDT.
- Impact: An attacker can mint USDT to pay for penalty fees in early unlistings, or if this token is ever used as a listing currency, mint currency to purchase vesting tokens for free. Combined with the reentrancy above, this could allow complete drainage of the marketplace.

## Division by Zero in `_createVesting` for Transferred Vestings
- Location: `SecondSwap_StepVesting.sol` : `_createVesting`
- Mechanism: When creating a new vesting for a beneficiary via `transferVesting` (with `_isInternal = true`), the code calculates `releaseRate: _totalAmount / (numOfSteps - _stepsClaimed)`. If `grantorVesting.stepsClaimed >= numOfSteps` (i.e., the grantor has already claimed all steps), this division reverts. The existing-beneficiary branch correctly guards against this with an `if` check, but the new-beneficiary branch does not.
- Impact: A DoS condition in `transferVesting` when the grantor has reached the end of their schedule but still holds unclaimed tokens (edge case where `totalAmount - amountClaimed > 0` but `stepsClaimed == numOfSteps`). The function reverts, blocking legitimate transfers.

## Missing Zero-Address and Same-Address Checks in Admin Functions
- Location: `SecondSwap_VestingManager.sol` : `setAdmin`, `setMarketplace`, `setVestingDeployer`; `SecondSwap_VestingDeployer.sol` : `setAdmin`, `setManager`
- Mechanism: Several privileged setters lack `require(_addr != address(0))` or `require(_addr != currentValue)` guards. For example, `VestingManager.setMarketplace` and `setAdmin` allow the admin to set these to `address(0)`, permanently locking the contract (no one can call `onlyAdmin` or `onlyMarketplace` functions). `VestingManager.setVestingDeployer` does check for the same address but not for zero.
- Impact: An admin mistake (or a compromised admin key) can brick the contract, freezing all vesting operations. There is no recovery path because the admin is also locked out.

## Step Duration Precision Loss
- Location: `SecondSwap_StepVesting.sol` : `constructor`
- Mechanism: `stepDuration = (_endTime - _startTime) / _numOfSteps;` performs integer division. If the duration is not evenly divisible by the number of steps, the sum of all step durations will be less than `_endTime - _startTime`, leaving a "dead zone" at the end of the schedule where no new steps unlock. Conversely, if the issuer chooses a duration that is evenly divisible, this is not an issue, but the contract silently truncates otherwise.
- Impact: Users may find that the final step unlocks slightly earlier than `endTime` (or that the last few seconds of the schedule yield no additional tokens). This causes minor value loss for beneficiaries and complicates off-chain accounting.
