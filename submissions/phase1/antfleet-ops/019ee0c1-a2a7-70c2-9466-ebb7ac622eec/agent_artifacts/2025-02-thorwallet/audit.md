# Audit: 2025-02-thorwallet

## Uncapped merge credits can exceed TITN reserves
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`, `claimTitn`, `withdrawRemainingTitn`
- Mechanism: `onTokenTransfer` credits `quoteTitn(amount)` for every TGT transfer but never enforces a global cap against `TITN_ARB`, `TGT_TO_EXCHANGE`, the contract’s TITN balance, or already claimed/claimable TITN. Once `totalTitnClaimable` exceeds the actual TITN reserve, early claimers can drain the contract. After 360 days, `withdrawRemainingTitn` can also underflow at `remainingTitnAfter1Year - initialTotalClaimable` if outstanding claimable TITN is greater than the remaining TITN balance.
- Impact: An attacker with enough TGT can over-subscribe the merge, drain the TITN allocation before later users claim, and/or permanently DoS post-year remaining-TITN withdrawals.

## Owner can withdraw active user backing funds
- Location: `contracts/MergeTgt.sol` : `withdraw`
- Mechanism: `withdraw(IERC20 token, uint256 amount)` lets the owner transfer any token from the merge contract at any time, with no restriction to excess funds, no accounting against outstanding `claimableTitnPerUser`, and no time/lock condition.
- Impact: A malicious or compromised owner can remove TITN owed to users, making claims revert or underpaying the merge, and can also withdraw TGT deposited by users.

## Bridged-token dust can freeze arbitrary holders
- Location: `contracts/Titn.sol` : `_credit`, `_validateTransfer`
- Mechanism: `_credit` marks the recipient address as `isBridgedTokenHolder` whenever any bridged amount is credited. The restriction is address-wide, not balance-specific. While `isBridgedTokensTransferLocked` is true, a marked address cannot transfer any of its TITN except through the allowed exemptions.
- Impact: An attacker can bridge a dust amount of TITN to a victim address, marking it as a bridged holder and freezing the victim’s entire existing TITN balance. The same attack can freeze contracts holding TITN, including merge/escrow contracts, unless they are configured as `transferAllowedContract`.

## Bridged-token lock can be bypassed after laundering to unmarked addresses
- Location: `contracts/Titn.sol` : `transfer`, `transferFrom`, `_validateTransfer`, `_credit`
- Mechanism: Bridged status is only set in `_credit`; it is not propagated when a flagged holder transfers tokens. If transfers are unlocked, a bridged holder can move tokens to a fresh unmarked address. If the owner later re-locks transfers, that new address is not restricted on non-Arbitrum chains because `isBridgedTokenHolder[newAddress]` remains false. The same laundering issue can occur through an exempt `transferAllowedContract` that forwards tokens onward.
- Impact: Bridged tokens can become indistinguishable from unrestricted tokens, allowing attackers to bypass future bridged-token transfer locks and circulate tokens that the lock was intended to restrict.

