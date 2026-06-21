# Audit: 2025-05-blackhole
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Audit report merge — Black/Blackhole ve(3,3) fork

Eighteen distinct findings were surfaced across the six input reports (claude-opus-4-8 ×3, gpt-5.5 ×3). All eighteen are reproduced below: 11 consensus, 7 minority. Nothing has been filtered on plausibility.

---

## Consensus findings

## `claim_many` misroutes AVM rebase rewards into the child escrow
*(consensus, 5 of 6 reports)*
- Location: contracts/RewardsDistributor.sol : `claim_many`
- Mechanism: `claim()` handles AVM-custodied NFTs (`if (avm.tokenIdToAVMId(_tokenId) != 0)` → pay `avm.getOriginalOwner(_tokenId)`). `claim_many()` omits that branch: for an expired, non-permanent lock it computes `_nftOwner = IVotingEscrow(_voting_escrow).ownerOf(_tokenId)`, which for an auto-voted NFT is the child `AutoVotingEscrow` contract (no function to move ERC20 out). The reward cursor is advanced before payout completes.
- Impact: The function is permissionless — anyone can call `claim_many([tokenId])` on an expired AVM-held lock and force the BLACK rebase into the child escrow, where it is unrecoverable. Silent, griefable, permanent loss of a rebase the single `claim` path would have delivered correctly.
- Reviewer disagreement: none material (the one report that did not flag it discussed only `distribute*/claimFees/notifyRewardAmount`, not `claim_many`).

## `setRouter` has an inverted require and can only zero the router
*(consensus, 3 of 6 reports)*
- Location: contracts/GenesisPoolManager.sol : `setRouter`
- Mechanism: `require(_router == address(0), "ZA"); router = _router;`. The guard is inverted — it passes only when `_router` is the zero address, so the only value the setter can ever store is `address(0)`; any real router reverts.
- Impact: The owner can never repoint `router` to a valid address, and the one reachable state (`router == 0`) bricks the launch path: `_launchPool → IGenesisPool.launch(router, MATURITY_TIME) → IRouter(router).addLiquidity(...)` reverts, halting all genesis pool launches. Setter admits an invalid value that bricks later logic.

## `setInternalBribe` zero-address guard is a no-op (`>= address(0)`)
*(consensus, 3 of 6 reports)*
- Location: contracts/GaugeV2.sol : `setInternalBribe` and contracts/AlgebraCLVe33/GaugeCL.sol : `setInternalBribe`
- Mechanism: Both use `require(_int >= address(0), ...)`. Addresses are unsigned, so the comparison is always true; the intended non-zero check never rejects anything, including `address(0)`.
- Impact: `internal_bribe` can be set to `address(0)`. The gauge's `_claimFees` path (`safeApprove(internal_bribe, ...)` / `IBribe(internal_bribe).notifyRewardAmount(...)`) then reverts against a no-code address, bricking fee forwarding for that gauge. Owner-gated, but the guard provides false safety and a single fat-finger disables fee accrual.

## `notifyRewardAmount` named return shadows the `rewardRate` state variable
*(consensus, 3 of 6 reports)*
- Location: contracts/AlgebraCLVe33/GaugeCL.sol : `notifyRewardAmount` (`returns (..., uint256 rewardRate, ...)`)
- Mechanism: The named return `rewardRate` shadows the `uint256 public rewardRate` storage variable. Every assignment and the read `uint256 leftover = remaining * rewardRate` bind to the local (default 0), never to storage. So `leftover` is always 0 (the mid-period carry-over branch is dead) and storage `rewardRate` is never written.
- Impact: A top-up while `block.timestamp < _periodFinish` recomputes the rate as `reward / DURATION`, silently discarding the still-undistributed remainder, under-rating emissions and stranding the residual. Storage `rewardRate` stays 0 permanently, so `rewardForDuration()`, `rewardRate()`, and every consumer (e.g. `AlgebraPoolAPI._poolAddressToInfo` → `info.emissions`, `BlackholePairAPIV2`) report zero emissions.

## CL referral/dibs fee is unbounded, enabling underflow DoS of fee distribution
*(consensus, 3 of 6 reports)*
- Location: contracts/AlgebraCLVe33/GaugeFactoryCL.sol : `setReferralFee`; effect in contracts/AlgebraCLVe33/GaugeCL.sol : `_claimFees`, `stakedFees`
- Mechanism: `setReferralFee(uint256 _dibsFee)` sets `dibsPercentage` with no upper bound. `_claimFees`/`stakedFees` compute `_dibsFeeToken = claimed * referralFee / REFERRAL_FEE_DENOMINATOR (1000)` then `claimed -= _dibsFeeToken`. If `dibsPercentage > 1000`, `_dibsFeeToken > claimed`, so the subtraction underflows and reverts (and `== 1000` routes 100% of LP fees to `dibs`).
- Impact: A `GAUGE_ADMIN`/owner misconfiguration (value > 100%) makes `GaugeCL.claimFees()` revert permanently, which makes `GaugeManager.distributeFees()` revert for that CL pool; accrued fees are stranded and the `stakedFees()` view also reverts. No guardrail; persists until reset.

## AVM bribe/fee rewards are routed to the child escrow instead of the original owner
*(consensus, 3 of 6 reports)*
- Location: contracts/Bribes.sol : `getReward`; interacts with contracts/AVM/AutoVotingEscrowManager.sol (`originalOwner`/`setOriginalOwner`/`getOriginalOwner`) and contracts/GaugeManager.sol : `claimBribes`
- Mechanism: When a veNFT is auto-voting, `enableAutoVoting` transfers it into a freshly-deployed **child** `AutoVotingEscrow`, so `ve.ownerOf(tokenId)` is the child. In `getReward`, `_owner = ve.ownerOf(tokenId)` and the redirect guard `if (_owner == avm)` compares against the **manager** address (`avm = IVotingEscrow(ve).avm()`), not the child — so it is always false and `safeTransfer(_owner, _reward)` sends rewards into the child escrow, which cannot forward ERC20. Compounding root cause: even if the guard matched, it reads `IAutomatedVotingManager(avm).originalOwner(tokenId)`, an unpopulated mapping (`setOriginalOwner` has an empty body) returning `address(0)`; the working accessor is `getOriginalOwner`, which `claimBribes` itself uses for authorization.
- Impact: Every internal-fee and external-bribe reward earned by an auto-voted veNFT is silently routed to the child escrow (or to `address(0)` / a revert via the unset mapping). The original owner passes the `claimBribes` authorization check, the call succeeds without revert, but they receive nothing — permanent loss of all voting rewards for AVM participants.
- Reviewer disagreement: one report (opus shot 3) asserted `Bribe.getReward`/`claimBribes` "pay only the ve owner" and are gauge-manager gated, treating the path as sound.

## `getAmountsIn` loop counter underflows to a guaranteed revert
*(consensus, 2 of 6 reports)*
- Location: contracts/APIHelper/TradeHelper.sol : `getAmountsIn`
- Mechanism: `for (uint i = routes.length-1; i >= 0; i--)` — `i` is unsigned, so `i >= 0` is always true; after `i == 0` the decrement wraps to `2**256-1` and the loop re-enters, indexing `amounts[i+1]`/`routes[huge]` out of bounds.
- Impact: The function reverts on every call, a functional DoS of any reverse-routing / input-amount quoting integration. View-only — no fund movement — but genuinely broken.
- Reviewer disagreement: two reports classified this as an off-chain view-only correctness bug with no fund impact and did not count it as a security vulnerability.

## Concentrated swaps ignore the user's `amountOutMin`
*(consensus, 2 of 6 reports)*
- Location: contracts/RouterV2.sol : `_swap`, `swapExactTokensForTokensSimple`, `swapExactTokensForTokens`, `swapExactETHForTokens`, `swapExactTokensForETH`
- Mechanism: The router checks `amountOutMin` only against a pre-swap `getAmountsOut` quote, but concentrated-liquidity hops execute `ISwapRouter.exactInputSingle` with `amountOutMinimum: 0`. The real output overwrites `amounts[i+1]` and no post-swap check verifies the final received amount against `amountOutMin`.
- Impact: A sandwich attacker (or any price move between quote and execution) can make a concentrated-route swap execute at a far worse price — potentially near-zero output — while the transaction still succeeds. Precondition: route includes at least one `concentrated == true` hop.

## Genesis LP can be drained via rounded-down deductions
*(consensus, 2 of 6 reports)*
- Location: contracts/GaugeV2.sol : `_withdraw`, `_deductBalance`; contracts/GenesisPool.sol : `deductAmount`, `balanceOf`
- Mechanism: `GaugeV2` lets a user withdraw arbitrary LP based on `_balanceOf` (which includes virtual genesis balances from `GenesisPool.balanceOf`), and `deductAmount` converts withdrawn LP back to funding-token debt with floor division `userAmount = totalDeposits * gaugeTokenAmount / depositerLiquidity`. For small `gaugeTokenAmount` this rounds to zero, so the gauge transfers LP out and decreases `_totalSupply` while `userDeposits` is never reduced. (One report also notes genesis depositors get `maturityTime == 0`, since only the token owner's maturity is set in `depositsForGenesis`.)
- Impact: A genesis depositor can repeatedly withdraw dust LP amounts without reducing their recorded genesis balance, draining LP allocated to other depositors/the token owner. Precondition: a launched genesis pool with a positive genesis deposit balance.
- Reviewer disagreement: two reports (opus shots 1 and 3) reviewed this exact path and defended it — claiming the `balanceOf`/`deductAmount` share math conserves `liquidity` and cannot over-withdraw because `GaugeV2._deductBalance` caps the genesis portion *(conflicting reviews: 2 of 6 reports defended this code path)*.

## Unrestricted custom pool creation can squat/register official CL pools
*(consensus, 2 of 6 reports)*
- Location: contracts/CustomPoolDeployer.sol : `createCustomPool`
- Mechanism: `createCustomPool` is `external` with no `onlyOwner`/`onlyAuthorized` restriction (the contract defines `onlyAuthorized` for other privileged config actions). The caller controls `creator`, token pair, init data, and `initialPrice`; the function creates the pool, initializes it, registers it in `AlgebraPoolAPIStorage` (`setDeployerForPair`), and configures fee/plugin settings.
- Impact: Any address can deploy and register custom CL pools with arbitrary initial pricing, front-running or poisoning the deployer's official pool for any pair. Those pools are then treated as registered by routing/API logic and may become gauge-eligible if tokens satisfy whitelist/connector requirements. Precondition: the deployer is registered as a custom deployer in `AlgebraPoolAPIStorage`.

## Payable `exactInput` traps ETH and performs no swap
*(consensus, 2 of 6 reports)*
- Location: contracts/GlobalRouter.sol : `exactInput`
- Mechanism: `exactInput` is `external payable` but its swap implementation is entirely commented out. It accepts `msg.value`, performs no swap, has no refund/withdrawal path, and returns the default `amountOut`.
- Impact: Users or integrations routing a v3 exact-input swap with ETH through `GlobalRouter.exactInput` lose that ETH permanently to the router. Precondition: caller sends ETH to `exactInput`.

---

## Minority findings

## `recoverERC20` can drain the BLACK reward token despite NatSpec
*(minority, 1 of 6 reports)*
- Location: contracts/BlackClaims.sol : `recoverERC20` (and contracts/RewardsDistributor.sol : `withdrawERC20`, same shape)
- Mechanism: NatSpec states "Cannot be called to withdraw emissions tokens," but the body has no such check: it reads `balanceOf(this)` for any `tokenAddress_` and transfers the full balance to the owner. The contract holds the season's BLACK rewards (pulled from treasury in `finalize`) that users claim via `claimAndStakeReward`. `RewardsDistributor.withdrawERC20` similarly can move the BLACK rebase balance to `owner` with no token exclusion.
- Impact: The owner can call `recoverERC20(BLACK)` and seize the entire pool of unclaimed season rewards out from under users, violating the documented invariant. Owner-only, but breaks a stated protection.
- Reviewer disagreement: none — no other report examined `BlackClaims`.

## Self-shadowing drops the bonus reward token on CL gauge creation
*(minority, 1 of 6 reports)*
- Location: contracts/GaugeManager.sol : `_createGauge` (`address bonusRewardToken = bonusRewardToken;`)
- Mechanism: Inside `_createGauge(address _pool, uint256 _gaugeType, address bonusRewardToken)` the line re-declares a local `bonusRewardToken` initialized from itself. Solidity brings the local into scope for its own initializer (the `T x = x;` footgun), so it resolves to the zero default rather than the parameter, shadowing the real argument for the rest of the function.
- Impact: For `createGaugeWithBonusReward(...)`, the intended bonus token is silently replaced by `address(0)` when forwarded to `createGauge(..., bonusRewardToken)` / `createEternalFarming`, so the eternal farming incentive is created with a zero bonus token and the second incentive can never be funded — the bonus-reward feature is dead. (The finder flags severity as contingent on the compiler binding the initializer to the new local.)
- Reviewer disagreement: none — other reports that touched `GaugeManager` only vouched for the `index`/`supplyIndex` emission accounting, not `_createGauge`'s bonus-token argument.

## ETH liquidity can initialize genesis pairs despite the genesis guard
*(minority, 1 of 6 reports)*
- Location: contracts/RouterV2.sol : `addLiquidityETH`
- Mechanism: `addLiquidity` blocks initial liquidity into genesis pairs with `require(!(isGenesis(pair) && totalSupply() == 0), "NA")`, but `addLiquidityETH` omits the same check. For native-token/WETH genesis pools, anyone can call `addLiquidityETH` before the official launch and become the first LP.
- Impact: An attacker can front-run or preemptively initialize a WETH genesis pair, set the initial pool ratio, and take the first LP tokens — corrupting genesis launch price/accounting and potentially capturing value when the genesis pool later adds protocol liquidity.
- Reviewer disagreement: none — no other report addressed the `addLiquidityETH` genesis guard gap.

## Router supporting-fee paths sweep unrelated balances
*(minority, 1 of 6 reports)*
- Location: contracts/RouterV2.sol : `swapExactTokensForETHSupportingFeeOnTransferTokens`, `removeLiquidityETHSupportingFeeOnTransferTokens`
- Mechanism: `swapExactTokensForETHSupportingFeeOnTransferTokens` withdraws and forwards the router's **entire** WETH balance, not just the current swap's output; `removeLiquidityETHSupportingFeeOnTransferTokens` transfers the router's **entire** balance of the removed token to `to`.
- Impact: Any WETH or supported token balance accidentally or transiently left in the router can be drained by executing a tiny compatible swap or liquidity removal. Precondition: the router holds stray token/WETH balance.
- Reviewer disagreement: none — no other report flagged these supporting-fee sweeps.

## Public mint cap can be bypassed by transferring NFTs away
*(minority, 1 of 6 reports)*
- Location: contracts/Thenian.sol : `mintPublic`
- Mechanism: The cap checks `balanceOf(msg.sender) + amount <= 15` but never tracks cumulative mints per address. A minter can transfer NFTs to another wallet and call `mintPublic` again with a low current balance.
- Impact: An attacker can exceed the intended 15-per-wallet public limit and mint repeatedly up to available supply, subject only to paying `NFT_PRICE`. Precondition: public sale active, supply remaining.
- Reviewer disagreement: none — no other report examined `Thenian`.

## Genesis pools can be reset over existing depositor state
*(minority, 1 of 6 reports)*
- Location: contracts/GenesisPoolManager.sol : `depositNativeToken`; contracts/GenesisPool.sol : `setGenesisPoolInfo`
- Mechanism: When a genesis pool already exists for a native token, `depositNativeToken` reuses it and calls `setGenesisPoolInfo` without checking current status. `setGenesisPoolInfo` overwrites `genesisInfo`, allocation fields, auction, and status, but does not clear prior `userDeposits`, `totalDeposits`, incentives, or launch state.
- Impact: A whitelisted malicious token owner can reset an active or failed genesis pool before users claim refunds, moving it out of `NOT_QUALIFIED` and carrying old funding deposits into new accounting. Precondition: attacker is the whitelisted token owner / has governance authority for that token.
- Reviewer disagreement: none — no other report addressed `setGenesisPoolInfo` re-initialization.

## Approved genesis launches can be dust-DoSed before first liquidity
*(minority, 1 of 6 reports)*
- Location: contracts/GenesisPoolManager.sol : `approveGenesisPool`; contracts/GenesisPool.sol : `launch`; contracts/RouterV2.sol : `_addLiquidity`, `quoteLiquidity`
- Mechanism: After approval the pair exists with no LP supply and genesis status blocks router-based first liquidity, but the pair still exposes `sync`. An attacker transfers dust of only one token directly to the pair and calls `sync`, setting one reserve nonzero and the other zero. Later `launch` calls router `_addLiquidity` → `quoteLiquidity`, which reverts because one reserve is zero.
- Impact: An attacker can block or delay a genesis launch with a dust transfer, potentially forcing manual intervention or failed launch timing. Precondition: the genesis pool is approved but not yet launched.
- Reviewer disagreement: none — no other report examined the post-approval `sync`/`quoteLiquidity` interaction.

---

### Merge reconciliation
- Distinct findings across all six inputs (by code path + root cause): **18**
- Findings in this output: **18** (11 consensus + 7 minority)
- No findings dropped; no findings invented. The Bribe-`getReward` AVM bug consolidates the "guard mismatch" and "unset `originalOwner` mapping" mechanisms (same code path, treated as one finding-with-compounding-cause by the report that surfaced both). The genesis LP rounding finding is retained as consensus despite two reports explicitly defending that path; that disagreement is recorded inline.

