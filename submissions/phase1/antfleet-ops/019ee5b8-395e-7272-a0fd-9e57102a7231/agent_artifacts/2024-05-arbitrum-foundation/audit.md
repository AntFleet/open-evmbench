# Audit: 2024-05-arbitrum-foundation

## Required-stake decrease lets a slashed staker withdraw recorded stake
- Location: `src/rollup/RollupCore.sol` : `requireInactiveStaker`; `src/rollup/RollupUserLogic.sol` : `stakeOnNewAssertion` / `returnOldDeposit` / `reduceDeposit`
- Mechanism: `stakeOnNewAssertion` transfers the parent assertion’s `requiredStake` to `loserStakeEscrow` for non-first-child assertions but does not reduce the staker’s recorded `amountStaked`. `requireInactiveStaker` then treats the staker as inactive once their latest assertion merely has a child, and staking logic lets them move away once that child exists. If `requiredStake` is lowered, an attacker can create a losing old-stake assertion, have an accomplice create its lower-stake child, become “inactive,” and withdraw the original high recorded stake even though that stake was already swept.
- Impact: The attacker can recover stake that should have been lost, making rollup escrow undercollateralized. Honest validators may become unable to withdraw legitimate assertion stakes because recorded balances exceed available tokens.

## `LOCAL_SET` one-step proof leaves locals unchanged
- Location: `src/osp/OneStepProver0.sol` : `executeLocalSet`
- Mechanism: `executeLocalSet` pops the new value, calls `mach.frameStack.peek()`, and assigns a new `localsMerkleRoot` to the returned `StackFrame memory` copy. The modified frame is never written back to `mach.frameStack.proved[0]`, while the final machine hash is computed from the unchanged frame stack. The on-chain transition for opcode `LOCAL_SET` therefore diverges from the intended WASM semantics.
- Impact: A malicious challenger can prove an invalid machine transition involving `LOCAL_SET`, allowing the challenge game to confirm an incorrect edge and potentially let an invalid assertion path defeat the honest one.

