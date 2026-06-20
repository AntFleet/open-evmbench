# Audit: 2024-05-olas

I focused on the project-specific contracts (`OLA`, `VotingEscrow`, `buOLA`, `GuardCM`, the bridge verifiers); the bulk of the file is unmodified OpenZeppelin/Curve code. Genuine findings below.

## Revoked vesting permanently locks remaining tokens after a partial withdrawal
- Location: `buOLA-flatten.sol` : `revoke` (and `withdraw`)
- Mechanism: `_releasableAmount()` returns the *incremental* claimable amount (`amountLocked * releasedSteps / numSteps - amountReleased`). `revoke()` then writes that incremental value back into the cumulative field: `lockedBalance.amountReleased = uint96(amountRelease)`. Everywhere else in the contract `amountReleased` is treated as the cumulative total ever withdrawn (`withdraw` does `amountReleased += amount`). So if a user has already withdrawn some amount `R1` (cumulative `amountReleased = R1`) and the owner later revokes, the field is overwritten with `vested - R1`, destroying the record of `R1`. In the post‑revoke `withdraw` (`end == 0` branch) the burn is computed as `amountBurn = amountLocked - amountReleased = (amountLocked - vested) + R1`, which is `R1` too large. The contract only holds `amountLocked - R1` OLA, so `IOLA(token).burn(amountBurn)` underflows the contract's balance and reverts.
- Impact: A locker who withdrew any vested portion before being revoked can never withdraw again — `withdraw()` reverts forever, permanently freezing the remaining vested OLA they are owed. (Absent the revert, the `supply` accounting would also be corrupted by `R1`.) The exploit path is a normal owner `revoke` of an account that exercised its normal `withdraw`.

## Anyone can open a lock on behalf of an arbitrary account, blocking the victim's own lock
- Location: `VotingEscrow-flatten.sol` : `createLockFor` (same pattern in `buOLA-flatten.sol` : `createLockFor`)
- Mechanism: `createLockFor(account, amount, unlockTime)` only requires `account`'s existing lock to be empty (`lockedBalance.amount == 0`) and pulls the tokens from `msg.sender`. There is no authorization that `msg.sender == account` or any consent from `account`. An attacker can create a dust lock (e.g. 1 wei) for a target address with attacker-chosen `unlockTime`.
- Impact: The victim can no longer call `createLock`/`createLockFor` for themselves (it reverts with `LockedValueNotZero`), so they cannot choose their own initial lock parameters; they are forced to inherit the attacker's `unlockTime` and adjust via `increaseAmount`/`increaseUnlockTime`. The griefer can also assign unwanted, long-duration locked voting power to an address. Funds are not stolen (attacker pays), so this is a low-severity griefing / loss-of-control issue, but it is a genuine missing access check.

I did not find exploitable reentrancy (guards present and state is updated before external transfers), and the inflation cap / checkpoint math in `OLA` and `VotingEscrow` stays within the documented bit-width bounds.

