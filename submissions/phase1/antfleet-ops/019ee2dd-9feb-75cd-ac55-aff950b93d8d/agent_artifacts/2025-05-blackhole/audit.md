# Audit: 2025-05-blackhole

 ## Unrestricted CL gauge creation in GaugeFactoryCL
- **Location:** `contracts/AlgebraCLVe33/GaugeFactoryCL.sol:createGauge`
- **Mechanism:** `createGauge` is `external` and has no authorization check. It deploys a `GaugeCL` and immediately calls `createEternalFarming`, which pulls reward tokens from the factory into Algebra’s eternal-farming contract. A whitelisted path through `GaugeManager` is expected, but the factory function itself is unprotected.
- **Impact:** Anyone can create gauges/incentives for arbitrary pools. If the factory holds reward tokens, an attacker can drain them 1e10-at-a-time into useless incentives, and the factory’s `__gauges` list can be polluted with attacker-controlled entries.

## GaugeManager never validates CL pool addresses
- **Location:** `contracts/GaugeManager.sol:_createGauge`
- **Mechanism:** For `_gaugeType == 1` the code simply sets `isPair = true` without querying the registered Algebra CL factory or verifying that `_pool` is a real Algebra pool. It only reads `token0()`/`token1()` and checks token whitelisting. A malicious contract that implements those two functions can pass all checks.
- **Impact:** An attacker can register a gauge for a fake CL pool whose tokens are whitelisted, then vote for it and receive real weekly emissions through `_distribute`/`notifyRewardAmount`.

## CustomPoolDeployer.createCustomPool lacks access control
- **Location:** `contracts/CustomPoolDeployer.sol:createCustomPool`
- **Mechanism:** Every other privileged operation on the deployer uses `onlyAuthorized`, but `createCustomPool` is `external` with no modifier. It calls the Algebra entry point and registers the new pool in `AlgebraPoolAPIStorage` via `setDeployerForPair`.
- **Impact:** Arbitrary users can deploy custom Algebra pools using this deployer’s plugin, fee recipient, and fee-share settings. Combined with the missing CL-pool validation above, this allows unauthorized pools to be promoted to gauges.

## Zero slippage protection on concentrated-liquidity swaps
- **Location:** `contracts/RouterV2.sol:_swap` (called by `swapExactTokensForTokensSimple`, `swapExactTokensForTokens`, `swapExactETHForTokens`, `swapExactTokensForETH`)
- **Mechanism:** For concentrated routes the router constructs `ISwapRouter.ExactInputSingleParams` with `amountOutMinimum: 0`. The user-provided `amountOutMin` is never passed into the Algebra swap.
- **Impact:** All CL swaps are fully exposed to sandwich attacks and frontrunning; a malicious validator or MEV bot can force users to receive arbitrarily little output.

## RouterV2.addLiquidityETH bypasses genesis-pair restriction
- **Location:** `contracts/RouterV2.sol:addLiquidityETH`
- **Mechanism:** `addLiquidity` contains `require(!(IBaseV1Factory(factory).isGenesis(pair) && IBaseV1Pair(pair).totalSupply() == 0), "NA")` to prevent anyone but the GenesisPool from seeding a genesis pair. `addLiquidityETH` performs the same mint path without this check.
- **Impact:** An attacker can provide initial liquidity to a WETH/genesis-token pair before the GenesisPool launches, breaking the launch mechanics and potentially creating a mispriced pair.

## Broken zero-address check in GaugeCL/GaugeV2.setInternalBribe
- **Location:** `contracts/AlgebraCLVe33/GaugeCL.sol:setInternalBribe` and `contracts/GaugeV2.sol:setInternalBribe`
- **Mechanism:** Both functions use `require(_int >= address(0), "zero")`, which is a tautology because `address(0)` is the minimum possible address. The intended check is `!= address(0)`.
- **Impact:** The owner can accidentally set `internal_bribe` to the zero address, causing `_claimFees` to revert when it tries to `safeApprove` and `notifyRewardAmount` to address(0), permanently bricking fee distribution for that gauge.

## Infinite loop in TradeHelper.getAmountsIn
- **Location:** `contracts/APIHelper/TradeHelper.sol:getAmountsIn`
- **Mechanism:** The loop `for (uint i = routes.length-1; i >= 0; i--)` uses an unsigned integer, so `i >= 0` is always true. When `i` decrements past zero it underflows to `2^256-1` and the loop never terminates.
- **Impact:** Every call to `getAmountsIn` runs out of gas; any downstream contract or UI relying on amount-in estimates is DoSed.

## RewardsDistributor.claim_many ignores AVM original owners
- **Location:** `contracts/RewardsDistributor.sol:claim_many`
- **Mechanism:** For expired locks the function sends rewards to `ownerOf(_tokenId)`. Unlike the single-token `claim` function, it never checks `avm.tokenIdToAVMId` or redirects to `avm.getOriginalOwner`.
- **Impact:** Rebase rewards for AVM-held expired locks are sent to the AVM contract address instead of the original owner, locking those funds with no recovery path.

## BlackGovernor clock and proposalThreshold are unimplemented
- **Location:** `contracts/BlackGovernor.sol:clock`, `CLOCK_MODE`, and `proposalThreshold`
- **Mechanism:** `clock()` has an empty body and returns `0`; `CLOCK_MODE()` returns an empty string; `proposalThreshold` passes the current `block.timestamp` to `token.getPastTotalSupply`, which expects a past timestamp/clock value.
- **Impact:** Time-based governance snapshots, voting delays/periods, quorum, and proposal thresholds are broken. Proposals may always revert, or, depending on the underlying L2 governor, may be created and passed with zero supply/quorum.

## GlobalRouter.exactInput is an empty payable function that traps ETH
- **Location:** `contracts/GlobalRouter.sol:exactInput`
- **Mechanism:** The function is declared `external payable` but its body is empty (the implementation is commented out). It has no deadline check, no swap logic, and the contract has no ETH withdrawal function.
- **Impact:** Any ETH sent to `exactInput` is permanently stuck in the contract.

## Inverted zero-address check in GenesisPoolManager.setRouter
- **Location:** `contracts/GenesisPoolManager.sol:setRouter`
- **Mechanism:** The requirement is `require(_router == address(0), "ZA")`, meaning the function only accepts the zero address. It should reject the zero address.
- **Impact:** The owner cannot update the router to a valid address, and a call with `address(0)` would brick future `launch` calls that depend on the router.

## RewardsDistributor owner withdrawal can brick checkpoint_token
- **Location:** `contracts/RewardsDistributor.sol:withdrawERC20` and `checkpoint_token`
- **Mechanism:** `withdrawERC20` lets the owner pull any ERC20, but it does not update `token_last_balance`. `checkpoint_token` later computes `token_balance - token_last_balance`; if the owner withdrew reward tokens, `token_balance` is now lower and the subtraction underflows.
- **Impact:** A reward-token withdrawal disables the weekly checkpoint mechanism, breaking all subsequent rebase claims until the shortfall is manually replenished.

## PermissionsRegistry.removeRole corrupts role accounting
- **Location:** `contracts/PermissionsRegistry.sol:removeRole`
- **Mechanism:** After the role is removed from `_roles`, the inner cleanup loop assigns `_roles[_roles.length - 1]` (which now points to a different role) into `_addressToRoles[rta[i]][k]` for addresses that had the removed role.
- **Impact:** The `_addressToRoles` bookkeeping becomes corrupted, so the registry may misreport which roles an address holds and access-control decisions can become unreliable.

## API bribe helpers revert on unset bribe addresses
- **Location:** `contracts/APIHelper/AlgebraPoolAPI.sol:_getBribes`, `contracts/APIHelper/BlackholePairAPIV2.sol:_getBribes`, `contracts/APIHelper/RewardAPI.sol:getPairBribe`
- **Mechanism:** These functions read a gauge’s external/internal bribe address from `gaugeManager` and pass it to `_getNextEpochRewards` without checking for `address(0)`. `_getNextEpochRewards` then calls `IBribeAPI(address(0)).rewardsListLength()`, which reverts.
- **Impact:** Batch view functions revert for any pool whose gauge has not been fully configured with bribes, breaking off-chain aggregators and UIs.
