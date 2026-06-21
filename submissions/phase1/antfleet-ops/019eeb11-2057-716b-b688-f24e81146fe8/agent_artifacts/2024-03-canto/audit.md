# Audit: 2024-03-canto
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Missing authentication on `lzCompose` — anyone can drive the pipeline / drain router-held tokens
*(consensus, 6 of 6 reports)*
- Location: `contracts/asd/asdRouter.sol` : `lzCompose` (whole function, reaching `_refundToken`, `_swapOFTForNote`, `_sendASD`)
- Mechanism: `lzCompose` is `external payable` with **no caller restriction** — it never checks `msg.sender == lzEndpoint` (the endpoint is never even stored in the constructor) and never validates that `_from`/source EID/peer is a trusted OFT. Every parameter is attacker-controlled: `_from`, `amountLD`, `composeFrom`, and the entire decoded `OftComposeMessage` (`_cantoRefundAddress`, `_cantoAsdAddress`, `_dstReceiver`, `_minAmountASD`, `_feeForSend`). Two fund-moving paths are reachable directly: **(1) the refund branch**, which runs *before* the `whitelistedUSDCVersions[_from]` check whenever `composeMsg.length != 224` (or whitelist fails), calling `_refundToken(... _from, composeFrom, amountLD ...)` → `IERC20(_from).transfer(refundAddr, amountLD)`; and **(2) the swap/mint pipeline**, where a forged 224-byte payload with a whitelisted `_from` drives deposit→swap→mint→`_sendASD` to an attacker-chosen `_dstReceiver`. The `_swapOFTForNote` comment claims it is "only callable by the owner," but it is reachable by anyone. No reentrancy guard is present.
- Impact: Anyone can set `_from` to any token the router holds and `amountLD` to that balance and transfer it to themselves. Because LayerZero credits the bridged OFT tokens to the composer (this router) **before** the separate `lzCompose` transaction runs, an attacker can front-run the executor and steal in-flight cross-chain deposits (the legitimate `lzCompose` then reverts on the now-empty balance), plus any stranded/failed-flow/accidental balances. Direct theft of funds; the critical vulnerability of the contract.
- Reviewer disagreement: none — found by all six reports.

## Deposits mint against requested amount, over-minting for short-transfer / fee-on-transfer tokens
*(consensus, 3 of 6 reports)*
- Location: `contracts/asd/asdUSDC.sol` : `deposit` (and exit via `withdraw`)
- Mechanism: `deposit` credits `usdcBalances[_usdcVersion] += _amount` and mints asdUSDC from the requested `_amount` after `safeTransferFrom`, without measuring the actual balance delta received. If a whitelisted version is fee-on-transfer, deflationary/rebasing, upgradeable into short-transfer behavior, or otherwise transfers less than `_amount`, the contract records and mints against assets it never received.
- Impact: An attacker using such a whitelisted token deposits it, receives over-minted asdUSDC, then redeems via `withdraw` against a fully-backed, valuable whitelisted version, draining honest collateral. Preconditions: a problematic token is whitelisted and another valuable reserve has withdrawable balance.
- Reviewer disagreement: the opus reviews asserted asdUSDC mints are "fully backed 1:1 (decimal-scaled) per tracked version" — but that assumes standard ERC-20 transfer behavior and does not address the non-standard-token case.

## Attacker-controlled `_cantoAsdAddress` is an approve-then-call primitive over the router's NOTE
*(consensus, 2 of 6 reports)*
- Location: `contracts/asd/asdRouter.sol` : `_depositNoteToASDVault` (`IERC20(noteAddress).approve(_asdVault, _amountNote); _asdVault.call(abi.encodeWithSelector(ASDOFT.mint.selector, _amountNote))`) and `_sendASD` (`ASDOFT(_payload._cantoAsdAddress).transfer(...)`)
- Mechanism: `_cantoAsdAddress` comes straight from the decoded (untrusted) compose payload and is never checked against an allow-list of real ASD vaults. The router grants this arbitrary address a NOTE allowance and then `call`s `mint(_amountNote)` on it; a malicious target can implement `mint` to `noteAddress.transferFrom(router, attacker, _amountNote)` (pulling the just-granted approval) or re-enter `lzCompose`, then return success. `_sendASD` then calls `transfer` on the same arbitrary address again.
- Impact: Arbitrary-approval / arbitrary-call primitive against the router, enabling theft of the NOTE produced by swapping in-flight USDC and corruption of deposit accounting. Exploitable even by a malicious source-chain composer (the payload is author-controlled) independent of the `lzCompose` auth hole.
- Reviewer disagreement: none — no report defended this path.

## Silent `uint256 → uint128` truncation of swap amount and `minOut` in `_swapOFTForNote`
*(consensus, 2 of 6 reports)*
- Location: `contracts/asd/asdRouter.sol` : `_swapOFTForNote` (`uint128 amountConverted = uint128(_amount);` and `uint128 uintMinAmount = uint128(_minAmountNote);`)
- Mechanism: `_amount` (asdUSDC scaled to 18 decimals) and `_minAmountNote` are `uint256` but are downcast to `uint128` before `calcImpact`/`swap`. The pre-trade safety check uses full-width `int minAmountInt = int(_minAmountNote)`, while the value actually enforced in the executed swap is the truncated `uint128(_minAmountNote)`. If either exceeds `2^128 − 1` the high bits drop: a smaller amount is swapped (remainder stranded) and/or the live `minOut` is far smaller than the checked value, desyncing slippage protection from the check.
- Impact: Loss of slippage protection (sandwich-able swap) and/or stranded funds when values exceed `2^128`. Both reporting reviewers rate this low because reaching `~3.4e38`/`~3.4e20` base units is not realistically reachable for this asset; it is the classic check-vs-execution truncation desync and should use a checked cast.
- Reviewer disagreement: one report (opus-4-8 shot 3) examined this and judged it not a genuine attack, arguing the protective full-width check means the truncated `minOut` can never be weaker than what already gated the swap.

## Minority findings

## Refund/send paths ignore ERC-20 boolean return values, stranding funds
*(minority, 1 of 6 reports)*
- Location: `contracts/asd/asdRouter.sol` : `_refundToken` (`IERC20(_tokenAddress).transfer(_refundAddress, _amount);`), `_sendASD` cantoLzEid branch (`ASDOFT(...).transfer(...)`), and `_depositNoteToASDVault` (`IERC20(noteAddress).approve(...)`)
- Mechanism: These use raw `IERC20` methods (not `SafeERC20`) and never check the boolean return. The contract's stated design goal is that it must never revert and must always send tokens to the intended receiver. For a token that returns `false` on failure instead of reverting (common with USDC-family / non-standard tokens), a refund appears to succeed while moving nothing — tokens remain in the router though the user's message is already consumed.
- Impact: User funds that should have been refunded sit unaccounted-for in the router; combined with the unauthenticated `lzCompose` above, an attacker can then sweep those stranded balances, converting a "graceful refund" into permanent loss / theft.
- Reviewer disagreement: none addressed this specific boolean-return issue.

## `asdUSDC` whitelist accepts tokens with `decimals() > 18`, bricking the version (DoS)
*(minority, 1 of 6 reports)*
*(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/asd/asdUSDC.sol` : `deposit` / `withdraw` / `updateWhitelist`
- Mechanism: Both `deposit` and `withdraw` compute `10 ** (this.decimals() - ERC20(_usdcVersion).decimals())`. `updateWhitelist` (owner) admits any token with no decimals sanity check, so whitelisting a token with `decimals() > 18` makes the subtraction underflow (Solidity 0.8 revert), permanently bricking `deposit`/`withdraw`/`recover` for that version.
- Impact: A configuration mistake (owner-gated) permanently denies service to user funds for that version.
- Reviewer disagreement: one report (opus-4-8 shot 3) reviewed the deposit/withdraw decimal-scaling path and considered it sound ("symmetric and inverse," `updateWhitelist` is `onlyOwner`), without flagging the `>18` underflow.

## `asdUSDC.withdraw` silently forfeits sub-unit dust (floor division, full burn)
*(minority, 1 of 6 reports)*
*(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `contracts/asd/asdUSDC.sol` : `withdraw`
- Mechanism: `withdraw` computes `amountToWithdraw = _amount / (10 ** diff)` (floor) but burns the full `_amount`; any sub-unit remainder is burned with zero USDC returned, while `usdcBalances` is only decremented by the floored amount. Value is silently forfeited to the contract.
- Impact: Ordinary users lose dust on every non-exact withdrawal; small per-call loss.
- Reviewer disagreement: two reports (opus-4-8 shots 1 and 3) noted the same rounding but treated it as benign — "by-design tradeoff" and "rounds toward the contract, no drain."

## Global fungible asdUSDC shares let a bad/depegged version drain good USDC versions
*(minority, 1 of 6 reports)*
*(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `contracts/asd/asdUSDC.sol` : `deposit` / `withdraw`
- Mechanism: `deposit` mints one fungible asdUSDC share for any whitelisted `_usdcVersion`, and `withdraw` lets the holder redeem against any whitelisted `_usdcVersion`. `usdcBalances` is tracked per version only as a liquidity cap, not as a per-version liability, and there is no oracle/equivalence check between versions.
- Impact: If two versions are whitelisted and one becomes cheaper/depegged/compromised/frozen-risky, an attacker deposits the bad version and withdraws the good version, draining good collateral from other users. Preconditions: ≥2 whitelisted versions with liquidity in the valuable one.
- Reviewer disagreement: two reports defended this path — opus-4-8 shot 1 dismissed cross-version redemption against shared share supply as a "by-design tradeoff" that only matters with divergent real value; opus-4-8 shot 3 argued "usdcBalances per-version guards prevent cross-version over-withdrawal" and there is "no share-price to inflate."

