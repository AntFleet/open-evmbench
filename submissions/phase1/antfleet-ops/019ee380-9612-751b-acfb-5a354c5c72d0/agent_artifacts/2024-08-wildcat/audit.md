# Audit: 2024-08-wildcat

After a careful pass over the Wildcat hooks/market system, the code is overwhelmingly the well-audited V2 codebase. The one place where I found a concrete, exploitable interaction problem is in `FixedTermLoanHooks.onQueueWithdrawal`, which reverts unconditionally before the term ends and is reachable from privileged/forced flows that are not supposed to be subject to the term gate.

## FixedTermLoanHooks term-gate DoS blocks sanctions enforcement (`nukeFromOrbit`) and exit from a closed market
- Location: `src/access/FixedTermLoanHooks.sol` : `onQueueWithdrawal` (interacting with `src/market/WildcatMarket.sol`: `_blockAccount`/`nukeFromOrbit` and `closeMarket`)
- Mechanism: `FixedTermLoanHooks.onQueueWithdrawal` rejects *every* queued withdrawal while the term is active:

  ```solidity
  function onQueueWithdrawal(address lender, uint32, uint, MarketState calldata, bytes calldata hooksData) external override {
    HookedMarket memory market = _hookedMarkets[msg.sender];
    if (!market.isHooked) revert NotHookedMarket();
    if (market.fixedTermEndTime > block.timestamp) {
      revert WithdrawBeforeTermEnd();
    }
    ...
  }
  ```

  This hook is a **required** flag for the fixed-term template, so the market always invokes it on the queue-withdrawal path. The problem is that the queue-withdrawal path is also used for two flows that must not be gated by the lender-facing term:
  1. `WildcatMarketConfig.nukeFromOrbit` → `WildcatMarket._blockAccount` → `WildcatMarketWithdrawals._queueWithdrawal` → `hooks.onQueueWithdrawal(...)`. There is no `state.isClosed` or "is-forced/sanctions" exception, so the hook reverts with `WithdrawBeforeTermEnd` whenever `fixedTermEndTime > block.timestamp`.
  2. Lender exit after `closeMarket()`: closing sets APR to 0 and (for new batches) uses zero duration so withdrawals expire immediately, but a lender who has not yet queued must still call `queueWithdrawal`, which the hook rejects until the original term elapses.

  Note the sibling `AccessControlHooks.onQueueWithdrawal` does not have this problem: a depositor is a known lender (`isKnownLenderOnMarket`), so the sanctioned-account block path succeeds there.

- Impact:
  - Sanctions enforcement is denied-of-service for the whole fixed term. `nukeFromOrbit` cannot move a sanctioned lender's balance into the per-account escrow until `fixedTermEndTime`, defeating the protocol's compliance guarantee for fixed-term markets (the operator cannot quarantine a flagged account when required).
  - Lenders cannot exit a *closed*, 0%-yield fixed-term market until the term ends, even though the borrower has already topped the market up to full collateralization on close. Their assets sit idle and illiquid for up to the remaining term despite the market being shut down.

  The fix is to waive the term gate when the queue is driven by a forced/sanctions block (or when `state.isClosed`), e.g. allow the queue through for known lenders / closed markets / the `_blockAccount` path, mirroring the `AccessControlHooks` behavior.

Outside of this, I did not find additional genuine vulnerabilities: the state-slot packing in `WildcatMarketBase._writeState`, the withdrawal pro‑rata accounting, the reserve-ratio / temporary-excess logic in `MarketConstraintHooks`, the credential/role-provider access control, the create2/stored-initcode deployment paths, and the sanctions sentinel/escrow all check out against the intended behavior, and the access-control modifiers on the privileged setters are present and correct.

