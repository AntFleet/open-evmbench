# Audit: 2024-04-noya
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## MorphoBlue position TVL adds borrowed debt instead of subtracting it
*(consensus, 6 of 6 reports)*
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: Net lending value should be `supplied + collateral − debt`, but the code computes `_getValue(loanToken, base, supplyAmount + borrowAmount + convertCToL(collateral, ...))`, **adding** the outstanding debt (`borrowShares.toAssetsUp(...)`). Every sibling lending connector (Aave, Compound, Dolomite, Frax, Prisma, Gearbox, Silo) nets debt out; Morpho adds it. Worse, the borrowed `loanToken` is separately registered as a type‑0 holding via `_updateTokenInRegistry`, so the borrow is double‑counted, giving an error of ~`2 × borrowValue`.
- Impact: Any open Morpho borrow inflates `totalAssets()`/`TVL()`, which drives `previewDeposit`/`previewRedeem` and `getProfit`. Withdrawers redeem more than fair share (draining remaining holders), new depositors are under‑minted, and `recordProfitForFee` mints phantom performance‑fee shares.

## `onlyVaultMaintainer` uses `||` — requires maintainer AND emergency role
*(consensus, 4 of 6 reports)*
- Location: `contracts/accountingManager/Registry.sol` : `onlyVaultMaintainer`
- Mechanism: The guard reverts on `msg.sender != maintainer || hasRole(EMERGENCY_ROLE, msg.sender) == false`, so the pass condition is `maintainer && EMERGENCY_ROLE`. The two sibling modifiers (`onlyVaultMaintainerWithoutTimeLock`, `onlyVaultGoverner`) use `&&` in the revert, yielding the intended "role‑holder OR emergency" semantics — confirming this is a logic error.
- Impact: `addConnector`, `updateConnectorTrustedTokens`, and `removeTrustedPosition` become uncallable by the normal maintainer (a timelock without emergency role) and uncallable by emergency‑role holders. Unless one address holds both roles, connector/trusted‑position management and emergency override are permanently bricked (availability / incident‑response failure).

## Uniswap V3 position TVL reads pool‑aggregate liquidity of all NPM LPs, not the vault's tokenId
*(consensus, 4 of 6 reports)*
- Location: `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL` (inherited by `PancakeswapConnector`)
- Mechanism: The function decodes the vault `tokenId` but never uses it. It derives the pool key as `keccak256(abi.encodePacked(positionManager, tickLower, tickUpper))` and reads `pool.positions(key)`. In Uniswap V3 the pool keys positions by `(owner=NonfungiblePositionManager, tickLower, tickUpper)`, so this slot aggregates the liquidity of *every* NFT minted through the NPM in that tick range. The correct read is `positionManager.positions(tokenId).liquidity` (as used in `getCurrentLiquidity`). Amounts are then priced with `slot0()` spot.
- Impact: Any external LP can mint liquidity in the same pair/fee/tick range to inflate the vault's reported TVL by an unbounded amount. With inflated `totalAssets()`, a withdrawing shareholder can redeem far more than backed, draining the vault and shortchanging later depositors/withdrawers.

## Aerodrome position TVL ignores LP staked in the gauge
*(consensus, 4 of 6 reports)*
- Location: `contracts/connectors/AerodromeConnector.sol` : `_getPositionTVL` (interacting with `stake`/`unstake`/`withdraw`)
- Mechanism: TVL uses only `IERC20(pool).balanceOf(address(this))`. But `stake(pool, liquidity)` deposits the LP into `voter.gauges(pool)`, after which the direct LP balance is 0; the gauge balance (`IGauge(gauge).balanceOf(address(this))`) is never added. Unlike Curve/Balancer/Stargate connectors which sum staked balances. (Report A additionally notes `withdraw` de‑registers the holding position when direct balance hits 0, permanently orphaning the still‑staked LP from TVL.)
- Impact: While LP is staked, TVL is understated, so depositors mint excess shares cheaply and dilute existing holders; withdrawals during that window underpay. The de‑registration case permanently drops staked value from TVL until manually re‑added.

## First‑depositor / donation share inflation (no minSharesOut, no virtual offset)
*(consensus, 4 of 6 reports)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `TVL`/`totalAssets`, `deposit`, `calculateDepositShares`, `executeDeposit`
- Mechanism: `TVL()` adds raw `baseToken.balanceOf(this)` (minus only `depositQueue.totalAWFDeposit`), so a direct token donation inflates `totalAssets()` without minting shares. The vault uses default OZ ERC‑4626 with `_decimalsOffset() == 0` (single virtual‑asset buffer only). `deposit` accepts any nonzero amount with no `minSharesOut`, shares are calculated later via `previewDeposit(data.amount)`, and zero‑share results are still minted.
- Impact: An existing shareholder/griefer who donates before `calculateDepositShares` can make queued depositors' shares round toward zero for real assets, with the value accruing to the attacker's shares. Partially mitigated by the manager‑gated, time‑delayed calculation flow and `resetMiddle`, so exploitation requires the manager to calculate shares while NAV is manipulated.

## Underwater debt positions cause net‑TVL underflow revert (TVL DoS)
*(consensus, 3 of 6 reports)*
- Location: `AaveConnector._getPositionTVL`, `CompoundConnector._getPositionTVL`, `Dolomite._getPositionTVL`, `PrismaConnector._getPositionTVL`, `SiloConnector._getPositionTVL`
- Mechanism: These compute net value with an unchecked Solidity‑0.8 subtraction (`collateral − debt`) and do not clamp negative equity to zero. If debt value exceeds collateral — during sharp price moves, interest, liquidation, or oracle manipulation — the subtraction underflows and reverts. `FraxConnector._getPositionTVL` guards this (`if (collateral > borrow) ... else return 0`), highlighting that the others do not.
- Impact: A single underwater position makes `_getPositionTVL` revert, propagating through `TVLHelper.getTVL` → `AccountingManager.TVL()`. Every function reading `TVL()` (deposit, share calculations, profit/fee accounting, withdrawals) reverts — a global DoS exactly when the vault is most stressed.

## Camelot & Aerodrome LP valued from spot reserves (flash‑loan manipulable)
*(consensus, 2 of 6 reports)*
- Location: `contracts/connectors/CamelotConnector.sol` : `_getPositionTVL`; `contracts/connectors/AerodromeConnector.sol` : `_getPositionTVL`
- Mechanism: Both price the LP from instantaneous `getReserves()` combined with fixed per‑token oracle prices (`balance * (value(tokenA, r0) + value(tokenB, r1)) / totalSupply`). For a constant‑product pool, `p0·r0 + p1·r1` is minimized at balance and rises as reserves are skewed, so an attacker can swap (e.g. via flash loan) to inflate the reported LP value, then unwind. This is the classic non‑"fair‑LP" (no `sqrt(k)`) pricing flaw. (Report C notes Balancer's weight‑based valuation shares this class to a lesser degree.)
- Impact: `TVL()` is manipulable by anyone; an attacker who gets a deposit/withdraw/profit calculation to read the skewed state can move value between themselves and other depositors or inflate accrued fees.
- Reviewer disagreement: opus shot 2 explicitly defended this code path, treating spot‑reserve LP pricing as an accepted design trade‑off because the manager‑gated, time‑delayed share‑calculation flow prevents single‑transaction profit (1 of 6 defended).

## Holding‑position removal recomputes the index key from the wrong connector field
*(consensus, 2 of 6 reports)*
- Location: `contracts/accountingManager/Registry.sol` : `updateHoldingPosition` (swap‑and‑pop removal branch)
- Mechanism: The canonical `isPositionUsed` key is `keccak256(abi.encode(msg.sender, _positionId, _data))`, keyed on the owning connector (and `HoldingPI` stores that owner in field 1, with `calculatorConnector` in field 0). During swap‑and‑pop the moved element's key is recomputed from `holdingPositions[positionIndex].calculatorConnector` (field 0), not the owning connector. For `onlyOwner == false` trusted positions held by a connector different from the `calculatorConnector`, the two fields differ, so a bogus key is written.
- Impact: The moved position's real key keeps pointing at the freed/stale index while a never‑looked‑up key is set, desyncing `isPositionUsed`. Subsequent `getHoldingPositionIndex`/`updateHoldingPosition` return a wrong or zero index → duplicate pushes, exceeding `maxNumHoldingPositions`, double‑counting, silent drop from TVL, or out‑of‑bounds revert.

## Withdraw fulfillment trusts requested amounts instead of received assets
*(consensus, 2 of 6 reports)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `retrieveTokensForWithdraw` (consumed by `fulfillCurrentWithdrawGroup` / `executeWithdraw`)
- Mechanism: For each connector pull, the code sanity‑checks the balance delta against the connector‑reported `amount`, but accumulates the **requested** `retrieveData[i].withdrawAmount` into `amountAskedForWithdraw`. `fulfillCurrentWithdrawGroup` gates only on `amountAskedForWithdraw == currentWithdrawGroup.totalCBAmount`. A connector returning less than requested (`amount < withdrawAmount`) still passes the balance check while the group is marked fulfilled, and `fulfill` sets `totalABAmount = availableAssets` (< `totalCBAmountFullfilled`).
- Impact: In `executeWithdraw` each request's full `shares` are burned while only pro‑rated `data.amount * totalABAmount / totalCBAmountFullfilled` is paid; withdrawers are silently shortchanged and the unpaid value accrues to remaining holders. `totalWithdrawnAmount += processedBaseTokenAmount` adds calculated (not paid) amounts, double‑counting in `getProfit()` and inflating fees.

## Zero‑address deposit receiver permanently bricks the deposit queue
*(consensus, 2 of 6 reports)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit`, `executeDeposit`
- Mechanism: `deposit` does not reject `receiver == address(0)`. The request is appended to the FIFO queue, and `executeDeposit` later calls `_mint(data.receiver, data.shares)`; OZ ERC20 minting to `address(0)` reverts. Execution always starts at `depositQueue.first` with no skip/cancel path.
- Impact: Any user can spend a small base‑token deposit with `receiver = address(0)` to place an unexecutable head‑of‑line entry, permanently blocking execution of that deposit and all later deposits until administrative/code‑level recovery.

## Dolomite borrow sub‑accounts are never registered (TVL undercount)
*(consensus, 2 of 6 reports)*
- Location: `contracts/connectors/Dolomite.sol` : `openBorrowPosition` (also `transferBetweenAccounts`, `closeBorrowPosition`)
- Mechanism: `openBorrowPosition` calls `registry.updateHoldingPosition(..., abi.encode(accountId), "", true)` with `removePosition = true`, so opening a borrow sub‑account attempts a removal (no‑op) instead of registering it; `transferBetweenAccounts` registers nothing. `deposit` only tracks `accountId = 0`, and `_getPositionTVL` queries that single decoded account.
- Impact: Collateral moved into a borrow sub‑account leaves account 0 (lowering tracked balance) but the sub‑account is invisible to TVL, so NAV is understated while the position is open. Depositors during the understatement mint excess shares (diluting holders); the effect reverses on close.

## SNX debt omitted from TVL (and assigned collateral over‑counted)
*(consensus, 2 of 6 reports)*
- Location: `contracts/connectors/SNXConnector.sol` : `_getPositionTVL`, `mintOrBurnSUSD`
- Mechanism: `_getPositionTVL` values `totalDeposited + totalAssigned` collateral from `getAccountCollateral` and never subtracts the sUSD debt minted via `mintOrBurnSUSD`; the minted sUSD may additionally be tracked as a positive holding token via `_updateTokenInRegistry(usdToken)`. (Report F additionally argues `totalAssigned` is derived from deposited collateral and so is itself double‑counted.)
- Impact: SNX borrowing makes the vault report collateral plus borrowed assets while ignoring liabilities, inflating share price; shareholders can redeem at the inflated price and drain value from remaining users.

## Zero‑share / zero‑receiver withdrawal bricks the withdrawal queue
*(consensus, 2 of 6 reports)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `withdraw`, `calculateWithdrawShares`, `fulfillCurrentWithdrawGroup`, `executeWithdraw`
- Mechanism: `withdraw` requires no `share > 0` and does not reject `receiver == address(0)`. A zero‑share request needs no balance, calculates to `amount == 0`, and can produce a fulfilled group with `totalCBAmountFullfilled == 0`. `executeWithdraw` then either divides by zero in `data.amount * totalABAmount / totalCBAmountFullfilled`, or performs a zero‑value transfer to `address(0)` which reverts for standard ERC20s/USDC.
- Impact: Any address, even with no shares, can enqueue a malformed withdrawal at no capital cost that reverts on execution and blocks all later withdrawals in the FIFO queue from exiting.

## Minority findings

## `resetMiddle` for withdrawals does not roll back `currentWithdrawGroup.totalCBAmount`
*(minority, 1 of 6 reports)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `resetMiddle` (withdraw branch) interacting with `calculateWithdrawShares`
- Mechanism: `calculateWithdrawShares` accumulates `currentWithdrawGroup.totalCBAmount += assetsNeededForWithdraw` as it advances `withdrawQueue.middle`. `resetMiddle(newMiddle, false)` moves `middle` backward but never decrements `totalCBAmount`. The withdrawals between `newMiddle` and the old `middle` are recalculated and re‑added, double‑counting their assets. (Deposits have no analogous global accumulator, so only the withdraw path is affected.)
- Impact: `totalCBAmount` exceeds true assets owed. Since `fulfillCurrentWithdrawGroup` requires `amountAskedForWithdraw == totalCBAmount`, the group either can never be fulfilled (withdrawal DoS) or the manager over‑retrieves (surplus stranded). If fulfilled with `availableAssets < inflated totalCBAmount`, the inflated `totalCBAmountFullfilled` denominator under‑pays every user in the group. The intended manipulation defense thereby corrupts withdraw accounting.

## Sibling role modifiers (`onlyVaultMaintainerWithoutTimeLock`, `onlyVaultGoverner`) also require two authorities at once
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `contracts/accountingManager/Registry.sol` : `onlyVaultMaintainerWithoutTimeLock`, `onlyVaultGoverner`
- Mechanism: This report reads all three vault role modifiers as using `if (msg.sender != vaultRole || hasRole(EMERGENCY_ROLE, msg.sender) == false) revert`, requiring the caller to be both the vault‑specific role and a global emergency‑role holder simultaneously.
- Impact: Unless one address is granted both roles, governance/maintenance paths gated by these modifiers (e.g. changing vault addresses, adding connectors/trusted positions) are bricked, preventing normal upgrades and emergency response.
- Reviewer disagreement: opus shots 1, 2, and 3 each examined these two modifiers and explicitly stated they correctly use `&&` (i.e. "maintainer OR emergency"), citing them as proof that only `onlyVaultMaintainer` is the bug.

## Maverick partial removal can delete a still‑live position from accounting
*(minority, 1 of 6 reports)*
- Location: `contracts/connectors/MaverickConnector.sol` : `removeLiquidityFromMaverickPool`
- Mechanism: After any liquidity removal the function unconditionally calls `registry.updateHoldingPosition(..., true)` (remove) for the pool position, without checking whether the connector still owns other Maverick liquidity/NFTs in that pool. `_getPositionTVL` values all token IDs owned by the connector for the pool.
- Impact: Remaining Maverick liquidity disappears from registry TVL after a partial removal, letting new depositors mint shares too cheaply and dilute existing holders (precondition: connector retains liquidity in the pool beyond the removed portion).

## Pendle Penpie‑staked LP can be removed from the registry while still owned
*(minority, 1 of 6 reports)*
- Location: `contracts/connectors/PendleConnector.sol` : `decreasePosition`, `isMarketEmpty`
- Mechanism: `isMarketEmpty` checks only local SY/PT/YT and local market LP balances, ignoring LP deposited in Penpie via `pendleMarketDepositHelper.balance`. `decreasePosition(..., closePosition=true)` can therefore remove the registry position while Penpie‑staked LP still exists and would otherwise be counted by `_getPositionTVL`.
- Impact: TVL is understated after a close‑position call, allowing subsequent depositors to mint excess shares (precondition: Pendle LP remains staked in Penpie at close).

## Zero‑share withdrawal requests can clog the FIFO withdrawal queue (gas backlog)
*(minority, 1 of 6 reports)*
- Location: `contracts/accountingManager/AccountingManager.sol` : `withdraw`
- Mechanism: `withdraw(uint256 share, address receiver)` does not reject `share == 0`. Any address can cheaply append arbitrarily many zero‑share requests to `withdrawQueue`, which the manager must iterate through in FIFO order in `calculateWithdrawShares` and `executeWithdraw` before reaching real withdrawals.
- Impact: An attacker can create an arbitrarily large withdrawal backlog at near‑zero cost, increasing keeper/manager gas and delaying or practically blocking legitimate withdrawals (distinct from the zero‑receiver revert‑brick: this is a gas/backlog griefing vector requiring no zero receiver).

---

*Reconciliation: 18 distinct findings identified across the 6 input reports (by code path + root cause); 18 findings emitted (13 consensus, 5 minority). No findings dropped.*

