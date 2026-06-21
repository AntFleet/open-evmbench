# Audit: 2024-12-secondswap

# SecondSwap Security Audit Report

Analysis is based on the provided Solidity sources. Findings below are limited to genuine security issues (logic, access control, accounting, reentrancy, etc.).

---

## Reentrancy in `spotPurchase` before listing balance update

- **Location:** `SecondSwap_Marketplace.sol` : `spotPurchase` / `_handleTransfers`
- **Mechanism:** `spotPurchase` performs external ERC20 calls in `_handleTransfers` (`safeTransferFrom` to the marketplace, then `safeTransfer` to seller and fee collector) before updating `listing.balance` and before calling `completePurchase`. Any payment token with transfer hooks (ERC777, ERC1363, or a malicious ERC20 registered via `addCoin`) can reenter `spotPurchase` while `listing.balance` is still the pre-purchase value. Each nested call re-passes `_validatePurchase` and can pull payment again.
- **Impact:** With hook-enabled currencies, an attacker can execute multiple purchases against the same listing balance in one transaction. Depending on amounts and ordering, this can oversell listing inventory, cause reverting transactions that grief buyers, or desynchronize marketplace accounting from vesting-manager state. Standard non-hook ERC20s are not affected, but `addCoin` places no restriction on token behavior.

---

## Manager vesting pool merges incompatible vesting schedules

- **Location:** `SecondSwap_StepVesting.sol` : `_createVesting` ; `SecondSwap_VestingManager.sol` : `listVesting`, `unlistVesting`, `completePurchase`
- **Mechanism:** All listed tokens are held in a single `VestingManager` vesting entry (`address(this)` on the step-vesting contract). When a second seller lists, `_createVesting` merges into the existing entry and only adds to `totalAmount`; it does **not** track per-seller `stepsClaimed` / unlock progress. Later, `transferVesting(address(this), buyer, amount)` and `transferVesting(address(this), seller, amount)` pass the **pooled** `stepsClaimed` to the recipient. A seller who is early in the schedule can therefore inherit a near-complete schedule (or vice versa) depending on who listed first.
- **Impact:**  
  - Buyers can pay for “locked” vesting but receive immediately claimable tokens if the pool was first seeded by a late-stage seller.  
  - Sellers can `unlistVesting` and receive back vesting tagged with another user’s unlock progress, **bypassing vesting locks** and `maxSellPercent` intent (list → unlist → `claim()`).  
  - Attackers can front-run pool state (list a dust amount late-stage) to corrupt schedules for subsequent listers/unlisters/buyers.

---

## `tokenIssuer` can arbitrarily reassign any user’s vesting

- **Location:** `SecondSwap_StepVesting.sol` : `transferVesting`
- **Mechanism:** `transferVesting` allows `msg.sender == tokenIssuer` (in addition to `manager` and `vestingDeployer`) with no check that the grantor consented, that the transfer is part of a marketplace flow, or that `maxSellPercent` is respected. `tokenIssuer` is set to the deployer (`msg.sender`) in `SecondSwap_VestingDeployer.deployVesting` and can call `StepVesting.transferVesting(victim, attacker, amount)` directly, bypassing `VestingDeployer` ownership checks.
- **Impact:** A compromised or malicious token issuer can steal or reallocate any beneficiary’s vesting without marketplace or seller authorization.

---

## Uninitialized upgradeable implementation contracts

- **Location:** `SecondSwap_Marketplace.sol` : `initialize` ; `SecondSwap_VestingManager.sol` : `initialize` ; `SecondSwap_VestingDeployer.sol` : `initialize`
- **Mechanism:** These contracts use OpenZeppelin’s `Initializable` but expose public `initialize` on the **implementation** with no `_disableInitializers()` in a constructor. If an implementation is deployed without an immediate proxy, anyone can initialize it, become admin-equivalent state holder, and (for marketplace) set `marketplaceSetting` to a malicious config.
- **Impact:** Implementation takeover; if the implementation is ever used directly or mistaken for the proxy, an attacker gains full administrative control of that logic contract.

---

## Unrestricted mint on test USDT allows unlimited marketplace purchases

- **Location:** `USDT.sol` (contract `TestToken1`) : `mint`
- **Mechanism:** `mint` is `public` with no access control. If this token (or any similarly permissionless token) is added as supported currency via `addCoin`, buyers can mint arbitrary balances and use them as payment in `spotPurchase` and penalty payments in `unlistVesting`.
- **Impact:** Complete collapse of payment integrity: unlimited free purchases of vesting positions and free penalty bypass (if penalty is denominated in that token).

---

## Zero `stepDuration` permanently bricks claims

- **Location:** `SecondSwap_StepVesting.sol` : constructor / `claimable`
- **Mechanism:** `stepDuration = (endTime - startTime) / numOfSteps` with no requirement that `endTime - startTime >= numOfSteps`. When `stepDuration == 0`, `claimable` computes `currentStep = elapsedTime / stepDuration` and **divides by zero**, reverting every claim.
- **Mechanism (continued):** `deployVesting` only checks `steps > 0` and `startTime < endTime`, so misconfigured (or maliciously configured) vesting plans are deployable and sellable via `setSellable`.
- **Impact:** Permanent denial-of-service on all claims for that vesting contract; listed tokens become untradeable/unclaimable with funds stuck in vesting/marketplace flows.

---

## Private-sale whitelist is first-come, self-serve (no seller curation)

- **Location:** `SecondSwap_Whitelist.sol` : `whitelistAddress` ; `SecondSwap_Marketplace.sol` : `_validatePurchase`
- **Mechanism:** For private listings, any address can call `whitelistAddress()` until `maxWhitelist` is reached. The lot owner cannot approve specific addresses—only raise `maxWhitelist`. `_validatePurchase` only checks `IWhitelist(listing.whitelist).validateAddress(msg.sender)`.
- **Impact:** Private listings provide no meaningful access control: bots or unintended buyers can fill the whitelist and purchase before intended participants, undermining the private-sale security model (asset leakage to unauthorized buyers at the seller’s chosen price).

---

## Payment rounding systematically undercharges buyers (seller/fund loss)

- **Location:** `SecondSwap_Marketplace.sol` : `listVesting`, `_handleTransfers` ; `SecondSwap_Marketplace.sol` : `_getDiscountedPrice`
- **Mechanism:** `baseAmount = (amount * price) / 10**decimals` rounds **down** on every purchase. `listVesting` only ensures the **full** listing amount has nonzero value; partial purchases can each round down. With `PARTIAL` listings and small `minPurchaseAmt`, a buyer can split purchases to minimize per-fill rounding. Linear discounts are also bypassed by splitting into smaller fills.
- **Impact:** Buyers acquire vesting for less than the listed economic price; sellers (and protocol fee accounting tied to `baseAmount`) lose value. In extreme decimal/price configurations, value leakage can be material across many fills.

---

## `doesFunctionExist` does not validate `decimals()` return data

- **Location:** `SecondSwap_Marketplace.sol` : `doesFunctionExist` / `listVesting`
- **Mechanism:** `listVesting` gates listing on `doesFunctionExist(token, "decimals()")`, which only checks whether a `staticcall` succeeds—not that the call returns 32 bytes or a sane `uint8`. A malicious or buggy token can implement `decimals()` to always succeed while returning garbage or the wrong size.
- **Impact:** Incorrect `10**decimals` scaling in pricing causes mispriced listings and purchases (including near-zero or zero `baseAmount` behavior), leading to seller loss or failed trades.

---

## Vesting permanently locked when merged at `stepsClaimed == numOfSteps`

- **Location:** `SecondSwap_StepVesting.sol` : `_createVesting` (merge branch) / `claimable`
- **Mechanism:** When adding to an existing beneficiary entry and `stepsClaimed == numOfSteps`, the code sets `releaseRate = 0`. If new tokens are transferred in after the schedule’s step window is exhausted, `claimable` returns zero steps/amount (no terminal catch-up path for “new allocation after schedule end”).
- **Impact:** Tokens transferred to such a beneficiary (including via marketplace `completePurchase` in edge timing cases) can become **permanently unclaimable**, locked in the vesting contract.

---

## Incorrect grantor `releaseRate` after `transferVesting`

- **Location:** `SecondSwap_StepVesting.sol` : `transferVesting`
- **Mechanism:** After reducing the grantor’s `totalAmount`, the code sets `grantorVesting.releaseRate = grantorVesting.totalAmount / numOfSteps` instead of dividing by **remaining** steps `(numOfSteps - grantorVesting.stepsClaimed)` (as `_createVesting` does on creation). For grantors with `stepsClaimed > 0`, this understates `releaseRate` and breaks step-to-amount accounting until the terminal branch of `claimable`.
- **Impact:** Grantors can be underpaid on intermediate claims; in combination with pooling/merging and schedule inheritance on secondary transfers, unlock schedules become unreliable and can be manipulated to shift value between grantor, buyer, and residual pool.

---

## Malicious `marketplaceSetting` redirect (admin rug vector)

- **Location:** `SecondSwap_Marketplace.sol` : `setMarketplaceSettingAddress`
- **Mechanism:** `s2Admin` can point `marketplaceSetting` at any contract. All privileged lookups (`vestingManager`, `feeCollector`, `whitelistDeployer`, `usdt`, fees, freeze flag) are resolved dynamically from that address on every call.
- **Impact:** A malicious or compromised admin can redirect vesting operations and fee routing to attacker-controlled contracts, enabling theft of listed assets and sale proceeds without upgrading the marketplace proxy.

---

## `setSellable` authorization trusts compromised `vestingDeployer`

- **Location:** `SecondSwap_VestingManager.sol` : `setSellable`
- **Mechanism:** `setSellable` is callable by `s2Admin` **or** `vestingDeployer`. `vestingDeployer` is upgradeable and admin-reassignable. Any address marked sellable becomes listable on the marketplace.
- **Impact:** If `vestingDeployer` is compromised or upgraded maliciously, attacker can mark arbitrary vesting contracts as sellable and route them through marketplace flows, amplifying the vesting-pool corruption and unauthorized transfer issues above.

---

## Referral rewards are computed but never paid

- **Location:** `SecondSwap_Marketplace.sol` : `_handleTransfers` / `spotPurchase`
- **Mechanism:** `referralFeeCost` is calculated when `_referral != address(0)` and a public listing is purchased, but no `safeTransfer` sends it to `_referral` or `referralFeeCollector` (declared in settings but unused). The full `buyerFeeTotal` still goes to `feeCollector`.
- **Impact:** Not a direct theft vector, but it breaks the protocol’s economic security model: referrers cannot be paid, incentivizing off-chain manipulation and misleading integrators who rely on `Purchased` event accounting for `referralReward`.

---

## `allocations.sold` can desynchronize from economic reality

- **Location:** `SecondSwap_VestingManager.sol` : `listVesting`, `unlistVesting` ; `SecondSwap_Marketplace.sol` : `spotPurchase`
- **Mechanism:** `allocations[seller][plan].sold` increases by the full listed amount on `listVesting`, is **not** decreased on partial `spotPurchase`, and is only reduced on `unlistVesting` by the **remaining** `listing.balance`. After partial sales then unlist, `sold` can undercount actual sold volume relative to the sell-limit formula.
- **Impact:** Primarily causes incorrect sell-limit enforcement (users blocked from listing their fair share). In edge compositions with the vesting-pool bug, inconsistent `sold` tracking can further confuse who may list how much, enabling policy bypass when combined with unlist/claim paths.

---

## Centralization / trust assumptions (noted for completeness)

The following are serious **trust** issues if keys are compromised, but depend on privileged actors rather than unprivileged attackers:

- `SecondSwap_MarketplaceSetting` admin can freeze/unfreeze, change fees, and re-point `vestingManager` / `whitelistDeployer`.
- `SecondSwap_VestingDeployer` admin can reassign `manager`, `s2Admin`, and `tokenOwner` mappings.
- `tokenIssuer` direct control over vesting transfers (finding above) is a backdoor even without key compromise.

---

## Severity summary

| Severity | Finding |
|----------|---------|
| **Critical** | Manager vesting pool schedule merge corruption (unlock bypass / wrong buyer unlocks) |
| **High** | Reentrancy in `spotPurchase` with hook tokens; `tokenIssuer` arbitrary vesting theft; unrestricted `TestToken1.mint`; zero `stepDuration` brick |
| **Medium** | Uninitialized implementations; FCFS whitelist; payment rounding; `decimals()` weak validation; post-schedule token lock; grantor `releaseRate` bug |
| **Low / Admin** | `marketplaceSetting` redirect; referral never paid; `sold` desync |

---

**Note:** Issues marked in comments (e.g. “3.3 Buyer can choose listing price”, “3.4 s2Admin unable to unlist”) do not manifest as described in the pasted code: `s2Admin` **can** unlist without penalty, and purchase price is taken from stored listing state, not buyer-supplied price. The highest-impact novel issue in this codebase is the **single pooled vesting entry on `VestingManager`**, which corrupts per-user unlock schedules across list/unlist/purchase paths.

