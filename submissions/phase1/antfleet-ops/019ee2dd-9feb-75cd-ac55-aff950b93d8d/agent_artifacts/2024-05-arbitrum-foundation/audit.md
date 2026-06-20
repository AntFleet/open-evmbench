# Audit: 2024-05-arbitrum-foundation

 ## Arbitrary sequencer sub-message count manipulation
- Location: `src/bridge/AbsBridge.sol` : `enqueueSequencerMessage`
- Mechanism: The consistency check `sequencerReportedSubMessageCount != prevMessageCount && prevMessageCount != 0 && sequencerReportedSubMessageCount != 0` lets any caller bypass validation by supplying `prevMessageCount == 0`. The function then assigns `sequencerReportedSubMessageCount = newMessageCount` without enforcing `newMessageCount >= prevMessageCount` or any upper bound. Since only `SequencerInbox` can call this, a compromised batch poster/sequencer can reset the counter to any value, including a lower one, in a single batch.
- Impact: Corrupts the on-chain reported sub-message count, breaking the invariant that the count only increases monotonically and enabling inconsistent message numbering or censorship via malformed batches.

## GasRefunder reentrancy and over-refund
- Location: `src/bridge/GasRefunder.sol` : `onGasSpent`
- Mechanism: `onGasSpent` has no reentrancy guard and sends ETH to `refundee`, which is `payable(msg.sender)` (an allowed contract), via a low-level `call` before updating any state or emitting the refund event. A malicious or compromised allowed contract can reenter during the ETH transfer, causing the inner call to compute a second refund from the current `gasleft()` while the outer call still refunds the gas consumed by the inner call. There is also no per-transaction one-call limit, so an allowed contract can call `onGasSpent` repeatedly to be paid for gas it intentionally burns.
- Impact: The GasRefunder balance can be drained beyond the actual gas cost of a single transaction.

## Allow-list bypass via `tx.origin`
- Location: `src/bridge/AbsInbox.sol` : modifier `onlyAllowed`
- Mechanism: The modifier authorizes callers based on `isAllowed[tx.origin]` instead of `msg.sender`. Every inbox action gated by `onlyAllowed` (e.g., `createRetryableTicket`, `depositEth`, `sendL2Message`) therefore inherits the authorization of the transaction origin.
- Impact: A malicious or phishing contract can perform inbox operations on behalf of an allowed user whose `tx.origin` is reused, leading to unauthorized message submissions, deposits, or loss of funds tied to retryable tickets.

## Missing storage gaps in upgradeable contracts
- Location: `src/bridge/SequencerInbox.sol` and `src/challengeV2/EdgeChallengeManager.sol`
- Mechanism: Both contracts are upgradeable (they expose `initialize` / `postUpgradeInit` and are intended to sit behind proxies) but declare many storage variables without an appended `__gap`. Future implementation upgrades that add or reorder inherited storage can collide with existing slots such as `bridge`, `rollup`, `buffer`, `stakeToken`, `challengePeriodBlocks`, and `store`.
- Impact: A storage-layout collision on upgrade can corrupt critical protocol state, potentially bricking the contract or enabling unauthorized parameter/fund manipulation.

## Staking pools leave residual ERC20 allowances to rollup / challenge manager
- Location: `src/assertionStakingPool/AssertionStakingPool.sol` : `createAssertion`; `src/assertionStakingPool/EdgeStakingPool.sol` : `createEdge`
- Mechanism: Both pools use `safeIncreaseAllowance(target, requiredStake)` immediately before the external call that consumes the stake. If that external call fails after the approval, the allowance persists. For tokens that require resetting approval to zero before a new non-zero approval (e.g., USDT-style), all subsequent retries will revert permanently. Even for standard ERC20 tokens, a successful call may leave an outstanding allowance.
- Impact: Permanent DoS of pool creation for certain ERC20 stake tokens, plus an unnecessary lingering token allowance that increases the attack surface if the rollup or challenge manager is compromised.

## ERC20 Inbox can spend any token balance it holds to pay fees
- Location: `src/bridge/ERC20Inbox.sol` : `_deliverToBridge`
- Mechanism: `_deliverToBridge` checks the Inbox's native-token balance and pulls only the deficit from `msg.sender`. Any tokens already held by the Inbox are implicitly used for the current message's `tokenTotalFeeAmount` without attributing them to any particular sender.
- Impact: An unrelated caller can consume tokens held by the Inbox (e.g., pre-funded balances from a token-bridge flow or accidentally transferred funds) to pay retryable-ticket fees, potentially causing the intended deposit/bridge message to fail when the Bridge later pulls its expected amount.
