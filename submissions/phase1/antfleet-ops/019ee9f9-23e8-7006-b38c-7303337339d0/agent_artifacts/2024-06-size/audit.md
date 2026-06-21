# Audit: 2024-06-size

Security review of the Size protocol code you shared. Findings below are limited to exploitable or materially risky logic — not style or gas.

---

## WETH deposit mints against full contract ETH balance

- **Location:** `src/libraries/actions/Deposit.sol` : `executeDeposit`
- **Mechanism:** For WETH deposits, validation requires `msg.value == params.amount`, but execution sets `amount = address(this).balance` and wraps that entire balance. Any ETH already held by the contract (donations, forced transfers, leftover from a prior call, or ETH sent in a `multicall`) is included in the minted amount, not just the caller’s payment.
- **Impact:** A caller can mint excess `collateralToken` / `borrowAToken` (for the `to` address) without paying for the extra amount, then withdraw underlying and drain protocol backing. An attacker can front-run a victim’s WETH deposit by sending ETH to the contract so the victim unintentionally mints more than they paid for (victim profits, protocol loses), or a single depositor can capture all stranded ETH. This is a direct accounting insolvency path.

```solidity
// validateDeposit: msg.value must equal params.amount
if (msg.value != 0 && (msg.value != params.amount || params.token != address(state.data.weth))) {
    revert Errors.INVALID_MSG_VALUE(msg.value);
}

// executeDeposit: ignores params.amount, uses entire balance
if (msg.value > 0) {
    amount = address(this).balance;
    state.data.weth.deposit{value: amount}();
    ...
}
```

---

## Multicall amplifies ETH balance accounting bug

- **Location:** `src/libraries/Multicall.sol` : `multicall` → `Deposit.sol` : `executeDeposit`
- **Mechanism:** `multicall` is `payable` and uses `delegatecall`, but `executeDeposit` still keys off `msg.value > 0` and then consumes `address(this).balance`. The multicall comments warn not to trust `msg.value`, yet the deposit path does the opposite: it trusts aggregate balance instead of per-call amounts. One `msg.value` attached to `multicall` can interact badly with multiple WETH deposits or with pre-existing contract ETH.
- **Impact:** Same as above — unbacked minting and withdrawal of underlying — with extra batching edge cases (first deposit in a batch can absorb all ETH; later deposits in the same batch can mis-account).

---

## Secondary-market `buyCreditMarket` prices off the wrong party’s yield curve

- **Location:** `src/libraries/actions/BuyCreditMarket.sol` : `validateBuyCreditMarket`, `executeBuyCreditMarket`
- **Mechanism:** When `creditPositionId != RESERVED_ID` (buying an existing credit position from an exiting lender), the code sets `borrower = creditPosition.lender` and uses **that lender’s** `borrowOffer` for APR validation and for `getRatePerTenor` / cash–credit conversion. The exiting lender is not the loan’s borrower; loan economics are already fixed in `DebtPosition` / `CreditPosition`. The symmetric flow (`sellCreditMarket`) correctly uses the **incoming** lender’s `loanOffer`.
- **Impact:** A selling lender can change their `sellCreditLimit` borrow curve immediately before a buyer’s transaction to move the cash price (higher APR → buyer pays more cash for the same credit, within the buyer’s `minAPR`). Buyers relying on fair secondary-market pricing can be overcharged. This is manipulable pricing / sandwichable MEV, not a fair order-book exit.

```solidity
// Existing credit path — uses seller (lender) as "borrower" for rate
borrower = creditPosition.lender;
...
uint256 ratePerTenor = state.data.users[borrower].borrowOffer.getRatePerTenor(..., tenor);
```

---

## Secondary-market `buyCreditMarket` can be DoS’d by missing borrow offer

- **Location:** `src/libraries/actions/BuyCreditMarket.sol` : `validateBuyCreditMarket`
- **Mechanism:** On the same path (`creditPositionId != RESERVED_ID`), validation requires `state.data.users[borrower].borrowOffer` to be non-null, where `borrower` is the **seller/lender**. A lender listing credit `forSale` has no protocol requirement to maintain a borrow offer; many lenders will only have a `loanOffer`.
- **Impact:** Buyers cannot take listed credit positions via `buyCreditMarket` unless the seller happens to have posted a borrow offer. Sellers can also grief buyers by clearing their borrow offer while leaving positions marked for sale. Secondary-market liquidity is broken or trivially censored.

---

## Compensate fragmentation fee can be evaded with low collateral

- **Location:** `src/libraries/actions/Compensate.sol` : `executeCompensate`
- **Mechanism:** When partial compensation leaves remaining credit (`exiterCreditRemaining > 0`), the fragmentation fee is charged in collateral as `min(feeInCollateral, borrowerCollateralBalance)`. There is no revert if the balance is insufficient — the fee is silently reduced to whatever collateral remains.
- **Impact:** A borrower with little or no remaining collateral (e.g., after other liquidations or self-liquidations) can fragment credit via `compensate` and pay zero or a heavily discounted fragmentation fee, depriving `feeRecipient` of fees the protocol assumes are collected on fragmentation.

```solidity
uint256 fragmentationFeeInCollateral = Math.min(
    state.debtTokenAmountToCollateralTokenAmount(state.feeConfig.fragmentationFee),
    state.data.collateralToken.balanceOf(msg.sender)
);
state.data.collateralToken.transferFrom(msg.sender, state.feeConfig.feeRecipient, fragmentationFeeInCollateral);
```

---

## `updateConfig` cannot increase `crLiquidation` (governance logic flaw)

- **Location:** `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig` (`"crLiquidation"` branch)
- **Mechanism:** Updating `crLiquidation` reverts when `params.value >= state.riskConfig.crLiquidation`, so the threshold can only be **lowered**, never raised. Initialization requires `crOpening > crLiquidation`, but post-deploy governance cannot tighten liquidation requirements upward if `crLiquidation` was set too low.
- **Impact:** Not a direct user exploit, but a misconfigured or compromised initial `crLiquidation` cannot be corrected upward without upgrade. Liquidations stay easier than intended, increasing borrower / lender loss risk beyond documented parameters.

```solidity
} else if (Strings.equal(params.key, "crLiquidation")) {
    if (params.value >= state.riskConfig.crLiquidation) {
        revert Errors.INVALID_COLLATERAL_RATIO(params.value);
    }
    state.riskConfig.crLiquidation = params.value;
}
```

---

## Self-liquidation lets lenders seize collateral without bringing borrow tokens

- **Location:** `src/libraries/actions/SelfLiquidate.sol` : `executeSelfLiquidate`
- **Mechanism:** When a loan is underwater (`CR < crLiquidation`) and `CR < 100%`, the credit lender can `selfLiquidate`: debt and credit are reduced, and pro-rata collateral is transferred to the lender. No `borrowAToken` is paid into the pool (unlike `repay` / `liquidate`). This is by design but creates an asymmetric exit.
- **Impact:** A lender can exit at the expense of the borrower’s collateral and **other lenders** on the same `DebtPosition` (who remain with credit backed by a smaller collateral pool) without repaying cash into Aave. Borrowers can be stripped of collateral while the loan stays active for others; competing liquidators are bypassed. This is a protocol-risk / fairness issue that can be abused when `crLiquidation` is high relative to market moves.

---

## Oracle / borrow-rate trust assumptions (configuration-dependent)

- **Location:** `src/oracle/PriceFeed.sol` : `getPrice`; `Size.sol` : `setVariablePoolBorrowRate`; `YieldCurveLibrary.sol` : `getAdjustedAPR`
- **Mechanism:**  
  - Price feed uses `latestRoundData` with staleness checks but no round-id / answered-in-round validation; a stale or bad round can still move collateral ratios if within the window.  
  - `BORROW_RATE_UPDATER_ROLE` can set `variablePoolBorrowRate` arbitrarily; offers with non-zero `marketRateMultipliers` trust this off-chain updater.  
  - Setting `variablePoolBorrowRateStaleRateInterval` to `0` disables all market-linked curves (`STALE_RATE`).
- **Impact:** With a malicious or compromised admin/updater, borrowers/lenders can be matched at extreme APRs; liquidations and opening limits can be triggered or avoided via price/rate manipulation. This is centralization risk that becomes exploitable if roles are not tightly controlled.

---

## Variable-pool liquidity check is naive

- **Location:** `src/libraries/CapsLibrary.sol` : `validateVariablePoolHasEnoughLiquidity`
- **Mechanism:** The check uses `underlyingBorrowToken.balanceOf(variablePool)` before market orders that withdraw cash. It does not account for Aave reserve pause, isolation mode, caps, or the fact that donations to the pool inflate this balance without guaranteeing withdrawability for Size’s aToken position.
- **Impact:** Users can match orders that pass the check but fail at withdrawal time, causing failed transactions or stuck funds depending on external Aave state. Lower severity than direct theft, but a real liveness / UX failure mode on the borrow path (`buyCreditMarket`, `sellCreditMarket`, `liquidateWithReplacement`).

---

### Summary

The highest-severity issue is the **WETH deposit / multicall ETH balance mismatch** — it breaks 1:1 minting and can drain backing. The next material issues are **wrong yield curve on secondary `buyCreditMarket`** (manipulable pricing + DoS) and **compensate fragmentation fee evasion**. The remaining items are governance, design asymmetry, or external-dependency risks that still matter in deployment.

I did not flag generic OpenZeppelin upgradeability concerns, rounding favoring the protocol, or voluntary unprofitable liquidations unless they enable third-party theft. If you want, I can switch to Agent mode and map each finding to a concrete proof-of-concept call sequence.

