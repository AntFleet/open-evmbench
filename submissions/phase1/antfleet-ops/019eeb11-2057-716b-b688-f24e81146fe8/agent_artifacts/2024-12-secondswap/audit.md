# Audit: 2024-12-secondswap
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Security audit — merged findings (6 reports: opus-4-8 ×3, gpt-5.5 ×3)

Merge of 6 independent reports. Disagreements are preserved, not resolved. **14 distinct findings** identified across all inputs; **14** appear below.

---

## Consensus findings

## Private-listing whitelist is open to anyone (self-whitelisting)
*(consensus, 5 of 6 reports)*
- Location: `contracts/SecondSwap_Whitelist.sol` : `whitelistAddress` (consumed by `contracts/SecondSwap_Marketplace.sol` : `_validatePurchase`)
- Mechanism: `whitelistAddress()` is externally callable by anyone and self-registers `msg.sender` until `maxWhitelist` is reached. The lot owner can only set the cap (`setMaxWhitelist`), never choose which addresses are allowed. Private listings gate buyers solely on `IWhitelist(listing.whitelist).validateAddress(msg.sender)`, so the whitelist enforces a head-count, not an access list.
- Impact: Any address can self-whitelist and purchase from a listing meant for specific buyers, or sybil-fill all slots to grief/DoS the intended participants out of the private allocation.

## Token issuer can seize any beneficiary's vesting without consent
*(consensus, 5 of 6 reports)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting` (the `msg.sender == tokenIssuer || manager || vestingDeployer` check) and `contracts/SecondSwap_VestingDeployer.sol` : `transferVesting`
- Mechanism: `transferVesting(_grantor, _beneficiary, _amount)` only checks that the *caller* is `tokenIssuer`/`manager`/`vestingDeployer`; it never verifies that `_grantor` authorized the move. The remediation added only a `_tokenOwner[msg.sender] == token` check in the deployer wrapper (caller owns the *token*, not grantor consent), and `tokenIssuer` (the deploy-time token owner EOA) can call `StepVesting.transferVesting` directly, bypassing the wrapper entirely.
- Impact: The issuer — or anyone who compromises that single key (no timelock/multisig) — can move any user's unclaimed allocation to themselves or any address and `claim()` it: a full clawback/rug of every beneficiary, including marketplace buyers.

## Default deployed payment token is freely mintable (permissionless `mint`)
*(consensus, 4 of 6 reports)*
- Location: `contracts/USDT.sol` : `TestToken1.mint` + `script/DeploySecondSwap.s.sol` : `run` (the `cfg.usdt == address(0)` / unset `SECOND_SWAP_USDT` branch)
- Mechanism: `TestToken1.mint(address,uint256)` has no access control. When `SECOND_SWAP_USDT` (and the initial payment token) are unset, the deploy script wires `TestToken1` in as `usdt`/`initialPaymentToken`; `Marketplace.initialize` marks it `isTokenSupport = true` and `MarketplaceSetting.usdt` (penalty currency) is the same token.
- Impact: In the default deployment, any attacker mints unlimited payment currency for free, then `spotPurchase`s every listing for zero real cost, receiving real vested tokens while sellers receive worthless minted currency — a total economic break.

## `releaseRate` recomputed with the wrong denominator in `transferVesting` → over-claim / pool insolvency
*(consensus, 3 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting` (`grantorVesting.releaseRate = grantorVesting.totalAmount / numOfSteps;` after `totalAmount -= _amount`) interacting with `claimable` (`claimableAmount = releaseRate * claimableSteps`)
- Mechanism: When a grantor's allocation is reduced (sale/listing or direct transfer), `releaseRate` is recomputed as `totalAmount / numOfSteps`, ignoring both `amountClaimed` and `stepsClaimed` — unlike `_createVesting`'s correct `(totalAmount - amountClaimed) / (numOfSteps - stepsClaimed)`. `claimable()`'s non-final branch returns `releaseRate * claimableSteps` with no cap at the true remaining entitlement (`totalAmount - amountClaimed`). Worked example (N=10, T=1000, rate 100; claim 5 → amountClaimed=500; list 400 → totalAmount=600, rate set to 600/10=60 instead of (600-500)/(10-5)=20): by step 9 the user claims 60×4=240 against a 100-token entitlement.
- Impact: Reachable permissionlessly via the normal "claim a bit, then `listVesting`" flow (which routes through `VestingManager.listVesting → StepVesting.transferVesting(seller, manager, amount)`). The beneficiary drains ~`(stepsClaimed/numOfSteps) * transferredAmount` extra tokens from the shared StepVesting pool that backs all beneficiaries; the final-step branch then underflow-reverts, bricking `claim()` for honest users.
- Reviewer disagreement: one report (opus-4-8 shot 2) argued `claimable`'s end-branch caps payout at `totalAmount - amountClaimed`, so no over-claim/insolvency results.

## Referral reward is computed and emitted but never paid (transfer/event desync)
*(consensus, 3 of 6 reports)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers` (the `referralFeeCost` block + `feeCollectorTotal` transfer) and `spotPurchase` (the `Purchased` event)
- Mechanism: `_handleTransfers` computes `referralFeeCost` but performs no transfer to `_referral`; the buyer is still charged the full `buyerFeeTotal`, and `feeCollectorTotal = buyerFeeTotal + sellerFeeTotal` (including the notional referral portion) is sent entirely to `feeCollector`. `referralFeeCollector` is never set/used. `spotPurchase` then emits `Purchased(..., referralReward = referralFeeCost)`, asserting a payout that never occurred.
- Impact: Referrers receive nothing while the event records a reward; `feeCollector` silently captures the funds. Off-chain accounting/integrators trusting the `Purchased` event's `referralReward` are misled (and may over-pay referrers from their own funds).

## Purchase price rounds down in the buyer's favor (partial-purchase underpay)
*(consensus, 2 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers` (`baseAmount = (_amount * discountedPrice) / 10**decimals`) and `_validatePurchase`
- Mechanism: `baseAmount` is a floor division (and `_getDiscountedPrice` also floors), so the buyer always pays the rounded-down cost. The `require(baseAmount > 0)` patch only blocks the zero-payment case. For partial listings with low/zero `minPurchaseAmt`, a buyer can split a purchase into many small chunks sized just above the `baseAmount == 1` boundary, capturing the discarded fractional unit each time; fees are also computed on the rounded-down amount.
- Impact: A seller who under-prices, or lists a high-`decimals` token with a low per-unit price, and does not set a sufficient `minPurchaseAmt`, can be drained up to ~50% below fair value through many small `spotPurchase` calls.
- Reviewer disagreement: one report (opus-4-8 shot 2) argued the truncation is bounded to <1 currency unit per purchase by the `require(baseAmount > 0)` guards, so it is not a practical drain.

## CEI violation in `spotPurchase` — external calls precede listing-state update (reentrancy)
*(consensus, 2 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `spotPurchase` / `_handleTransfers` (the buyer/seller/feeCollector transfers run before `listing.balance -= _amount` and `listing.status = ...`)
- Mechanism: Currency moves to/from buyer, seller, and `feeCollector` happen before the listing balance/status are updated. With a hook-bearing currency (ERC-777, or any token added via the now-validation-free `addCoin`), the seller/fee collector can re-enter `spotPurchase`/`unlistVesting` while the listing still shows the pre-purchase `balance`/`LIST` status. A fee-on-transfer currency also makes outbound payouts exceed what was actually received.
- Impact: A latent reentrancy window. Both reporting models note the most damaging double-spend is currently blocked by the `listing.balance -= _amount` 0.8 underflow revert, but flag it as exploitable under any relaxation of the balance math or a re-entrant path that bypasses that decrement; fix via checks-effects-interactions and/or `nonReentrant`.
- Reviewer disagreement: one report (opus-4-8 shot 1) classified this as not exploitable, "incidentally protected" by the same underflow revert.

## Unbounded discount percentage can permanently brick a listing
*(consensus, 2 of 6 reports)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `listVesting` (discount validation) → `_getDiscountedPrice`
- Mechanism: `listVesting` only enforces `(_discountType != NO && _discountPct > 0) || _discountType == NO`; there is no upper bound. For `FIX`, `discountPct >= BASE` makes `BASE - discountPct` underflow-revert or yields `discountedPrice == 0 → baseAmount == 0 →` `require(baseAmount > 0)` revert. For `LINEAR`, `discountPct > BASE` makes `(_amount * discountPct)/total` exceed `BASE` and underflow for larger amounts.
- Impact: A misconfigured or maliciously crafted listing becomes permanently unpurchasable (every `spotPurchase` reverts), locking the seller's tokens in vesting-manager escrow until `unlistVesting`. Self-inflicted (no theft), but a config-validation gap; bound `_discountPct <= BASE`.

## Merged vesting histories allow early unlock of transferred/listed allocations
*(consensus, 2 of 6 reports)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting` / `_createVesting` / `claimable`
- Mechanism: `transferVesting` passes the grantor's `stepsClaimed` into `_createVesting`, but when the beneficiary already has a vesting entry, `_createVesting` ignores the incoming `_stepsClaimed`, keeps the beneficiary's existing `stepsClaimed`, and recomputes `releaseRate` over the merged total. Because the marketplace escrows all listed vesting under the single `VestingManager` address, allocations with different claim histories get merged into one record. (Distinct from the `releaseRate` over-claim finding: this is early unlock from merging *different* claim histories, not over-claim from the wrong denominator.)
- Impact: A buyer (or the escrow) with a lower `stepsClaimed` can make a newly received future-locked allocation immediately claimable. No extra total tokens are minted, but the lockup schedule is broken and vesting is accelerated. Precondition: merged allocations with differing claim histories.

## Invalid step math can unlock early or brick claims
*(consensus, 2 of 6 reports)*
- Location: `contracts/SecondSwap_VestingDeployer.sol` : `deployVesting`; `contracts/SecondSwap_StepVesting.sol` : `constructor` / `claimable`
- Mechanism: `deployVesting` only checks `steps > 0` and `startTime < endTime`, never `steps <= endTime - startTime`. The constructor computes `stepDuration = (endTime - startTime) / numOfSteps` (floor division). If non-divisible, `claimable()` can reach `numOfSteps` before `endTime` (early full unlock); if `steps > endTime - startTime`, `stepDuration == 0` and `claimable()` divides by zero (every claim reverts).
- Impact: A token issuer can deploy a sellable plan whose allocations either unlock fully before the configured end time, or are permanently unclaimable (divide-by-zero), then list/sell them through the marketplace; buyers receive accelerated or permanently bricked vesting.

---

## Minority findings

## `addCoin` performs no validation on added currencies
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `addCoin`
- Mechanism: The decimals/sanity validation is commented out; `addCoin` only checks admin and not-already-supported, then sets `isTokenSupport[_token] = true`. Any token (fee-on-transfer, rebasing, reentrant/ERC-777, or one whose `decimals()` reverts) can become a purchase currency.
- Impact: Admin-gated, so primarily a trust/operational hazard, but it directly enables the reentrancy surface above and can desync `_handleTransfers` accounting (fee-on-transfer tokens make outbound transfers exceed receipts), and re-opens the `decimals()`-existence assumption the rest of the code relies on.
- Reviewer disagreement: one report (opus-4-8 shot 1) classified the dropped `decimals()` validation as admin/seller-gated misconfiguration, not externally exploitable (and another report corroborated the concern as an aggravator within its reentrancy finding).

## Uninitialized implementation contracts (missing `_disableInitializers()`)
*(minority, 1 of 6 reports)*
- Location: `contracts/SecondSwap_Marketplace.sol`, `SecondSwap_VestingManager.sol`, `SecondSwap_VestingDeployer.sol` (each `initialize(...) initializer`, no constructor `_disableInitializers()`)
- Mechanism: The logic contracts behind the transparent proxies never call `_disableInitializers()`, so their `initialize` functions are callable directly on the implementation by anyone.
- Impact: Low for transparent proxies (no delegatecall/selfdestruct in the implementations, separate proxy storage), but a deviation from standard upgradeable-contract hardening; add a constructor calling `_disableInitializers()`.

## Max-sell limit can be bypassed by wash trading
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `contracts/SecondSwap_VestingManager.sol` : `listVesting`, `completePurchase`
- Mechanism: `listVesting` treats `allocations[user][plan].bought` as fully resellable and separately allows a percentage of `currentAlloc + sold - bought`. `completePurchase` increments `bought` whenever an address buys vesting, including controlled addresses in a self-trade cycle. A grantee sells the allowed percentage to a second wallet, has it sold back, raising the original grantee's `bought` while retaining `sold` history, increasing future sell capacity.
- Impact: A beneficiary cycles vesting through controlled wallets (paying marketplace fees) to bypass `maxSellPercent` and eventually sell far more than the issuer-configured cap, potentially the full allocation.
- Reviewer disagreement: two reports (opus-4-8 shots 1 and 2) argued self-purchases increase `bought` and `sold` by equal amounts so `sellLimit - sold` / `currentAlloc + sold` stays invariant, leaving the on-market amount bounded by `maxSellPercent`.

## Fee-on-transfer vested tokens create unbacked vesting balances
*(minority, 1 of 6 reports)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `_createVesting`, `claim`
- Mechanism: `_createVesting` credits the full `_totalAmount` to the beneficiary after `safeTransferFrom` without verifying how many tokens were actually received; `claim` increments `amountClaimed` by the full claimable amount before transferring, without checking the recipient received that full amount.
- Impact: For fee-on-transfer, rebasing, or otherwise non-standard vested tokens, recorded accounting can exceed the contract's real balance; beneficiaries/buyers may receive less than recorded, have later claims revert, or buy vesting that is not fully backed. Precondition: a vesting plan deployed for a token with transfer fees, rebasing, or malicious ERC20 semantics.

---

**Checklist:** distinct findings across inputs = 14; findings emitted = 14 (10 consensus + 4 minority). No finding dropped; defended-but-claimed paths (releaseRate over-claim, price rounding, CEI/reentrancy, addCoin, wash trading) retained with their disagreements noted. The two distinct vesting-merge/over-claim defects (wrong-denominator over-claim vs. merged-history early unlock) and the two distinct fee-on-transfer surfaces (payment currency via `addCoin` vs. vested token via `_createVesting`) are kept separate per the no-merge rule.

