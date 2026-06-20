# Audit: 2024-12-secondswap

## Vesting seller can claim tokens after listing/selling them
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting`, `claimable`
- Mechanism: `transferVesting` subtracts `_amount` from the grantor’s `totalAmount` but leaves `amountClaimed` unchanged and recalculates `releaseRate` as `totalAmount / numOfSteps`. After a seller has already claimed some steps, listing vesting through `Marketplace -> VestingManager -> transferVesting` can leave the seller with a release rate that is too high for their reduced remaining allocation. `claimable` only caps to remaining balance at the final step, so intermediate claims can withdraw tokens that were already transferred to the marketplace/buyer allocation.
- Impact: A seller can list or sell vested tokens, then continue claiming from the same underlying token pool, leaving buyers with undercollateralized vesting that may become impossible to fully claim.

## Existing buyers can accelerate newly purchased locked vesting
- Location: `contracts/SecondSwap_StepVesting.sol` : `_createVesting`
- Mechanism: When a beneficiary already has a vesting entry, `_createVesting` ignores the incoming `_stepsClaimed` value and merges the new amount into the beneficiary’s existing `stepsClaimed` and `releaseRate`. A buyer can keep a small old vesting position with low `stepsClaimed`, then buy a larger allocation whose seller/marketplace position had more steps already claimed. The new amount is treated as if it had been vesting from the buyer’s older schedule.
- Impact: Buyers can claim newly purchased locked tokens earlier than intended, bypassing the transferred allocation’s vesting state.

## Token issuer can confiscate user vesting without consent
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting`; `contracts/SecondSwap_VestingDeployer.sol` : `transferVesting`
- Mechanism: `transferVesting` allows `tokenIssuer`, `manager`, or `vestingDeployer` to move vesting from any `_grantor` to any `_beneficiary` without approval from the grantor. `SecondSwap_VestingDeployer.transferVesting` exposes the same arbitrary transfer power to the registered token owner.
- Impact: A token issuer or registered token owner can reassign or steal any holder’s unclaimed vesting allocation, including allocations bought through the marketplace.

## Private listings are not private
- Location: `contracts/SecondSwap_Whitelist.sol` : `whitelistAddress`
- Mechanism: Private marketplace listings rely on a deployed whitelist, but `whitelistAddress` lets any caller add themselves until `maxWhitelist` is reached. The lot owner does not approve addresses and there is no signature, allowlist root, or access control over entry.
- Impact: Any attacker can join a private sale whitelist, front-run intended buyers, fill all whitelist slots with Sybil addresses, and purchase listings meant to be restricted.

## Partial purchases can systematically underpay through rounding
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: Payment is calculated per purchase as `(_amount * discountedPrice) / 10 ** vestingTokenDecimals`, rounding down every fill. For partial listings, the contract does not track or charge cumulative rounding remainders. A buyer can split purchases into amounts just below the next payment-unit boundary and lose nearly one smallest payment unit on each fill.
- Impact: Buyers can acquire listed vesting for less than the seller’s stated price, reducing seller proceeds and marketplace fees. The issue is worse for low-decimal payment currencies or cheap execution environments.

## Invalid step duration can break or shorten vesting
- Location: `contracts/SecondSwap_VestingDeployer.sol` : `deployVesting`; `contracts/SecondSwap_StepVesting.sol` : `constructor`, `claimable`
- Mechanism: The deployer only checks `startTime < endTime` and `steps > 0`. `SecondSwap_StepVesting` computes `stepDuration = (_endTime - _startTime) / _numOfSteps` using floor division. If `steps > endTime - startTime`, `stepDuration` becomes zero and `claimable` reverts on division by zero. If the duration is not evenly divisible by steps, the vesting can fully mature before `endTime`.
- Impact: A malicious or careless issuer can deploy sellable vesting that buyers cannot claim, or a schedule that unlocks earlier than the advertised end time.

## Referral rewards are never paid
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: The function computes `referralFeeCost` when `_referral` is set, but never transfers anything to `_referral`. It then sends `buyerFeeTotal + sellerFeeTotal` to `feeCollector`, so all fees are collected by the protocol regardless of referral.
- Impact: Referrers receive no on-chain reward even though purchases emit a referral reward value, causing incorrect fee accounting and misleading settlement events.

## Mock USDT has unrestricted minting if used as a live payment token
- Location: `contracts/USDT.sol` : `mint`
- Mechanism: `TestToken1.mint` is public and has no access control.
- Impact: If this token is used as the marketplace payment currency or configured as `usdt`, any attacker can mint unlimited tokens and buy vesting listings or pay penalties with worthless self-minted balances.

