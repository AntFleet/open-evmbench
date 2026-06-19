# Audit: 2023-12-ethereumcreditguild

## Late gauge voters can claim historical rewards
- Location: `src/governance/ProfitManager.sol` : `claimGaugeRewards`; `src/tokens/GuildToken.sol` : `_incrementGaugeWeight`
- Mechanism: `claimGaugeRewards()` returns immediately when a user has zero current gauge weight, so it does not initialize `userGaugeProfitIndex[user][gauge]` to the current `gaugeProfitIndex`. When that user later adds gauge weight, their index remains `0`, which is treated as `1e18` on the next claim. This makes the new voter accrue all past gauge profit since index initialization, not only profit earned after they started voting.
- Impact: An attacker can wait for a gauge to accumulate profits, vote GUILD to that gauge, then claim historical CREDIT rewards they did not earn. This can drain CREDIT held by `ProfitManager`, including funds backing legitimate rewards and potentially other accounting buckets.

## SurplusGuildMinter incorrectly slashes all users after any historical loss
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: `getRewards()` checks `lastGaugeLoss > uint256(userStake.lastGaugeLoss)` before loading `userStake = _stakes[user][term]`. The comparison is therefore made against the zero-value memory struct. Once a term has ever had a loss, `slashed` becomes true for every user, including users who staked after that loss and whose stored `lastGaugeLoss` should protect them.
- Impact: Anyone can call `getRewards(user, term)` for another user and wipe that user’s SurplusGuildMinter position after any prior loss on the term. The victim’s CREDIT stake is forfeited and their accounting is deleted even though they were not exposed to the loss.

## Loss slashing can be blocked by the debt-ceiling check
- Location: `src/tokens/GuildToken.sol` : `applyGaugeLoss` / `_decrementGaugeWeight`
- Mechanism: `applyGaugeLoss()` uses `_decrementGaugeWeight()` to remove lossy gauge weight. The override also enforces the voluntary-decrement debt-ceiling check: if the lending term still has issuance, it requires `issuance <= debtCeilingAfterDecrement`. After a real loss, removing/slashing weight often reduces the debt ceiling below remaining issuance, so the forced slash can revert.
- Impact: GUILD voters exposed to a bad-debt event may be impossible to slash while the term still has outstanding issuance. Their weight can remain counted in gauge totals, preserving debt ceiling for a lossy term and defeating the intended first-loss/slashing mechanism.

## Stale offboarding quorum can be executed indefinitely
- Location: `src/governance/LendingTermOffboarding.sol` : `supportOffboard` / `offboard`
- Mechanism: `supportOffboard()` enforces `POLL_DURATION_BLOCKS` only while votes are being added. Once quorum is reached, it sets `canOffboard[term] = true` permanently. `offboard()` only checks `canOffboard[term]` and does not verify that the poll is still within its validity window.
- Impact: A term that reached offboarding quorum once can be offboarded by anyone at any later time, even long after the poll became stale. This can unexpectedly remove an active lending term, force loan calls, and pause PSM redemptions.

## Bad debt larger than remaining CREDIT supply bricks loss realization
- Location: `src/governance/ProfitManager.sol` : `notifyPnL`
- Mechanism: For losses exceeding the surplus buffer, the contract computes `creditTotalSupply - loss`. If borrowers have redeemed or otherwise reduced circulating CREDIT such that the remaining loss is greater than current CREDIT total supply, this subtraction reverts. The lending term and auction house call this during `onBid()` / `forgive()`, so the whole loan-closing transaction reverts.
- Impact: An attacker can borrow CREDIT, redeem or move it out of circulation, then default so the realized loss exceeds remaining CREDIT supply. The protocol cannot finalize the auction/forgiveness path, leaving bad loans and collateral stuck and preventing accounting from recognizing the loss.

## Same-block gauge losses can be collapsed and bypass slashing
- Location: `src/tokens/GuildToken.sol` : `notifyGaugeLoss` / `applyGaugeLoss`
- Mechanism: Losses are tracked only by `block.timestamp` in `lastGaugeLoss[gauge]`. Multiple loss events for the same gauge in the same block write the same value. A user can be slashed or marked applied for the first loss, re-add weight in the same block, and the second loss is indistinguishable because `lastGaugeLossApplied >= lastGaugeLoss`.
- Impact: If multiple losses are realized for a gauge in one block, users can avoid being slashed for later losses in that block. This undercharges GUILD voters for bad debt and weakens the loss-socialization mechanism.

## Fee-on-transfer collateral is overcounted
- Location: `src/loan/LendingTerm.sol` : `_borrow`, `_addCollateral`
- Mechanism: The lending term records `collateralAmount` and calculates borrow capacity from the user-supplied amount before verifying how many collateral tokens were actually received. With a fee-on-transfer or deflationary collateral token, `safeTransferFrom()` can deliver less than `collateralAmount` while the loan is accounted as if the full amount arrived.
- Impact: If such a collateral token is onboarded, borrowers can mint CREDIT against collateral the term never received. Repayment/auction accounting will overstate collateral, creating undercollateralized debt and potential bad debt for the protocol.

