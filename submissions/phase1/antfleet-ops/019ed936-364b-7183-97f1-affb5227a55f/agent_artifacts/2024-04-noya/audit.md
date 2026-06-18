# Audit: 2024-04-noya

## Consensus findings

## Morpho Blue position TVL adds debt instead of subtracting it
*(consensus)*
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL line computes `tvl = _getValue(params.loanToken, base, supplyAmount + borrowAmount + convertCToL(pos.collateral, ...))`, i.e. it *adds* `borrowAmount` (the loan-token debt owed). Net asset value for a lending position is `supply + collateral − debt`; every other lending connector correctly subtracts debt (Aave `totalCollateralBase - totalDebtBase`, Compound `positiveBalance - negativeBalance`, Dolomite `totalCollateral - totalDebt`, Frax `collateralValue - borrowValue`, Gearboxv3 `totalValueUSD - totalDebtUSD`, Prisma `collateral - debt`, Silo `totalDepositAmount - totalBAmount`). The borrowed loan tokens are also credited a second time as a normal held-token position (the connector calls `_updateTokenInRegistry(market.loanToken)` after borrowing), so the position is overvalued by ~`2 × borrowAmount`.
- Impact: Whenever the vault holds a borrow position on Morpho Blue, `TVL()`/`totalAssets()` is massively overstated, corrupting the ERC-4626 share price used by `previewDeposit`/`previewRedeem` in `calculateDepositShares`/`calculateWithdrawShares` and inflating `getProfit()` (hence the performance fee). A redeemer can extract more base token than owed, draining real assets from later depositors and remaining shareholders. Deterministic NAV corruption, not a rounding edge case.

## Uniswap V3 TVL reads the position manager’s aggregate liquidity, not the vault’s NFT
*(consensus)*
- Location: `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL`
- Mechanism: The function computes `bytes32 key = keccak256(abi.encodePacked(positionManager, tL, tU)); (uint128 liquidity,,, uint128 tokensOwed0, uint128 tokensOwed1) = pool.positions(key);`. In Uniswap V3 all NFT-backed liquidity minted through the `NonfungiblePositionManager` is owned in the core pool under the single `positionManager` address, with positions keyed by `keccak256(owner, tickLower, tickUpper)`. This key therefore returns the *sum of every LP’s liquidity* in that tick range routed through the NFPM, not the vault’s `tokenId`. The decoded `tokenId` is never used for the value computation; the correct source is `positionManager.positions(tokenId)` (already used by `getCurrentLiquidity` elsewhere in the same contract). `PancakeswapConnector` inherits the same TVL logic.
- Impact: A vault holding a tiny NFT in a popular range is credited with unrelated third-party liquidity and fees, overstating the position (often by orders of magnitude). This propagates into `TVL()`/share pricing and `getProfit()`/performance-fee accounting, letting shareholders withdraw against assets the vault does not own and inflating fees.

## Registry vault role modifier uses `||` instead of `&&`, requiring two roles instead of either
*(consensus)*
- Location: `contracts/accountingManager/Registry.sol` : `onlyVaultMaintainer`
- Mechanism: The modifier is `if (msg.sender != vaults[_vaultId].maintainer || hasRole(EMERGENCY_ROLE, msg.sender) == false) revert;`. De-Morgan’d, the call is *allowed* only when `msg.sender == maintainer` **AND** `msg.sender` holds `EMERGENCY_ROLE`, inverting the intended “maintainer OR emergency” into “maintainer AND emergency”. The fix is `&&` in the revert condition. (Scope disagreement between reviewers: Reviewer A states only `onlyVaultMaintainer` is affected and that the sibling modifiers `onlyVaultMaintainerWithoutTimeLock` and `onlyVaultGoverner` correctly use `&&`; Reviewer B states all three modifiers share the `||` bug — including `onlyVaultMaintainerWithoutTimeLock` and `onlyVaultGoverner` and the vault-address-change path. The shared, confirmed locus is `onlyVaultMaintainer`.)
- Impact: With a normal deployment (separate maintainer and emergency addresses), the guarded functions — `addConnector`, `updateConnectorTrustedTokens`, `removeTrustedPosition` (per Reviewer B also vault-address changes) — become permanently uncallable, and the emergency role loses its intended override. This bricks connector enable/disable, trusted-token configuration, and trusted-position removal, including the ability to remove a dangerous connector or position during an incident.

## Additional findings (single-reviewer)

## Missing zero-address validation on deposit/withdraw recipients permanently bricks the queues
*(Reviewer A only)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit` (stores `receiver` unchecked) → `executeDeposit` (`_mint(data.receiver, data.shares)`); and `withdraw` (stores `receiver` unchecked) → `executeWithdraw` (`baseToken.safeTransfer(data.receiver, baseTokenAmount)`)
- Mechanism: `deposit(address receiver, ...)` and `withdraw(uint256 share, address receiver)` never validate `receiver != address(0)`. Requests are processed strictly FIFO; `executeDeposit`/`executeWithdraw` advance `depositQueue.first`/`withdrawQueue.first` only on successful processing and have no skip mechanism. `_mint` reverts on a zero recipient (OZ `ERC20InvalidReceiver`) and `baseToken.safeTransfer` reverts on a zero recipient for standard ERC-20s. `resetMiddle` only moves the `middle` index (used for share *calculation*), not `first`, so it cannot skip a poisoned entry.
- Impact: An attacker submits a `deposit` (or `withdraw`, after acquiring shares) with `receiver = address(0)`. Once it reaches the head of the execution range, processing reverts on every call and never makes progress, freezing all subsequent deposits/withdrawals (and already-transferred funds) with no recovery short of a contract upgrade. Cost to the attacker is only their own deposit — a cheap, permanent DoS of the core vault flows.

## LP TVL valued from spot AMM reserves is flash-loan manipulable
*(Reviewer A only)*
- Location: `contracts/connectors/CamelotConnector.sol` : `_getPositionTVL` (`balanceThis * (_getValue(tokenA, base, reserves0) + _getValue(tokenB, base, reserves1)) / totalSupply`) and `contracts/connectors/AerodromeConnector.sol` : `_getPositionTVL` (`amount0 = balance * reserve0 / totalSupply; ...` then `_getValue(...)`)
- Mechanism: Both connectors value an LP position as the pro-rata share of the pool’s *current* reserves priced at the oracle. For a constant-product pool, `reserve0·p0 + reserve1·p1` is minimized at the balanced point and grows as the pool is pushed off-balance, while `getReserves()` reflects instantaneous, swappable state. An attacker can flash-borrow, skew reserves, and the computed LP value rises even though the true redeemable value (bounded by the invariant `k`) does not. A fair-value method would derive reserves from the invariant and oracle prices, not from spot reserves.
- Impact: If a share calculation (`calculateDepositShares`/`calculateWithdrawShares` → `previewDeposit`/`previewRedeem` → `TVL()`) runs while the pool is manipulated, an attacker can move the vault’s NAV within a single transaction to mint excess shares or redeem excess assets. Exploitability is bounded by the manager controlling calculation timing and by `resetMiddle`, but the valuation primitive itself is manipulable and should use a manipulation-resistant LP price.

## Partial withdraw fills overstate `totalWithdrawnAmount`, inflating profit and the performance fee
*(Reviewer A only)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `executeWithdraw` (`processedBaseTokenAmount += data.amount;` then `totalWithdrawnAmount += processedBaseTokenAmount;`)
- Mechanism: Each request pays out `baseTokenAmount = data.amount * totalABAmount / totalCBAmountFullfilled`, i.e. only a fraction when the group is partially fulfilled (`fulfillCurrentWithdrawGroup` sets `totalABAmount = availableAssets < totalCBAmount` when connectors return less than `amountAskedForWithdraw`). But `totalWithdrawnAmount` is incremented by the *full* `data.amount`, not the fraction actually transferred. Because the unpaid portion also remains inside the vault (still counted in `TVL()`), `getProfit() = TVL + totalWithdrawnAmount − totalDepositedAmount` double-counts the shortfall.
- Impact: In any partial-fill withdrawal the recorded profit is overstated by roughly the unpaid amount, then converted to extra performance-fee shares in `recordProfitForFee`/`collectPerformanceFees`. Additionally, affected users’ shares are fully burned while they receive only the partial amount, with no re-queue of the remainder — a silent loss to those withdrawers.

## Direct base-token transfers are immediately counted as TVL (donation / first-depositor surface)
*(Reviewer A only)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `TVL()` (`... + baseToken.balanceOf(address(this)) - depositQueue.totalAWFDeposit`)
- Mechanism: `TVL()` credits the entire idle `baseToken` balance (minus queued, not-yet-executed deposits) to the vault. Any base token sent directly to the contract — not via `deposit`, so untracked in `depositQueue.totalAWFDeposit` — instantly raises `totalAssets()` and the share price. Combined with a small first deposit and the default OZ v5 ERC-4626 share scaling (no `_decimalsOffset` override), a donation can round subsequent depositors’ `previewDeposit` shares down.
- Impact: An attacker can inflate per-share value via a donation so a later depositor (shares computed in `calculateDepositShares`) receives fewer shares than fair, then redeem at the inflated price. Manager-controlled calculation timing and `resetMiddle` are the intended mitigations, so exploitation requires the manager to calculate shares while the balance is manipulated; nonetheless the raw accounting treats unsolicited balances as profit and should be reconciled against an explicitly tracked accounted balance.

## Zero-share withdrawals can indefinitely clog the withdrawal queue
*(Reviewer B only)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `withdraw(uint256 share, address receiver)`
- Mechanism: `withdraw` does not reject `share == 0`. A caller with no shares passes `balanceOf(msg.sender) < share + withdrawRequestsByAddress[msg.sender]`, creates a `WithdrawRequest` with zero shares, and increments `withdrawQueue.last`. The manager-side `calculateWithdrawShares` and `executeWithdraw` loops must still process these entries in FIFO order.
- Impact: Any address can spam unlimited zero-share withdrawal requests, forcing managers to spend gas processing worthless entries before real withdrawals progress. Because queue processing is bounded by `maxIterations`, this can delay or practically DoS withdrawals.

## Aerodrome staked LP tokens are omitted from TVL
*(Reviewer B only)*
- Location: `contracts/connectors/AerodromeConnector.sol` : `stake`, `_getPositionTVL`
- Mechanism: `stake` deposits LP tokens into a gauge, but `_getPositionTVL` only values `IERC20(pool).balanceOf(address(this))`. It does not include `IGauge(gauge).balanceOf(address(this))`, so staked LP tokens disappear from accounting while the holding position remains active.
- Impact: After LP is staked, vault TVL is understated. Attackers can deposit while shares are underpriced, then profit when the LP is unstaked or otherwise becomes counted again, diluting existing shareholders.

## Maverick partial LP removal deletes accounting for remaining liquidity
*(Reviewer B only)*
- Location: `contracts/connectors/MaverickConnector.sol` : `removeLiquidityFromMaverickPool`
- Mechanism: The connector removes the registry holding position unconditionally after removing liquidity for one `tokenId`. `_getPositionTVL` values all Maverick NFTs held by the connector for that pool, so if more NFTs or bins remain, deleting the holding position excludes the remaining liquidity from TVL.
- Impact: A partial withdrawal can make live Maverick liquidity invisible to accounting. Depositors can mint shares at an artificially low price until the position is re-added, extracting value from existing shareholders.

## Insolvent lending positions can brick vault accounting through underflow
*(Reviewer B only)*
- Location: `contracts/connectors/AaveConnector.sol` : `_getPositionTVL`; `contracts/connectors/CompoundConnector.sol` : `_getPositionTVL`; `contracts/connectors/Dolomite.sol` : `_getPositionTVL`; `contracts/connectors/PrismaConnector.sol` : `_getPositionTVL`; `contracts/connectors/SiloConnector.sol` : `_getPositionTVL`
- Mechanism: These TVL functions subtract debt from collateral using checked unsigned arithmetic (e.g. `totalCollateralBase - totalDebtBase`, `totalDepositAmount - totalBAmount`) without capping negative equity at zero. If market movement, oracle movement, interest accrual, or liquidation loss makes debt exceed collateral, the subtraction underflows and the view reverts.
- Impact: A single underwater position can make `TVL()`/`totalAssets()` revert, blocking deposits, share calculations, withdrawals, and fee accounting across the vault. Preconditions are any debt position becoming net negative, including through normal market movement or oracle manipulation.

