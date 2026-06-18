# Audit: 2025-01-liquid-ron

## Consensus findings

## Accrued operator fee is never subtracted from `totalAssets()` — share price is inflated by the fee liability
*(consensus)*
- Location: `src/LiquidRon.sol` : `totalAssets()` (the `super.totalAssets() + getTotalStaked() + getTotalRewards()` override), in conjunction with `harvest()` / `harvestAndDelegateRewards()` (`operatorFeeAmount += (harvestedAmount * operatorFee) / BIPS`) and `fetchOperatorFee()`.
- Mechanism: Pending rewards are valued *net of fee* by `getTotalRewards()` (it returns `totalRewards - totalFees`). When an operator calls `harvest()`, the proxy claims the **gross** reward `R` and deposits it into the vault as WRON, so `super.totalAssets()` (= `IERC20(asset()).balanceOf(this)`) rises by the full `R`. Simultaneously `getTotalRewards()` drops by the net `R·(1-f)`. The net change to `totalAssets()` is therefore `+R·f`, exactly the amount booked into `operatorFeeAmount` — but `totalAssets()` never subtracts `operatorFeeAmount`, so the fee WRON owed to `feeRecipient` is counted toward depositor NAV / ERC‑4626 share price. (Same effect via `harvestAndDelegateRewards()`, where the gross reward is re‑staked and counted in `getTotalStaked()` while the fee is still owed.) When `fetchOperatorFee()` later withdraws those assets it removes WRON from the vault **without burning any shares**. The NAV stays overstated by `operatorFeeAmount` until the fee is finally fetched.
- Impact: While fees are accrued-but-unfetched, every share is overpriced by `operatorFeeAmount / totalSupply`. A user can deposit immediately before harvest (receiving shares priced against net pending rewards) and redeem after harvest at a price that includes the operator-fee portion, extracting a pro‑rata share of the fees; more generally any holder who `redeem`/`withdraw`s during this window is overpaid pro‑rata, draining the buffer meant to pay `feeRecipient`. The leak compounds as more fees accrue between fee fetches; eventually `fetchOperatorFee()` can be left unable to pay (insufficient liquid WRON), i.e. the protocol pays the operator fee out of remaining LPs’/last‑redeemers’ principal. Fix: `totalAssets()` must subtract `operatorFeeAmount`.

## Additional findings (single-reviewer)

## Inverted `onlyOperator` modifier locks out all operators and can permanently brick the owner
*(Reviewer A only)*
- Location: `src/LiquidRon.sol` : `onlyOperator` modifier — `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`
- Mechanism: The condition is logically wrong. Applying De Morgan, the call only passes when `msg.sender == owner() && !operator[msg.sender]`. Intended logic was clearly `if (msg.sender != owner() && !operator[msg.sender]) revert`. As written: (a) any address in the `operator` mapping that is *not* the owner always satisfies `msg.sender != owner()` and is rejected — the operator role is completely non‑functional; (b) if the owner is ever added to the `operator` mapping (the natural way to let the owner act as operator), `operator[owner] == true` makes the `||` true and the owner is rejected too.
- Impact: All operator‑gated functions — `harvest`, `harvestAndDelegateRewards`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, and critically `finaliseRonRewardsForEpoch` — can never be called by designated operators. If the owner mistakenly grants themselves operator status, every one of these becomes uncallable by anyone, freezing stake management and the entire withdrawal‑finalisation pipeline. Since users can only get staked RON back through `finaliseRonRewardsForEpoch` → `redeem(epoch)`, this is a permanent denial‑of‑service / funds‑lockup condition that depends only on a single innocuous configuration call.

## Async withdrawal redemptions underpay when share price is above 1
*(Reviewer B only)*
- Location: `src/LiquidRon.sol` : `finaliseRonRewardsForEpoch`, `redeem(uint256)`, `_convertToAssets`
- Mechanism: The epoch snapshot stores `lockedShares` and `assets`, but redemption converts each user’s snapshot shares using `_convertToAssets(shares, assetSupply, shareSupply)`, which adds ERC‑4626 virtual offsets: `_totalAssets + 1` and `_totalShares + 10 ** _decimalsOffset()`. For a closed withdrawal epoch, conversion should be purely pro‑rata over the locked snapshot. With the virtual denominator, users are systematically underpaid whenever `assetSupply > shareSupply`.
- Impact: Any user using the delayed withdrawal flow can lose part of their redeemed RON after rewards increase share price. The unpaid assets remain stranded in `Escrow`, with no recovery path shown. No special attacker is required; a finalised withdrawal epoch at PPS > 1 triggers the loss.

## `maxWithdraw` / `maxRedeem` overstate withdrawable amount versus what `withdraw`/`redeem` can actually pay
*(Reviewer A only)*
- Location: `src/LiquidRon.sol` : inherited `maxWithdraw`/`maxRedeem` (derived from `totalAssets()`) vs. overridden `withdraw()` / `redeem()` which call `_withdrawRONTo` → `IWRON.withdraw`.
- Mechanism: `totalAssets()` includes `getTotalStaked()` and `getTotalRewards()`, i.e. RON that is delegated to validators and not liquid in the vault. `maxWithdraw(owner)` is computed from that full NAV. But the actual `withdraw()`/`redeem()` path requires the vault to hold enough liquid WRON: `super.withdraw` does `SafeERC20.safeTransfer(asset, this, assets)` and then `_withdrawRONTo` calls `IWRON(wron).withdraw(assets)`, both of which revert if the vault’s WRON balance is below `assets`. There is no on‑chain reconciliation between `maxWithdraw` and the liquid balance.
- Impact: At boundary values (most assets delegated), `maxWithdraw`/`maxRedeem` report a figure far larger than the contract can satisfy, so a compliant integrator or user calling `withdraw(maxWithdraw(addr), …)` reverts. This breaks the ERC‑4626 invariant that a withdrawal of `maxWithdraw` must succeed, and can cause downstream protocols that rely on these views to mis‑size operations / get stuck. (The `requestWithdrawal` epoch flow is the intended escape hatch, but the standard ERC‑4626 surface is still left inconsistent.)

## CEI violation: `requestWithdrawal` makes an external call to the caller before updating state
*(Reviewer A only)*
- Location: `src/LiquidRon.sol` : `requestWithdrawal(uint256 _shares)` — `_checkUserCanReceiveRon(msg.sender)` (which executes `payable(_user).call{value: 0}("")`) runs before `request.shares += _shares`, `lockedSharesPerEpoch[epoch] += _shares`, and `_transfer(...)`.
- Mechanism: An arbitrary low‑level call is made to `msg.sender` (fully attacker‑controlled) at the very start of the function, before any state mutation and before the share transfer. This is a classic checks‑effects‑interactions violation and an open reentrancy surface into every non‑paused function of the vault.
- Impact: No clean fund‑draining sequence was constructed, because the subsequent `_transfer(msg.sender, address(this), _shares)` and any reentered `redeem`/`withdraw` are bounded by the attacker’s actual ERC‑20 share balance (a reentrant redeem that burns the shares makes the outer `_transfer` revert on insufficient balance). However, the pattern is unsafe — the only reason it isn’t exploitable is incidental balance checks. Given the contract’s other accounting subtleties, the external call should be removed/moved after state updates (and `whenNotPaused` plus a reentrancy guard added) so a future change doesn’t turn this into a live exploit.

## Redundant full-array `claimRewards` loop in proxy `harvest()`
*(Reviewer A only)*
- Location: `src/LiquidProxy.sol` : `harvest()`
- Mechanism: The loop `for (i…_consensusAddrs.length) { claimRewards(_consensusAddrs); }` calls `claimRewards` with the **entire** array on every iteration, i.e. `N` redundant full‑array claims (only the first does anything; the rest claim zero). It should call `claimRewards(_consensusAddrs)` once.
- Impact: Not a theft vector, but wasted gas that grows quadratically with the validator set and can hit the block gas limit, making harvest revert — a soft DoS on reward collection.

## `WithdrawalClaimed` event emitted with wrong epoch
*(Reviewer A only)*
- Location: `src/LiquidRon.sol` : `redeem(uint256 _epoch)`
- Mechanism: The `WithdrawalClaimed` event is emitted with `epoch` (= the *current* `withdrawalEpoch`) instead of the `_epoch` actually being redeemed (`emit WithdrawalClaimed(msg.sender, epoch, shares, assets)`). This is an event‑vs‑state desync.
- Impact: Mislabels every historical claim and breaks off‑chain accounting/indexers that key on the emitted epoch.

