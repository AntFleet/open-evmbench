# Audit: 2025-05-blackhole

I found these genuine security issues.

## Genesis liquidity can be launched at an attacker-chosen price
- Location: `contracts/GenesisPool.sol` : `_addLiquidityAndDistribute`
- Mechanism: Genesis launch deposits liquidity through the router with `amountAMin = 0` and `amountBMin = 0`, assuming the pair is still empty. But `Pair.mint()` is public, and `RouterV2.addLiquidityETH()` does not block genesis pairs, so an attacker can pre-seed the genesis pair with arbitrary reserves before launch. The launch then adds the protocol’s genesis liquidity at that manipulated ratio.
- Impact: An attacker can force the genesis pool to launch at a bad price, then arbitrage or withdraw value from the protocol-funded liquidity.

## Genesis LP withdrawals can drain gauge liquidity through rounding
- Location: `contracts/GaugeV2.sol` : `_withdraw`, `_deductBalance`; `contracts/GenesisPool.sol` : `deductAmount`
- Mechanism: Withdrawals from genesis-backed gauges reduce the gauge LP balance immediately, but the corresponding genesis deposit is reduced using floor division: `userAmount = totalDeposits * gaugeTokenAmount / depositerLiquidity`. For very small LP withdrawals this rounds to zero, leaving the user’s genesis accounting unchanged while LP tokens are transferred out.
- Impact: A depositor can repeatedly withdraw tiny LP amounts that do not reduce their recorded deposit, draining LP tokens backing other users.

## AVM bribe rewards are sent to custody contracts and become stuck
- Location: `contracts/Bribes.sol` : `getReward`; `contracts/AVM/AutoVotingEscrowManager.sol` : `enableAutoVoting`
- Mechanism: Auto-voted veNFTs are transferred into child `AutoVotingEscrow` custody contracts. `Bribes.getReward()` sends rewards to `IVotingEscrow.ownerOf(tokenId)`, which is the child custody contract, unless the owner equals the AVM manager address. That condition does not match child AVM custody contracts, and the child contracts have no ERC20 recovery path.
- Impact: Bribe rewards for auto-voted locks can be permanently stranded in custody contracts instead of reaching the original lock owner.

## Batched rebase claims strand expired AVM lock rewards
- Location: `contracts/RewardsDistributor.sol` : `claim_many`
- Mechanism: `claim()` correctly special-cases AVM-held expired locks by resolving the original owner through the AVM manager. `claim_many()` omits that logic and transfers expired-lock rewards to `IVotingEscrow.ownerOf(tokenId)`, which is the child `AutoVotingEscrow` custody contract for auto-voted locks.
- Impact: Anyone can call `claim_many()` on expired AVM-held locks and strand the user’s rebase rewards in the custody contract.

## CL gauge reward leftovers are discarded on overlapping distributions
- Location: `contracts/AlgebraCLVe33/GaugeCL.sol` : `notifyRewardAmount`
- Mechanism: `notifyRewardAmount()` declares a named return variable `rewardRate` that shadows the state variable `rewardRate`. In the overlapping-period branch, `leftover = remaining * rewardRate` uses the uninitialized local value, so leftover rewards from the previous period are treated as zero and are not rolled into the new rate.
- Impact: Concentrated-liquidity stakers can receive less than the allocated emissions, with rewards left unscheduled or stuck in gauge/farming accounting.

## Simple concentrated swaps can route output to `address(0)`
- Location: `contracts/RouterV2.sol` : `swapExactTokensForTokensSimple`, `_swap`
- Mechanism: For `concentrated = true`, `swapExactTokensForTokensSimple()` creates a one-hop route but never sets `routes[0].pair` or `routes[0].receiver`. `_swap()` then uses `pairToDeployer(routes[i].pair)` and sends Algebra swap output to `routes[i].receiver`, which is zero instead of the user-provided `to`.
- Impact: Concentrated simple swaps can revert unexpectedly or send swap output to `address(0)`, causing user fund loss when routed through this function.

## Public mint wallet cap is bypassable
- Location: `contracts/Thenian.sol` : `mintPublic`
- Mechanism: The public mint cap checks `balanceOf(msg.sender) + amount <= 15`, which limits only current holdings, not cumulative mints. A user can mint, transfer NFTs away, and mint again.
- Impact: A single actor can exceed the intended per-wallet public sale cap and acquire more NFTs than allowed.

