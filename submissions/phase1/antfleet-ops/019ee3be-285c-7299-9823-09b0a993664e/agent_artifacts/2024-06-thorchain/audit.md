# Audit: 2024-06-thorchain

**## Reentrancy / Callback Attack via Native Token Receipt**
- Location: `chain/ethereum/contracts/THORChain_Router.sol:transferOut` (and `transferOutV5`/`batchTransferOutV5`), `transferOutAndCall`, `returnVaultAssets`; equivalent paths in `AvaxRouter.sol:transferOut`/`deposit`; `EvilCallback.sol:receive`
- Mechanism: Low-level `.send`/`.transfer` (or implicit forwarding) of AVAX/ETH to an arbitrary `to`/`target`/`asgard`/`vault` executes the recipient's `receive()` (or fallback). `EvilCallback.receive` immediately calls back into the router via `transferAllowance` (or a fake `depositWithExpiry` that re-enters `deposit`). The `nonReentrant` modifier only guards the outer entry point; the callback occurs while state (allowances, `_status`) is already mutated and before the outer function returns. No `msg.sender`/`tx.origin` checks or context validation on incoming native-value transfers.
- Impact: Attacker-controlled contract can mutate vault allowances, emit spoofed `TransferAllowance`/`Deposit` events, or cause Bifrost to miss Yggdrasil observations, enabling double-spend or incorrect accounting of vault funds.

**## Unsafe Balance Accounting in Aggregator (Extra Native Tokens Drained)**
- Location: `avalanche/src/contracts/AvaxAggregator.sol:swapIn` (lines ~70-80) and `chain/avalanche/...` duplicate; `THORChain_Aggregator.sol:swapIn` (and `swapOutV5`)
- Mechanism: After `safeTransferFrom` + swap, `safeAmount = address(this).balance` (full contract balance) is forwarded to `depositWithExpiry`. No subtraction of pre-existing balance, no `msg.value` accounting, and `receive()` is payable with no access control. Previous AVAX/ETH (from prior failed swaps, direct sends, or other calls) is included.
- Impact: Any caller (permissionless) can force the aggregator to forward attacker-supplied or leftover native tokens to a THORChain vault under an arbitrary memo, draining or mis-attributing funds.

**## Allowance Underflow / Incorrect Deduction on Fee-on-Transfer Tokens (TransferOut Path)**
- Location: `THORChain_Router.sol:transferOut` (ERC20 branch, line ~140) and `AvaxRouter.sol:transferOut`; `_routerDeposit`
- Mechanism: `_vaultAllowance[msg.sender][asset] -= amount` is performed unconditionally before the low-level `transfer` call. The deduction uses the nominal `amount`, not the actual received amount returned by a fee-on-transfer token. No use of `safeTransferFrom`-style balance-diff logic (unlike `deposit`).
- Impact: Vault allowance can underflow or become permanently inconsistent with actual token balances held by the router, allowing a subsequent caller to transfer more tokens than remain or locking funds.

**## Reentrancy via ERC20 `transferFrom` Callback (Nested Deposit)**
- Location: `chain/ethereum/contracts/EvilToken.sol:transferFrom` (and `StealERC20Token`); called from `AvaxRouter.safeTransferFrom`/`deposit` and `THORChain_Router._deposit`
- Mechanism: Malicious `transferFrom` implementation (when `!second`) mutates its own balances/allowances then calls `iROUTER(to).deposit(...)` while the outer `deposit`/`safeTransferFrom` is still executing. The router's `nonReentrant` is already set, but the inner call bypasses the caller's intended single-deposit semantics and can credit allowances multiple times before the outer function finishes.
- Impact: Attacker token can cause multiple `Deposit` events / allowance credits from a single user `transferFrom`, enabling inflation of vault credits without corresponding token movement.

**## Missing Authorization on `rescueFunds` Owner-Only Path Combined with Permissionless Aggregator**
- Location: `THORChain_Aggregator.sol:rescueFunds` (onlyOwner) vs. fully permissionless `swapIn`/`swapOut`; same pattern absent in `AvaxAggregator`
- Mechanism: Aggregator holds arbitrary ERC20 + native balances after swaps. `owner` can unilaterally drain any asset, while any user can still call `swapIn` and route through the same contract.
- Impact: Owner (or compromised owner key) can steal user funds that are temporarily resident in the aggregator; no timelock or multi-sig on rescue.

All other issues observed (gas stipend on `.send`, duplicate source files, comment typos, `type(uint256).max` deadlines) are either intentional design choices or non-security.
