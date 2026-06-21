# Audit: 2024-01-curves
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Broken `onlyOwner` / `onlyManager` modifiers — total loss of access control
*(consensus, 6 of 6 reports)*
- Location: `contracts/Security.sol` : `onlyOwner`, `onlyManager` modifiers
- Mechanism: Both modifier bodies contain a bare boolean expression statement (`msg.sender == owner;` and `managers[msg.sender] == true;`) that is evaluated and discarded — no `require`, no `if/revert`, no `assert`. Execution always falls through to `_;`, so no caller is ever rejected. Every function guarded by these modifiers is effectively public.
- Impact: Anyone can call `Security.transferOwnership` (seize ownership) and `Security.setManager` (grant self manager) on both `Curves` and `FeeSplitter`, then `setProtocolFeePercent` / `setExternalFeePercent` / `setMaxFeePercent` (redirect/steal protocol fees, set confiscatory or >100% fees), `setERC20Factory` / `setFeeRedistributor` (swap in malicious contracts), and `FeeSplitter.addFees` / `onBalanceChange` (corrupt or wipe fee accounting). Total compromise of every privileged path.

## Token transfers / wrapping never update FeeSplitter offsets — repeatable holder-fee theft
*(consensus, 6 of 6 reports)*
- Location: `contracts/Curves.sol` : `_transfer`, `transferCurvesToken`, `transferAllCurvesTokens`, `withdraw`, `deposit` ; interacting with `contracts/FeeSplitter.sol` : `getClaimableFees` / `updateFeeCredit` / `claimFees`
- Mechanism: Holder fees use a MasterChef-style debt model: `claimable = (cumulativeFeePerToken − userFeeOffset[account]) * balanceOf / PRECISION`. `userFeeOffset` is only ever initialized inside `onBalanceChange`, which `Curves` calls solely on the buy/sell path in `_transferFees`. `_transfer` (used by `transferCurvesToken`/`transferAllCurvesTokens`) and the `withdraw`/`deposit` wrap/unwrap paths move balances without notifying `FeeSplitter`. A recipient that never traded keeps the default `userFeeOffset == 0`, so its claimable equals the *entire historical* `cumulativeFeePerToken * balance`, as if held since genesis.
- Impact: An attacker with any balance waits for fees to accrue, transfers (or wraps/unwraps) the tokens to a fresh zero-offset address, calls `claimFees` to harvest the full historical fee-per-token, then repeats with the same tokens through new fresh addresses. Because all tokens' holder fees pool in one shared ETH balance, this drains the entire `FeeSplitter`, including funds owed to legitimate holders. No flash loan or admin role required.

## `FeeSplitter.setCurves` has no access control — fee-pool drain via fake balances
*(consensus, 5 of 6 reports)*
- Location: `contracts/FeeSplitter.sol` : `setCurves(Curves curves_)`
- Mechanism: `setCurves` is `public` with no modifier (not even a broken one). It repoints the `curves` reference that every accounting function (`balanceOf`, `totalSupply`, `getClaimableFees`, `addFees`) reads. An attacker sets `curves` to a malicious contract returning an arbitrarily large `curvesTokenBalance` for the attacker (and any benign supply).
- Impact: For any token with nonzero `cumulativeFeePerToken` (or bumped via the now-open `addFees`), `getClaimableFees` returns an attacker-chosen amount, so `claimFees` / `batchClaiming` drains the entire ETH balance of `FeeSplitter`. Independent of the broken modifiers; precondition is only that the splitter holds ETH.

## `onBalanceChange` resets the fee offset without crediting accrued fees
*(consensus, 5 of 6 reports)*
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange(address token, address account)` (called from `Curves._transferFees`)
- Mechanism: `onBalanceChange` sets `userFeeOffset[account] = cumulativeFeePerToken` **without** first calling `updateFeeCredit` to bank the owed `(cumulativeFeePerToken − oldOffset) * balance` into `unclaimedFees`. In buy/sell, the user's balance is already updated before `_transferFees` runs, so by the time the hook fires the previously accrued, unclaimed fees are silently discarded and the offset advanced past them.
- Impact: Honest holders lose all accrued-but-unclaimed holder fees whenever they trade again. Because `onlyManager` is broken, an attacker can call `onBalanceChange(token, victim)` directly to forcibly zero out any holder's pending rewards as a griefing attack.

## Cross-contract reentrancy window in `_transferFees` (no `nonReentrant` guard)
*(consensus, 2 of 6 reports)*
- Location: `contracts/Curves.sol` : `_transferFees` (called from `_buyCurvesToken` / `sellCurvesToken`)
- Mechanism: There is no reentrancy guard anywhere in the system. `_transferFees` makes raw `.call{value:...}` transfers to attacker-influenceable addresses — `curvesTokenSubject` (arbitrary, attacker-chosen on buy) and `msg.sender` (the seller) — *before* the `feeRedistributor.onBalanceChange` / `addFees` bookkeeping for the current trade completes. `FeeSplitter` reads live `curvesTokenBalance`/`curvesTokenSupply`, so during the callback its view of the trade is half-updated; `addFees` later divides `msg.value * PRECISION` by a supply the attacker can mutate mid-frame.
- Impact: A malicious subject (or seller) regains control with `FeeSplitter` in a half-updated state and can re-enter `buyCurvesToken` / `sellCurvesToken` / `claimFees` across subjects, manipulating `cumulativeFeePerToken` relative to real supply and interleaving claims against stale offsets — widening the surface for the offset-accounting flaws above. Violates CEI for cross-contract fee state.
- Reviewer disagreement: One opus shot examined this path and argued balance/supply are updated before the external `.call`s and `claimFees`/`batchClaiming` use `.transfer` (2300 gas), so it could not construct a profitable reentrancy beyond the already-reported accounting issues.

## Fee setters lack an upper bound — fees ≥100% brick selling
*(consensus, 2 of 6 reports)*
- Location: `contracts/Curves.sol` : `setMaxFeePercent`, `setProtocolFeePercent`, `setExternalFeePercent` ; consumed in `_transferFees`
- Mechanism: `setMaxFeePercent` has no upper bound and the other setters only constrain the fee sum to `<= maxFeePercent`; nothing checks the total stays below 100% (`1 ether`). If the configured percentages sum to `>= 1 ether`, the sell branch `sellValue = price − protocolFee − subjectFee − referralFee − holderFee` underflows and reverts under checked arithmetic.
- Impact: Any caller (the privileged check is broken) can set fees to ≥100% and permanently brick `sellCurvesToken` and every flow routing through it (e.g. `sellExternalCurvesToken`), locking holders' funds in the bonding curve. A configuration footgun with no guardrail even if access control worked.

## Holder-fee distribution blocks valid sells when remaining supply is wrapped
*(consensus, 2 of 6 reports)*
- Location: `contracts/Curves.sol` : `sellCurvesToken`, `_transferFees` ; `contracts/FeeSplitter.sol` : `totalSupply`, `addFees`
- Mechanism: On sells, `Curves` decrements the seller's balance and total supply *before* `_transferFees` calls `feeRedistributor.addFees`. `FeeSplitter.totalSupply` excludes Curves tokens locked in the Curves contract as wrapped-ERC20 backing. If a sale leaves only wrapped/locked tokens outstanding, `totalSupply_ == 0` and `addFees` reverts with `NoTokenHolders`, rolling back the whole sale.
- Impact: With holder fees enabled, the last circulating internal holder cannot exit whenever post-sale circulating supply would be zero while wrapped ERC20 tokens remain. An attacker holding other supply can wrap it via `withdraw` to deliberately trap a victim's full-exit sale (and, via the broken fee setters, can enable a nonzero holder fee to arm this DoS).

## Minority findings

## Precision-destroying scaling in `addFees` — holder fees rounded away / stuck
*(minority, 1 of 6 reports)*
- Location: `contracts/FeeSplitter.sol` : `addFees`, with `balanceOf` / `totalSupply`
- Mechanism: `balanceOf` and `totalSupply` both multiply the raw Curves balance/supply by `PRECISION` (1e18). `addFees` computes `cumulativeFeePerToken += (msg.value * PRECISION) / totalSupply_` where `totalSupply_ = tokens * PRECISION`; the two `PRECISION` factors cancel, reducing the expression to integer `msg.value / tokens` and discarding the `msg.value % tokens` remainder on every call.
- Impact: Each fee deposit strands up to `(supply − 1)` wei in the contract. If `msg.value < tokens` (small fee, large supply), `cumulativeFeePerToken` increments by 0 and the entire deposited holder fee is lost/stuck — distributing nothing to holders while still charging the trader.

## `withdraw` deploys a subject's ERC-20 without the `onlyTokenSubject` check
*(minority, 1 of 6 reports)*
- Location: `contracts/Curves.sol` : `withdraw` → `_deployERC20`
- Mechanism: ERC-20 deployment is normally gated through `_mint` (`onlyTokenSubject`). `withdraw` instead calls `_deployERC20` directly when no token exists, requiring only that the caller hold a balance of the subject's token — not that they *be* the subject — defaulting `name`/`symbol` to `DEFAULT_NAME`/`DEFAULT_SYMBOL`.
- Impact: Any non-subject holder can force-deploy a subject's ERC-20, claiming the symbol namespace via `symbolToSubject` and locking in a default/auto-numbered name. The real subject is then permanently blocked from `setNameAndSymbol`/`mint` (reverts `ERC20TokenAlreadyMinted`) — a griefing / namespace-squatting vector.

## Sell-side protocol fee (and undefined referral fee) trapped in `Curves`
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `contracts/Curves.sol` : `_transferFees` (sell branch)
- Mechanism: On sells, `firstDestination` is `msg.sender` and the contract sends `price − protocolFee − subjectFee − referralFee − holderFee` to the seller, pays the subject fee, optionally the referral fee, and holder fees — but never forwards the sell-side `protocolFee` to `protocolFeeDestination`. If no referral destination is defined, the sell-side `referralFee` is likewise subtracted and sent nowhere.
- Impact: Sellers are charged fees that remain permanently stuck in `Curves` instead of being distributed; combined with the broken fee setters, an attacker can raise these to confiscatory levels causing severe seller loss / sell-path DoS.
- Reviewer disagreement: Two opus shots examined the same sell-side stuck protocol fee and classified it as stranded/stuck value that is not attacker-reachable theft, so they deliberately did not list it as a vulnerability.

## Zero-amount transfers permanently bloat a victim's token-subject list
*(minority, 1 of 6 reports)*
- Location: `contracts/Curves.sol` : `transferCurvesToken`, `_transfer`, `_addOwnedCurvesTokenSubject`, `transferAllCurvesTokens`
- Mechanism: `_transfer` adds `curvesTokenSubject` to the recipient's `ownedCurvesTokenSubjects` before changing balances and permits `amount == 0`; the zero-balance check passes even though the sender owns nothing of that subject.
- Impact: An attacker can repeatedly call `transferCurvesToken(arbitrarySubject, victim, 0)` with many distinct subject addresses, permanently bloating the victim's private subject list until `transferAllCurvesTokens` runs out of gas and becomes unusable for that victim.

## `onBalanceChange` unconditionally pushes duplicate tokens — `userTokens` bloat / DoS
*(minority, 1 of 6 reports)*
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange`
- Mechanism: Distinct from the offset-reset defect: `onBalanceChange` unconditionally executes `userTokens[account].push(token)` whenever balance > 0, with no de-duplication. Repeated buys append duplicate entries to `userTokens`.
- Impact: The growing array bloats `getUserTokensAndClaimable` / `batchClaiming`. Because the broken `onlyManager` lets anyone call `onBalanceChange(token, victim)`, an attacker can spam duplicate pushes to inflate a victim's `userTokens` array toward out-of-gas, griefing their claim path.

