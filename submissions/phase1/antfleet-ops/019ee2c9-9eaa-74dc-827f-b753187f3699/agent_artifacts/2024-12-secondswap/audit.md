# Audit: 2024-12-secondswap

## Seller can overclaim vesting after listing or transferring it away
- Location: `audit_sources/2024-12-secondswap/contracts/SecondSwap_StepVesting.sol` : `transferVesting`
- Mechanism: `transferVesting` reduces `grantorVesting.totalAmount` but leaves `amountClaimed` unchanged, then recomputes `grantorVesting.releaseRate` as `grantorVesting.totalAmount / numOfSteps`. That ignores both `stepsClaimed` and already-claimed tokens. After a user has claimed some steps, then lists or transfers part of the remaining vesting, their per-step release rate becomes too high. `claimable()` uses that inflated `releaseRate` for non-final steps without capping against `totalAmount - amountClaimed`, so the grantor can keep claiming tokens that were already sold or transferred away.
- Impact: A seller can sell vesting through the marketplace and still extract extra underlying tokens afterward, draining tokens that should back buyers or other beneficiaries.

## Marketplace escrow pools incompatible vesting schedules and gives buyers the wrong claim state
- Location: `audit_sources/2024-12-secondswap/contracts/SecondSwap_StepVesting.sol` : `_createVesting`; `audit_sources/2024-12-secondswap/contracts/SecondSwap_VestingManager.sol` : `listVesting`, `completePurchase`
- Mechanism: All listings for a vesting plan are escrowed into the single `SecondSwap_VestingManager` address, but `SecondSwap_StepVesting` stores only one `Vesting` struct per beneficiary address. When escrow already has a balance, `_createVesting` ignores the incoming `_stepsClaimed` and merges the new tranche into the manager’s existing `stepsClaimed`/`releaseRate`. Later, purchases transfer vesting out of that pooled manager position, so the buyer inherits the manager’s aggregate step state instead of the original seller’s step state.
- Impact: A buyer can receive vesting with fewer claimed steps than the seller actually had, making future-locked tokens claimable too early. Conversely, pooled state can also corrupt later buyers’ schedules and deny correct claims.

## “Private” listings are not private
- Location: `audit_sources/2024-12-secondswap/contracts/SecondSwap_Whitelist.sol` : `whitelistAddress`
- Mechanism: Private sales rely on `_validatePurchase` checking `IWhitelist(listing.whitelist).validateAddress(msg.sender)`, but the whitelist contract lets any caller add itself by calling `whitelistAddress()` as long as capacity remains. There is no seller approval, signature check, preset allowlist, or removal flow; the seller only controls the max slot count.
- Impact: Any attacker can self-whitelist and buy from a supposedly private listing. Attackers can also sybil-fill the whitelist first and block the intended counterparties entirely.

## Token issuer can confiscate any beneficiary’s vesting without consent
- Location: `audit_sources/2024-12-secondswap/contracts/SecondSwap_StepVesting.sol` : `transferVesting`; `audit_sources/2024-12-secondswap/contracts/SecondSwap_VestingDeployer.sol` : `transferVesting`
- Mechanism: `SecondSwap_StepVesting.transferVesting` authorizes `tokenIssuer`, `manager`, or `vestingDeployer` to move vesting from any `_grantor` to any `_beneficiary`. The deployer wrapper also exposes this power to the configured token owner. There is no user approval, no marketplace payment requirement, and no restriction that the grantor initiated the transfer.
- Impact: A malicious issuer or token owner can arbitrarily seize users’ unclaimed vesting and redirect it to itself or an accomplice.

## Vesting parameters can be set so tokens unlock early or never unlock at all
- Location: `audit_sources/2024-12-secondswap/contracts/SecondSwap_VestingDeployer.sol` : `deployVesting`; `audit_sources/2024-12-secondswap/contracts/SecondSwap_StepVesting.sol` : `constructor`, `claimable`
- Mechanism: `deployVesting` checks only `startTime < endTime` and `steps > 0`. The vesting contract then computes `stepDuration = (endTime - startTime) / numOfSteps` using integer division. If the duration is not evenly divisible by `numOfSteps`, the final step becomes reachable before `endTime`; if `numOfSteps` exceeds the duration in seconds, `stepDuration` becomes zero and `claimable()` divides by zero forever.
- Impact: A malicious or careless vesting creator can deploy schedules that fully vest earlier than advertised, or permanently brick all claims and lock deposited tokens.

