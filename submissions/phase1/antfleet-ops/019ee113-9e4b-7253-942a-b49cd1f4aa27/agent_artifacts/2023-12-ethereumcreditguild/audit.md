# Audit: 2023-12-ethereumcreditguild

# Security Audit Report

## Loss Exceeding Total CREDIT Supply Causes DoS
- **Location:** `src/governance/ProfitManager.sol` : `notifyPnL`
- **Mechanism:** When a loss is reported that exceeds the surplus buffer, the function attempts to update the `creditMultiplier` via `creditTotalSupply - loss`. If `loss` (after subtracting the surplus buffer) is greater than the current `creditTotalSupply`, this subtraction underflows. Since Solidity 0.8+ checks for arithmetic underflow, the entire transaction reverts. This can occur if multiple lending terms default simultaneously or if a single term suffers a catastrophic loss exceeding the entire protocol's credit supply. Because `notifyPnL` is the only way to record losses, a revert here permanently blocks loss reporting for that gauge.
- **Impact:** A sufficiently large loss (or the accumulation of several losses across gauges) bricks loss reporting, leaving the system in an inconsistent state where bad debt exists on-chain but is not reflected in the `creditMultiplier` or the `surplusBuffer`. This can lead to under-collateralized loans that the system cannot liquidate properly, and prevents the GUILD loss mechanism from being triggered.

## `assert` in `state()` Consumes All Gas on Failure
- **Location:** `src/governance/GuildVetoGovernor.sol` : `state`
- **Mechanism:** The function contains `assert(queueid != bytes32(0))`. In Solidity ≥0.8, `assert` failures trigger the `Panic(0x01)` error which consumes all remaining gas. While `createVeto` is designed to always set `_timelockIds`, any code path that calls `state()` with a proposal ID lacking a mapping (e.g., direct calls to `executeVeto` with a crafted or never-proposed `timelockId`, or internal calls during proposal lifecycle operations) will hit this branch. Since `Governor.execute()` calls `state()` internally, such a call would revert with an out-of-gas error rather than a clean revert, making it impossible to distinguish or handle gracefully.
- **Impact:** Denial-of-service vector for the veto governor. Any attempt to execute or query the state of a non-existent or malformed veto proposal consumes the entire gas allowance of the transaction, potentially bricking integrators that rely on `state()` calls (e.g., UIs or keeper bots).

## Profit Index Manipulation via Gauge Weight Changes
- **Location:** `src/governance/ProfitManager.sol` : `notifyPnL`
- **Mechanism:** When profit is distributed via `notifyPnL`, the `gaugeProfitIndex` is updated using the *current* `getGaugeWeight(gauge)` at the time of the call. There is no snapshot mechanism. An attacker observing a pending large profit distribution (e.g., from a successful auction or interest payment) can front-run the transaction by voting with a large amount of GUILD on that gauge, claim the proportionally larger reward, and then unvote in a follow-up transaction. This dilutes the share of passive, long-term voters.
- **Impact:** Systematic theft of GUILD staking rewards from passive voters by MEV bots or sophisticated users. The profit distribution is not fairly allocated to genuine supporters of the gauge but to those who can front-run the `notifyPnL` call.

## Quorum of 0 Enables Instant Offboarding
- **Location:** `src/governance/LendingTermOffboarding.sol` : `setQuorum` / `supportOffboard`
- **Mechanism:** The offboarding quorum can be set to 0 by any address with the `GOVERNOR` role. When `quorum == 0`, the check `if (_weight + userWeight >= quorum)` in `supportOffboard` evaluates to true on the very first support (since the poll is initialized with weight 1 in `proposeOffboard`). This immediately sets `canOffboard[term] = true` for any term, allowing instant offboarding with the absolute minimum GUILD holding. Even without admin action, a very low quorum (e.g., 1 wei) combined with flash-loaned or temporarily acquired GUILD could trigger offboarding.
- **Impact:** A holder of even 1 wei of GUILD (or a flash-loan of GUILD) can immediately set the offboarding flag for any active lending term if the quorum is set low or to 0, allowing griefing attacks or forcing terms out of the system without genuine consensus.

## Rounding Errors in SimplePSM Can Cause Loss of Value
- **Location:** `src/loan/SimplePSM.sol` : `getMintAmountOut` / `getRedeemAmountOut`
- **Mechanism:** The PSM uses `decimalCorrection` (10^(18 - pegDecimals)) to scale between different token decimals. For tokens with low decimals (e.g., USDC with 6 decimals, `decimalCorrection = 1e12`), small input amounts can round down to 0 in the output calculation. For example, minting with an `amountIn` that results in `amountIn * 1e12 * 1e18 / creditMultiplier < 0.5` will round to 0. The user transfers peg tokens to the contract but receives 0 CREDIT, with no revert. A user might also receive 0 peg tokens on redeem if `amountIn * creditMultiplier / 1e18 / decimalCorrection < 0.5`.
- **Impact:** Loss of user funds on small transactions. A user depositing peg tokens when the computed output rounds to 0 will lose their entire input, as the contract retains the peg tokens (increasing `pegTokenBalance`) but issues no CREDIT.

## GOVERNOR Role is Its Own Admin Without Two-Step Transfer
- **Location:** `src/core/Core.sol` : `constructor` / `Core` (OZ AccessControl)
- **Mechanism:** The constructor sets `_setRoleAdmin(CoreRoles.GOVERNOR, CoreRoles.GOVERNOR)`, making the `GOVERNOR` role its own admin. Combined with the standard single-step `grantRole`/`renounceRole` from OpenZeppelin's `AccessControl`, if the deployer renounces the `GOVERNOR` role prematurely, or if `GOVERNOR` is granted to a contract that cannot call back (or a multisig that is bricked), the system becomes permanently locked. There is no two-step transfer pattern (accept-then-claim) to prevent accidental loss of admin control.
- **Impact:** Permanent loss of administrative control over the entire protocol if the GOVERNOR key is lost, compromised in a way that prevents further action, or transferred to an inaccessible address. All governance, parameter updates, and emergency actions become impossible.

## Profit Not Distributed When Gauge Weight is Zero
- **Location:** `src/governance/ProfitManager.sol` : `notifyPnL` (profit branch)
- **Mechanism:** In the profit distribution branch, the `gaugeProfitIndex` is only updated if `_gaugeWeight != 0`. If no GUILD is currently voting for the gauge (or the gauge has just been offboarded/deprecated), the `amountForGuild` remains in the ProfitManager contract but is never credited to any user's `userGaugeProfitIndex`. The `CreditToken.distribute()` is called for the `amountForCredit` portion, but the GUILD portion becomes stuck in the contract balance without being claimable.
- **Impact:** Loss of GUILD staking rewards. If a profit is generated for a term with no current GUILD supporters, that portion of the profit is permanently locked in the ProfitManager and cannot be claimed by any future voter, since the `gaugeProfitIndex` is never advanced. This represents a value leak from the system.

## Interest and Fee Accounting in Partial Repayment
- **Location:** `src/loan/LendingTerm.sol` : `_partialRepay`
- **Mechanism:** The function calculates `interestRepaid = debtToRepay - principalRepaid`, where `principalRepaid = principal * percentRepaid / 1e18` and `percentRepaid = debtToRepay * 1e18 / loanDebt`. Due to integer division rounding down, when `principal` is small or `percentRepaid` has low precision, `principalRepaid` may round to 0 while `interestRepaid` equals the full `debtToRepay`. This causes the opening fee and time-based interest to be over-counted as "interest" in the current period, and the principal reduction (`issuanceDecrease = borrowAmount * percentRepaid / 1e18`) is calculated independently from the same `percentRepaid`. If rounding causes `principalRepaid = 0` but `percentRepaid > 0`, the `require(principalRepaid != 0 && interestRepaid != 0)` check prevents the transaction, but if `principalRepaid` is very small (e.g., 1 wei) and `interestRepaid` is large, the accounting allocates a disproportionately large share to interest rather than principal, affecting the `borrowAmount` tracking and future interest calculations.
- **Impact:** Minor accounting inconsistencies in loan principal tracking over many partial repayments, potentially leading to slightly incorrect `issuance` values or interest accrual in edge cases with very small principals or large partial repayments.

## Auction End State Requires `forgive` Instead of `bid`
- **Location:** `src/loan/AuctionHouse.sol` : `getBidDetail` / `bid` / `forgive`
- **Mechanism:** After the `auctionDuration` elapses, `getBidDetail` returns `collateralReceived = full amount, creditAsked = 0`. However, the `bid` function explicitly reverts if `creditAsked == 0` (`require(creditAsked != 0, "AuctionHouse: cannot bid 0")`). This means that at the very end of the auction, a rational bidder cannot take the collateral even for free via `bid`; they must rely on `forgive` being called (permissionlessly), which gives 0 collateral to the bidder. The collateral remains stuck in the lending term.
- **Impact:** In the worst case (no bidders during the auction), the collateral is not distributed to anyone and stays in the lending term contract indefinitely. The `forgive` function must be called to clean up the auction state, but it provides no incentive for a third party to do so, and the collateral must be recovered via `emergencyAction` (governance), creating a manual operational burden.
