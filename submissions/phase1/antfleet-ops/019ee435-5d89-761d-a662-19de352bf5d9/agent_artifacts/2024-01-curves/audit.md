# Audit: 2024-01-curves

## Broken access control modifiers
- Location: `contracts/Security.sol` : `onlyOwner`, `onlyManager`
- Mechanism: Both modifiers perform a boolean comparison but never require or revert on the result: `msg.sender == owner;` and `managers[msg.sender] == true;`. These statements are no-ops, so every `onlyOwner` and `onlyManager` protected function in `Curves` and `FeeSplitter` is callable by anyone.
- Impact: Any attacker can change protocol fee settings, set themselves as manager/owner, redirect protocol fees, replace the ERC20 factory, replace the fee redistributor, and call privileged FeeSplitter functions. This enables fee theft, market-wide DoS through malicious fee settings/contracts, and loss of administrative control.

## FeeSplitter owner source can be replaced by anyone
- Location: `contracts/FeeSplitter.sol` : `setCurves`
- Mechanism: `setCurves(Curves curves_)` is public and has no access control. FeeSplitter trusts `curves` for both holder balances and total supply when calculating and paying holder fees. An attacker can point `curves` to a malicious contract that reports attacker-owned balances and arbitrary supply.
- Impact: When holder fees are added, the attacker can make FeeSplitter account those fees as belonging to them and then claim them via `claimFees`/`batchClaiming`. They can also make holder-fee distribution revert by returning zero supply, blocking Curves trades that attempt to distribute holder fees.

## Holder-fee accounting can be stolen through transfers and wrapper deposits
- Location: `contracts/Curves.sol` : `_transfer`, `withdraw`, `deposit`; `contracts/FeeSplitter.sol` : `getClaimableFees`, `onBalanceChange`
- Mechanism: FeeSplitter calculates claimable fees from the current Curves balance multiplied by the difference between `cumulativeFeePerToken` and `userFeeOffset`. However, Curves balance changes in `_transfer`, `withdraw`, and `deposit` do not update FeeSplitter offsets for the sender or receiver. A fresh address with offset `0` can receive tokens after fees have accumulated and claim historical fees it did not earn. Similarly, users can withdraw to ERC20, sit out fee distribution, deposit back later, and claim fees accrued while their tokens were excluded from FeeSplitter supply.
- Impact: Attackers can drain holder-fee ETH that belongs to legitimate holders. If the original holder already claimed before transferring, the recipient can attempt to double-claim historical fees against FeeSplitter’s shared ETH balance, stealing later deposits or other holders’ unpaid fees.

## Trading wipes accrued holder fees for the trader
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange`
- Mechanism: `onBalanceChange` sets `userFeeOffset[account] = cumulativeFeePerToken` without first crediting already accrued fees into `unclaimedFees`. Curves calls this during buys and sells after mutating the trader’s balance. Any accrued holder fees for that trader are therefore discarded whenever they trade.
- Impact: Holders who buy or sell lose previously earned holder fees. The lost accounting value remains in FeeSplitter and can be captured by other users through the stale-offset transfer/deposit issue above.

## Sell-side fees are deducted but not fully paid out
- Location: `contracts/Curves.sol` : `_transferFees`
- Mechanism: On sells, `firstDestination` is `msg.sender`, and the amount sent is `price - protocolFee - subjectFee - referralFee - holderFee`. The function then pays `subjectFee`, optionally pays `referralFee`, and distributes `holderFee`, but it never sends `protocolFee` to `protocolFeeDestination` on sells. If no referral destination is set, `referralFee` is also deducted from the seller but not paid anywhere.
- Impact: Sellers are underpaid by at least the protocol fee on every sell, and by the referral fee too when no referral destination exists. Those deducted funds become trapped surplus in the Curves contract rather than reaching the intended recipients.

## Reverting fee recipients can freeze trading
- Location: `contracts/Curves.sol` : `_transferFees`
- Mechanism: Every buy and sell performs synchronous ETH pushes to `protocolFeeDestination`, `curvesTokenSubject`, and optionally `referralFeeDestination`, reverting the whole trade if any call fails. The subject can be an arbitrary contract, and the subject can set an arbitrary referral destination. Even zero-value calls can execute and revert.
- Impact: A malicious or incompatible token subject/referral contract can permanently block buys and sells for that curve, trapping holders who need `sellCurvesToken` to exit. Because access control is broken, an external attacker can also set global fee-related destinations/contracts to cause broader DoS.

