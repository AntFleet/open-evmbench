# Audit: 2025-04-virtuals

## Validator reward distribution reverts due to base-score double-counting
- Location: `ValidatorRegistry.sol` : `_initValidatorScore` / `AgentRewardV2.sol` : `_distributeValidatorRewards`
- Mechanism: `_initValidatorScore` sets `_baseValidatorScore[validator][virtualId] = totalProposals(virtualId)` at the time the validator is added. `validatorScore()` returns `base + scoreOf` (base = totalProposals at join time, scoreOf = proposals actually voted on). In `_distributeValidatorRewards`, `participationReward = validatorRewards * validatorScore / totalProposals`. When a validator is added while proposals already exist (or `addValidator` is called publicly) and then votes on an already-existing proposal, `base + scoreOf > current totalProposals`, so `participationReward > validatorRewards`. The next line `validatorPoolRewards += validatorRewards - participationReward` then underflows and reverts, permanently blocking reward distribution for that agent.
- Impact: An attacker (or any validator added after proposals exist) can permanently DoS reward distribution for an agent. Additionally, even when no underflow occurs, validators receive `> 100%` participation credit, over-allocating rewards from the validator pool.

## `addValidator` is publicly callable
- Location: `AgentNftV2.sol` : `addValidator`
- Mechanism: `addValidator(uint256, address)` has no access control — anyone can add arbitrary addresses as validators for any virtual. Each added validator is appended to the `_validators` array and initialized with a base score.
- Impact: An attacker can bloat the validator array (unbounded loop in `_distributeValidatorRewards` → gas DoS) and can register themselves as a validator to exploit the base-score bug above. Even without voting power, the array growth alone blocks distribution.

## Contribution NFT can be minted regardless of proposal outcome
- Location: `ContributionNft.sol` : `mint`
- Mechanism: `mint` only checks `msg.sender == personaDAO.proposalProposer(proposalId)`. It never checks `isAccepted(proposalId)` (i.e., that the proposal `state == Succeeded`). A proposer can call `mint` for a proposal that is still Active, Defeated, or Expired.
- Impact: A proposer can mint a Contribution NFT (and subsequently trigger Service NFT minting / reward accrual / Minter payouts) for proposals that were rejected or not yet passed, stealing rewards from legitimate contributors.

## `ServiceNft.updateImpact` is publicly callable
- Location: `ServiceNft.sol` : `updateImpact`
- Mechanism: `updateImpact(uint256 virtualId, uint256 proposalId)` is `public` with no access control. It recomputes `_impacts[proposalId]` (and any linked dataset impact) based on the current `_coreServices` maturity. Anyone can call it on any proposalId at any time, overriding previously computed impacts.
- Impact: An attacker can inflate or corrupt service/dataset impacts, manipulating downstream reward distribution in `AgentRewardV2._distributeContributorRewards` and `Minter.mint` payouts.

## `Bonding.unwrapToken` lets anyone force-burn and convert other users' tokens
- Location: `Bonding.sol` : `unwrapToken`
- Mechanism: `unwrapToken(address srcTokenAddress, address[] memory accounts)` is `public` and iterates over arbitrary `accounts`, calling `token.burnFrom(acc, balance)` (Bonding is the FERC20 owner so `burnFrom` succeeds) and then `agentToken.transferFrom(pairAddress, acc, balance)`. No permission from the token holders is required.
- Impact: Anyone can force-burn another user's bonding-curve tokens and irrevocably convert them to agent tokens 1:1, regardless of whether the holder consented or whether the timing is favorable.

## `Airdrop.airdrop` does not verify array length match
- Location: `Airdrop.sol` : `airdrop`
- Mechanism: The assembly loop uses `sz := _amounts.length` as the bound for both `_amounts` and `_recipients`. There is no `require(_recipients.length == _amounts.length)`. If `_recipients` is shorter than `_amounts`, the code reads past the end of the `_recipients` calldata array, sending tokens to arbitrary calldata-derived addresses.
- Impact: Token loss to unintended addresses; silent corruption of the airdrop.

## `BMWToken.mint` is publicly callable
- Location: `BMWToken.sol` : `mint`
- Mechanism: `mint(address to, uint256 amount)` has no access control (`onlyOwner` missing).
- Impact: Anyone can mint unlimited BMW tokens, destroying the token's value.

## `BMWTokenChild.setFxManager` is publicly callable
- Location: `BMWTokenChild.sol` : `setFxManager`
- Mechanism: `setFxManager` has no access control. Once set as `_fxManager`, the caller can freely `mint` and `burn` any user's balance.
- Impact: An attacker can take over the bridge token, minting arbitrary supply or burning any holder's tokens.

## `AgentTax.dcaSell` computes `minOutput` in wrong units
- Location: `AgentTax.sol` : `dcaSell`
- Mechanism: `minOutput = ((amountToSwap * (DENOM - slippage)) / DENOM)` uses the **input** taxToken amount as the basis for the minimum **output** (assetToken) amount. The correct minimum output should be derived from `getAmountsOut` and then reduced by slippage. Because input and output token amounts have no fixed 1:1 relationship, the computed `minOutput` is unrelated to the actual expected output.
- Impact: Slippage protection is ineffective; swaps can be sandwiched for arbitrary loss, draining tax revenue.

## `AgentToken.distributeTaxTokens` is publicly callable
- Location: `AgentToken.sol` : `distributeTaxTokens`
- Mechanism: `distributeTaxTokens()` has no access control. It transfers the full `projectTaxPendingSwap` balance of the token itself (not the swapped pairToken) directly to `projectTaxRecipient`, bypassing the auto-swap mechanism.
- Impact: Anyone can force premature tax-token distribution as raw tokens instead of the intended swapped asset, disrupting the project's tax conversion strategy and potentially causing the recipient to receive less value than intended.
