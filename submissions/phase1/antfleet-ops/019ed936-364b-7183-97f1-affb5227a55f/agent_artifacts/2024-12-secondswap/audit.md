# Audit: 2024-12-secondswap

# SecondSwap — Merged Security Audit Report

Merged from Report A (Claude) and Report B (Codex). Both reviewers note the SecondSwap contracts were not on disk; locations are cited from the reviewed source with A's approximate line ranges preserved.

A note on merging: the two reports each surface several issues in the same areas (vesting `transferVesting`/`_createVesting` step-math, and privileged vesting transfers). On close reading these are *distinct* root causes and code paths, not restatements of one bug, so most are kept as separate single-reviewer findings rather than force-merged. Only the whitelist issue is described identically by both.

---

## Consensus findings

## Private-sale whitelist allows permissionless self-whitelisting
*(consensus — Reviewer A and Reviewer B)*
- Location: `contracts/SecondSwap_Whitelist.sol` : `whitelistAddress` (~lines 70–80); consumed in `contracts/SecondSwap_Marketplace.sol` : `_validatePurchase` via `IWhitelist(listing.whitelist).validateAddress(msg.sender)`.
- Mechanism: `whitelistAddress()` lets any `msg.sender` add *itself* to the whitelist with no `lotOwner` approval, signature, or preconfigured allowlist check — the only constraint is `totalWhitelist < maxWhitelist`. The `lotOwner` (seller) has no function to curate addresses; they can only raise the cap. `_validatePurchase` treats `validateAddress(msg.sender)` as the sole private-sale gate, so a "private" listing is capacity-limited, not identity-permissioned. The whitelist gates *count*, not *identity*.
- Impact: Any address can front-run/self-register and purchase from a listing the seller intended to restrict to specific buyers, defeating the private-sale access control entirely. An attacker can additionally fill every whitelist slot with sybil addresses to block the intended buyers (DoS). Precondition: listing created with `_isPrivate = true`.

---

## Additional findings (single-reviewer)

## Wrong grantor `releaseRate` recomputation in `transferVesting` enables over-claim
*(Reviewer A only)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting` (the line `grantorVesting.releaseRate = grantorVesting.totalAmount / numOfSteps;`, ~lines 250–262), interacting with `claimable` (~lines 200–225).
- Mechanism: When a grantor transfers part of their vesting out, the grantor's release rate is recomputed as `totalAmount / numOfSteps` using the **full** step count, ignoring `amountClaimed` / `stepsClaimed`. The correct formula (used in `_createVesting`'s else-branch) is `(totalAmount - amountClaimed) / (numOfSteps - stepsClaimed)`. The per-step rate is set far too high whenever `amountClaimed > totalAmount * (stepsClaimed + 1) / numOfSteps`. The linear claim path (`claimableAmount = releaseRate * claimableSteps`) has **no per-step cap** against `totalAmount - amountClaimed`; the only cap exists in the terminal `stepsClaimed + claimableSteps >= numOfSteps` branch, reached *after* the over-claim. Worked example: total=1000, 10 steps, claim 5 steps (claimed=500), transfer out 400 → `totalAmount=600`, `releaseRate=600/10=60`, but only 100 should remain over 5 steps; at steps 6 and 7 the user claims 60+60=120 against a 100 entitlement.
- Impact: Reachable by any beneficiary via the normal marketplace flow (`Marketplace.listVesting → VestingManager.listVesting → StepVesting.transferVesting(seller, manager, amount)`), which recomputes the *seller's* `releaseRate` with the buggy formula. A user who partially claimed then lists a chunk for sale gets an inflated release rate and can `claim()` more than entitled — the extra tokens come from the shared contract balance backing other beneficiaries and the manager's pooled tokens. Direct theft, repeatable across accounts/vestings.

## `tokenIssuer` can directly transfer any beneficiary's vesting (incomplete arbitrary-transfer fix)
*(Reviewer A only)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting` (auth check `msg.sender == tokenIssuer || manager || vestingDeployer`, ~lines 243–248).
- Mechanism: The `VestingDeployer.transferVesting` wrapper was hardened with a `_tokenOwner` check (the "3.2 Arbitrary transfer of vesting" fix), but `StepVesting.transferVesting` still independently authorizes `tokenIssuer`. `tokenIssuer` is set to the deployer's `msg.sender` at construction and can call `StepVesting.transferVesting(_grantor, _beneficiary, _amount)` **directly**, bypassing the wrapper, with an arbitrary `_grantor` (any victim) and arbitrary `_beneficiary`.
- Impact: The token issuer can move any beneficiary's entire unclaimed allocation to an address it controls and then `claim()` it — a complete clawback/rug of distributed vesting with no beneficiary consent. The `VestingDeployer` fix is ineffective because the direct `StepVesting` path remains open. Privileged-actor theft of all beneficiaries' tokens.

## Reentrancy / CEI violation in `spotPurchase` (state updated after external token calls)
*(Reviewer A only)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `spotPurchase` (~lines 470–520) and `_handleTransfers` (~lines 400–450).
- Mechanism: `_handleTransfers` performs external token transfers (`safeTransferFrom` from buyer, `safeTransfer` to seller, `safeTransfer` to fee collector) **before** `listing.balance -= _amount`, `listing.status = …`, and `completePurchase` (allocation update) are written. `_validatePurchase` gates on the still-stale `listing.balance`. If the configured payment `currency` has a transfer hook (ERC-777 / ERC-1363-style, or any malicious admin-added token), the buyer can re-enter `spotPurchase`/`unlistVesting`/`listVesting` while the listing still shows full balance and the manager still holds pooled tokens.
- Impact: Cross-function/same-function reentrancy against pooled vesting accounting and listing state. Reachability depends on `addCoin` (admin-controlled), so it is conditional — but it is a clear CEI violation. Fix by moving balance/status/`completePurchase` writes before transfers or adding a `nonReentrant` guard, since the marketplace explicitly supports arbitrary currencies.

## Referral reward computed and emitted but never paid
*(Reviewer A only)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers` (`referralFeeCost = …`, ~lines 430–445) and `spotPurchase`'s `Purchased` event.
- Mechanism: `referralFeeCost` is calculated when a referral is supplied, but no transfer is ever made to `_referral`. The full `buyerFeeTotal + sellerFeeTotal` is sent to `feeCollector`, and `referralFeeCost` is only passed into the `Purchased` event as `referralReward`. The emitted event reports a referral reward that was never disbursed.
- Impact: Referrers are never paid despite the event indicating otherwise; the amount intended for referrers is silently retained by the fee collector. Funds are conserved (no drain), but the referral mechanism is non-functional and the event misreports on-chain economics — an accounting/integrity bug for any off-chain system relying on `referralReward`.

## No upper bound on `_discountPct` in `listVesting` can permanently brick a listing
*(Reviewer A only)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `listVesting` discount validation (~lines 250–256) and `_getDiscountedPrice` (~lines 360–370).
- Mechanism: Validation enforces only `_discountPct > 0` for non-`NO` discount types; it never checks `_discountPct <= BASE` (10000). In `_getDiscountedPrice`, FIX computes `BASE - listing.discountPct` and LINEAR computes `BASE - (_amount * discountPct / total)`. With `discountPct > BASE` (or FIX `== BASE`) these underflow and revert, or drive the price to 0 so the `baseAmount > 0` check reverts.
- Impact: A misconfigured/oversized discount makes every `spotPurchase` against that listing revert (self-DoS; the seller's tokens are stuck until unlisted). Lower severity since it harms only the lister, but it is an unvalidated setter that bricks downstream logic — needs a `_discountPct <= BASE` bound check.

## `transferVesting` reverts (division-by-zero) when the grantor is fully vested
*(Reviewer A only)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `_createVesting` first branch (`releaseRate: _totalAmount / (numOfSteps - _stepsClaimed)`, ~lines 300–320), reached from `transferVesting` which passes `_stepsClaimed = grantorVesting.stepsClaimed`.
- Mechanism: If the grantor has `stepsClaimed == numOfSteps` (fully vested) and transfers to a brand-new beneficiary, `_createVesting` computes `_totalAmount / (numOfSteps - numOfSteps)` = division by zero → revert.
- Impact: Listing/selling from a fully-vested position to a fresh beneficiary reverts. Mostly an edge-case DoS, but it can block legitimate listings/purchases once a plan is fully vested (e.g., `completePurchase` creating a new buyer vesting from a manager whose `stepsClaimed == numOfSteps`).

## Pooled marketplace escrow corrupts buyer claim schedules
*(Reviewer B only)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting` / `_createVesting`; `contracts/SecondSwap_Marketplace.sol` : `listVesting` / `spotPurchase`.
- Mechanism: `transferVesting` merges incoming vesting into the beneficiary's single aggregate `Vesting` record. When the beneficiary already has a vesting balance, `_createVesting` ignores the incoming `_stepsClaimed` and recomputes `releaseRate` using the beneficiary's *existing* `stepsClaimed`. The marketplace escrow beneficiary is always `SecondSwap_VestingManager`, so listings from sellers with different claimed-step states are pooled into one manager vesting record. Purchases then transfer from that pooled manager record to buyers using the manager's possibly stale `stepsClaimed`, not the original seller/listing schedule. (Distinct from the Reviewer-A grantor-side `releaseRate` bug above: this concerns the beneficiary/manager merge path and the schedule buyers inherit.)
- Impact: An attacker can seed the escrow with a tiny listing that has low `stepsClaimed`, then buy tokens listed by sellers whose vested portions were already claimed. The purchased tokens inherit the escrow's lower `stepsClaimed`, making future-locked tokens immediately or prematurely claimable. Precondition: multiple listings for the same vesting plan pooled through the manager with different claim progress.

## Partial purchases can systematically underpay through rounding
*(Reviewer B only)*
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers`.
- Mechanism: Payment is `(_amount * discountedPrice) / 10 ** vestingTokenDecimals`, rounded down on every purchase. For partial listings the buyer controls `_amount`, so they can split a purchase into many fills that each discard almost one smallest payment unit. The contract only requires `baseAmount > 0`; it does not round up or accumulate the fractional remainder.
- Impact: Buyers can pay less than the listed price and reduce seller proceeds and protocol fees, especially for low-decimal/high-value payment tokens or listings with small/zero `minPurchaseAmt`. Precondition: a partial listing allows sufficiently small purchase chunks. (Note: Reviewer A examined this same `baseAmount` rounding path and assessed the per-trade loss as below one currency unit and not economically meaningful given gas — the two reviewers disagree on exploitability/severity.)

## Invalid step math allows early release or permanently bricked vesting
*(Reviewer B only)*
- Location: `contracts/SecondSwap_StepVesting.sol` : `constructor` / `claimable`; `contracts/SecondSwap_VestingDeployer.sol` : `deployVesting`.
- Mechanism: `stepDuration` is computed with floor division as `(_endTime - _startTime) / _numOfSteps`, while `deployVesting` only checks `startTime < endTime` and `steps > 0`. If the duration is not evenly divisible, `claimable` reaches `currentStep >= numOfSteps` at `startTime + stepDuration * numOfSteps`, which can be earlier than `endTime`. If `steps > endTime - startTime`, `stepDuration` becomes zero and `claimable` reverts on division by zero. (Distinct from Reviewer A's `_createVesting` division-by-zero, which stems from `numOfSteps - stepsClaimed == 0`; this one stems from `stepDuration == 0` in the time math.)
- Impact: Beneficiaries can claim all tokens before the configured `endTime`, or the vesting can be permanently bricked. Precondition: vesting deployed with non-divisible timing, or with more steps than seconds in the vesting duration.

## Duplicate token owners can transfer other issuers' vestings
*(Reviewer B only)*
- Location: `contracts/SecondSwap_VestingDeployer.sol` : `setTokenOwner` / `transferVesting`; `contracts/SecondSwap_StepVesting.sol` : `transferVesting`.
- Mechanism: `setTokenOwner` prevents an owner from receiving two tokens, but does not prevent the same token from being assigned to multiple owners. `transferVesting` authorizes callers only by checking `_tokenOwner[msg.sender] == StepVesting(_stepVesting).token()`. Since `SecondSwap_StepVesting` trusts the deployer contract itself, a second owner assigned to the same token can use the deployer to transfer vesting balances from arbitrary grantors in another owner's vesting contract. (Distinct from Reviewer A's `tokenIssuer` finding: that bypasses the deployer wrapper entirely via direct `StepVesting` access; this abuses the `setTokenOwner` duplicate-owner gap *through* the wrapper.)
- Impact: A duplicated token owner can redirect or steal users' vesting allocations for any vesting contract using that token. Precondition: admin assigns the same token to more than one owner.

## Default USDT token is freely mintable
*(Reviewer B only)*
- Location: `contracts/USDT.sol` : `TestToken1.mint`; `script/DeploySecondSwap.s.sol` : `run`.
- Mechanism: `TestToken1.mint` is public and has no access control. The deployment script deploys `TestToken1` as `USDT` and uses it as the initial payment token when `SECOND_SWAP_USDT` is not provided.
- Impact: On deployments using this default token, any attacker can mint unlimited payment tokens and buy all marketplace listings without real payment. Precondition: the unrestricted `TestToken1` is configured as a supported marketplace currency.

---

### Reconciliation notes
- **Vesting `transferVesting`/`_createVesting` step-math** is hit by four separate findings (A's grantor `releaseRate` over-claim, A's `numOfSteps - stepsClaimed == 0` div-zero, B's pooled-escrow `stepsClaimed` corruption, B's `stepDuration` time-math). They share a subsystem but have different root-cause lines, exploits, and victims, so they are kept distinct rather than merged.
- **Arbitrary vesting transfer** appears as two findings (A's direct-`tokenIssuer` bypass of the deployer wrapper, B's `setTokenOwner` duplicate-owner gap). Different authorization gaps and preconditions; kept distinct.
- **Reviewer A's own non-findings** (rounding dust beyond the partial-fill angle, `VestingManager` sell-limit math, missing `_disableInitializers`, fee bounds) were examined and dismissed by A and are not reproduced as findings here, except where B independently elevated the rounding path (noted inline above).

