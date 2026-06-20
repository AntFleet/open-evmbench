# Audit: 2024-01-renft

## Rental order hash does not bind the rental safe
- Location: `smart-contracts/src/packages/Signer.sol` : `_deriveRentalOrderHash`
- Mechanism: The rental order hash omits `order.rentalWallet` even though `Stop.stopRent()` later trusts the caller-supplied `rentalWallet` for reclaiming assets and for decrementing `rentedAssets`. The stored `orders[hash]` entry therefore authenticates the order terms but not the safe that actually holds the rental.
- Impact: A caller can stop an active order using a different protocol safe as `rentalWallet`. For ERC1155 rentals with the same token/id active in multiple safes, this lets an attacker reclaim assets from a victim safe to the attacker-controlled lender and decrement the victim safe’s rental accounting.

## Safe module disabling checks the wrong argument
- Location: `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- Mechanism: For `disableModule(address prevModule,address module)`, the guard loads `gnosis_safe_disable_module_offset = 0x24`, which is the `prevModule` argument, not the `module` being disabled. The whitelist check is therefore applied to the previous linked-list module instead of the target module.
- Impact: If a whitelisted extension is enabled before the Stop policy in the Safe module list, a renter can call `disableModule(whitelistedExtension, stopPolicy)` and pass the guard. Disabling the Stop policy prevents `Stop._reclaimRentedItems()` from executing from that safe, locking rented assets and blocking normal settlement.

## Token movement guard is bypassable by unlisted token methods
- Location: `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- Mechanism: The guard relies on a hard-coded selector blacklist for standard ERC721/ERC1155 transfer and approval methods. Any rented token contract that exposes an alternate movement, approval, burn, unwrap, permit, or custom operator path with a different selector falls through the final `else` branch without checking whether the token is rented.
- Impact: A renter can move, approve, or destroy a rented asset through an unlisted token-specific method while the protocol still believes the asset is safely held by the rental safe. The lender can lose the asset or be unable to stop the rental.

## Hooked targets skip the base rental-asset guard
- Location: `smart-contracts/src/policies/Guard.sol` : `checkTransaction`
- Mechanism: When `STORE.contractToHook(to)` returns an active `onTransaction` hook, the guard forwards to the hook and does not also run `_checkTransaction`. This makes the hook a replacement for the core transfer/approval checks rather than an additional restriction.
- Impact: If a hook is configured for a token or multi-function target and the hook does not block standard transfer/approval selectors, the renter can transfer or approve rented assets through that hooked target even though the base guard would have rejected the call.

## Escrow accounting trusts nominal ERC20 amounts instead of received balances
- Location: `smart-contracts/src/policies/Create.sol` : `_rentFromZone`; `smart-contracts/src/modules/PaymentEscrow.sol` : `increaseDeposit`
- Mechanism: After Seaport fulfillment, the protocol increments `PaymentEscrow.balanceOf[token]` by the order item amount without checking how many tokens the escrow actually received. Fee-on-transfer, rebasing, or otherwise non-standard ERC20s can leave the escrow underfunded while internal accounting records the full nominal amount.
- Impact: Settlement can revert when `settlePayment()` tries to transfer more tokens than the escrow actually holds. This can prevent rentals from being stopped and lock rented assets/payments until an external recovery path exists.

## Reward accrual is shared across unrelated rentals of the same asset id
- Location: `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` : `onStart` / `onStop`; `smart-contracts/src/examples/revenue-share/ERC1155RewardHook.sol` : `onStart` / `onStop`
- Mechanism: `rentInfo` is keyed only by `keccak256(abi.encode(safe, token, identifier))`, while rewards are credited using the `RevenueShare` data from the current start/stop call. Multiple concurrent rentals of the same token id in the same safe but from different lenders or with different shares are aggregated into one `amount` and one `lastRewardBlock`.
- Impact: A later rental can cause rewards accrued by earlier rentals to be credited to the wrong lender/share configuration. Attackers can misallocate or steal rewards by starting/stopping overlapping rentals of the same ERC1155/asset id.

## ERC20 reward claims zero accounting before confirming transfer success
- Location: `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` : `claimRewards`
- Mechanism: `claimRewards()` sets `accruedRewards[rewardedAddress] = 0` and then calls `rewardToken.transfer(msg.sender, withdrawAmount)` without checking the returned boolean. ERC20 tokens that return `false` instead of reverting are treated as successful.
- Impact: A claimant’s accrued rewards can be erased without any tokens being transferred, permanently losing the recorded claim amount for false-returning ERC20 reward tokens.

