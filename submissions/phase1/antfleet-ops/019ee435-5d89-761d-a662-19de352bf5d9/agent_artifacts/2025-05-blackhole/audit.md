# Audit: 2025-05-blackhole

I found the following genuine security-impacting issues in the supplied code.

## Bribe rewards can be sniped at epoch end
- Location: `contracts/Bribes.sol` : `notifyRewardAmount`, `earned`, `_writeCheckpoint`
- Mechanism: Bribe rewards are credited to `epochStart(block.timestamp)`, but `earned()` pays an epoch using the last vote checkpoint before `epoch + WEEK - 1`. Because checkpoints within the same epoch are overwritten, a voter can move voting weight to a bribe shortly before epoch end and receive rewards for the whole epoch, regardless of how long they supported that pool.
- Impact: Attackers can capture a disproportionate share of bribes by voting late, stealing rewards from voters who supported the pool for most of the epoch.

## Gauge emissions can be permanently stranded when total vote weight is zero
- Location: `contracts/GaugeManager.sol` : `notifyRewardAmount`; `contracts/MinterUpgradeable.sol` : `update_period`
- Mechanism: `MinterUpgradeable.update_period()` is permissionless and transfers gauge emissions to `GaugeManager.notifyRewardAmount()`. If `IVoter(voter).totalWeight()` is zero, `GaugeManager` receives the tokens but does not increase `index`, leaving those emissions unaccounted and undistributable.
- Impact: Anyone can trigger an epoch update while total vote weight is zero and strand that epoch’s gauge emissions inside `GaugeManager`.

## Batch rebase claims misroute expired AVM lock rewards
- Location: `contracts/RewardsDistributor.sol` : `claim_many`
- Mechanism: `claim()` handles AVM-owned expired locks by resolving the original owner through `avm.getOriginalOwner()`. `claim_many()` does not perform that AVM owner resolution and instead transfers expired-lock rewards to `ownerOf(tokenId)`, which is the `AutoVotingEscrow` contract.
- Impact: Anyone can batch-claim an expired AVM-owned lock and send the user’s rebase rewards to the AVM contract, where they appear unrecoverable.

## Genesis LP maturity lock does not apply to depositors
- Location: `contracts/GaugeV2.sol` : `depositsForGenesis`, `_withdraw`; `contracts/GenesisPool.sol` : `balanceOf`
- Mechanism: `depositsForGenesis()` sets `maturityTime` only for the token owner, but `GaugeV2._balanceOf()` includes `GenesisPool.balanceOf(account)` for every depositor. Depositors have default `maturityTime == 0`, so the maturity check in `_withdraw()` passes immediately.
- Impact: Funding-token depositors can withdraw their genesis LP share immediately after launch, bypassing the intended staking maturity and draining launch liquidity earlier than designed.

## Router swap output can be redirected or burned
- Location: `contracts/RouterV2.sol` : `_swap`, `swapExactTokensForTokensSimple`
- Mechanism: `_swap()` ignores the public function’s `to` parameter and sends each hop to `routes[i].receiver`. `swapExactTokensForTokensSimple()` creates a route but never initializes `receiver`, so swaps route output to `address(0)`. Other swap paths also trust caller-supplied receivers instead of enforcing the final `to`.
- Impact: Swap output can be sent to an attacker-controlled receiver or burned, while the caller-facing `to` parameter suggests funds should go elsewhere.

## Anyone can front-run official custom Algebra pool creation
- Location: `contracts/CustomPoolDeployer.sol` : `createCustomPool`
- Mechanism: `createCustomPool()` is external and has no `onlyOwner` or `onlyAuthorized` guard. The function creates and initializes the deployer’s custom Algebra pool, sets tick spacing/plugin/community fee settings, and registers the pool in `AlgebraPoolAPIStorage`.
- Impact: An attacker can preemptively create the canonical custom pool for a token pair with attacker-chosen initialization parameters, poisoning or blocking the intended pool deployment.

## CL gauge creation does not verify the pool belongs to the Algebra factory
- Location: `contracts/GaugeManager.sol` : `_createGauge`
- Mechanism: For `_gaugeType == 1`, the code sets `isPair = true` without checking the supplied pool against the Algebra factory or `AlgebraPoolAPIStorage`. It only reads `token0()` and `token1()` from the supplied contract before creating and registering a gauge.
- Impact: A malicious or unauthorized pool contract for whitelisted tokens can be registered as a CL gauge and become eligible for votes, bribes, and emissions.

## Reward token can be drained from the claims contract
- Location: `contracts/BlackClaims.sol` : `recoverERC20`
- Mechanism: `recoverERC20()` allows `owner` or `secondOwner` to withdraw any ERC20 held by the contract, including the reward token used for finalized user claims. The function’s comment says emissions tokens cannot be withdrawn, but no such restriction is enforced.
- Impact: A malicious or compromised owner can drain claimable BLACK rewards, causing user claims to fail or become unfunded.

## Public mint wallet cap can be bypassed by transferring NFTs away
- Location: `contracts/Thenian.sol` : `mintPublic`
- Mechanism: The public sale limit checks `balanceOf(msg.sender) + amount <= 15`. It does not track cumulative public mints. A minter can transfer NFTs out of the wallet and call `mintPublic()` again.
- Impact: An attacker can mint more than the intended per-wallet cap and monopolize supply during the public sale.

## Payable exact-input router function accepts funds but performs no swap
- Location: `contracts/GlobalRouter.sol` : `exactInput`
- Mechanism: `exactInput()` is payable and exposes a standard router-like interface, but the swap implementation is commented out. The function returns without transferring input tokens, executing a swap, refunding ETH, or enforcing `amountOutMinimum`.
- Impact: Users or integrations calling this function can send ETH to the router and receive no output, leaving funds stuck in the contract.

