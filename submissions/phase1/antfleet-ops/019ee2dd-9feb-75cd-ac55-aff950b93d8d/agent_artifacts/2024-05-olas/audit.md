# Audit: 2024-05-olas

 ## TimelockController `execute`/`executeBatch` reentrancy
- Location: `TimelockController.sol` : `execute` and `executeBatch`
- Mechanism: `_beforeCall` checks that the operation is ready, `_call` performs the external call(s), and only then does `_afterCall` mark the operation as done. A malicious target called during execution can reenter the Timelock before the state update; the post-call `isOperationReady` check only catches the replay after the reentrant call has already run.
- Impact: A governance-scheduled target can force operations to execute multiple times or in an intermediate state, enabling duplicate transfers, unexpected ordering with predecessor-dependent operations, or denial of queued execution. This is the known OpenZeppelin v4.6 pattern that later versions mitigate with `nonReentrant`.

## OLA `mint` silently skips over-cap mints
- Location: `OLA.sol` : `mint`
- Mechanism: The function only mints inside `if (inflationControl(amount)) { _mint(account, amount); }`. If the amount exceeds the inflation remainder, the condition is false and the call returns without minting, reverting, or emitting any event.
- Impact: Integrations or minters that do not explicitly verify balances may assume the mint succeeded and credit tokens off-chain while no OLA were actually created, causing accounting mismatches.

## OLA constructor can permanently disable `mint`
- Location: `OLA.sol` : `constructor` / `inflationRemainder`
- Mechanism: The constructor mints `_supply` without validating it against `tenYearSupplyCap`. `inflationRemainder` then computes `supplyCap - totalSupply` with no underflow protection, so if `totalSupply` is ever larger than `supplyCap` the function reverts.
- Impact: If the deployer sets an initial supply above the ten-year cap, `inflationControl` always reverts and `mint` becomes permanently unusable.

## VotingEscrow checkpoint becomes stale after >255 weeks of inactivity
- Location: `VotingEscrow.sol` : `_checkpoint`
- Mechanism: The weekly point-fill loop is capped at 255 iterations. If more than 255 weeks pass without a checkpoint, the loop exits before reaching `block.timestamp` and stores a supply point whose timestamp and block number lag behind the current chain state.
- Impact: `getPastTotalSupply`, `totalSupplyLocked`, and related time-weighted reads become incorrect until enough subsequent checkpoints catch up, which can distort quorum calculations and governance snapshots during extended low-activity periods.

## GuardCM does not restrict non-schedule timelock calls
- Location: `GuardCM.sol` : `checkTransaction`
- Mechanism: `checkTransaction` only inspects calls whose `to` is the timelock and whose selector is `schedule` or `scheduleBatch`. Calls to other timelock functions, such as `cancel(bytes32)` or `executeBatch`, are allowed without any target/selector verification.
- Impact: If the guarded community multisig holds the `CANCELLER_ROLE` or `EXECUTOR_ROLE` on the timelock, it can bypass the intended whitelist to cancel queued proposals or execute them without guard review, defeating the guard's purpose.

## buOLA owner can unilaterally burn locked tokens
- Location: `buOLA.sol` : `revoke`
- Mechanism: Only the contract owner can call `revoke`, which immediately flags a lock as revoked and causes all non-released tokens to be burned on the user's next `withdraw`. There is no timelock, multi-sig enforcement, or two-step process in the contract itself.
- Impact: A compromised or malicious owner can destroy a user's unvested buOLA balance at any time, resulting in direct loss of user funds.

## OLA owner/minter changes are single-step and minter can be zeroed
- Location: `OLA.sol` : `changeOwner` / `changeMinter`
- Mechanism: `changeMinter` has no zero-address check, and neither function uses a two-step transfer with acceptance. The owner can instantly set `minter` to any address, including `address(0)`.
- Impact: A typo, compromised owner key, or front-running mistake can permanently disable minting by setting `minter` to the zero address, or transfer minting power to an attacker with no recovery path.

## GuardCM target-selector keys can collide for oversized chain IDs
- Location: `GuardCM.sol` : `setTargetSelectorChainIds` / `VerifyData._verifyData`
- Mechanism: The authorization key is built by shifting `chainIds[i]` left by 192 bits with no mask or upper-bound check other than `chainId > 0`. A `chainId` larger than `type(uint64).max` is truncated inside the 256-bit key, so two different chain IDs can map to the same storage slot.
- Impact: A misconfiguration (or malicious owner) can create colliding authorizations, causing an unauthorized chain's calls to be treated as whitelisted or making the authorization mapping behave inconsistently.
