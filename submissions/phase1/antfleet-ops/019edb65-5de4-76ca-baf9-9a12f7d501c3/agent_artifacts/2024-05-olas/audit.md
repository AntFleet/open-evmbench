# Audit: 2024-05-olas

## Missing chainId validation in setTargetSelectorChainIds
- Location: GuardCM-flatten.sol : setTargetSelectorChainIds
- Mechanism: The function packs `chainIds[i]` into a storage key by shifting left 192 bits. If the provided `chainId` exceeds `type(uint64).max`, the higher bits are truncated, effectively storing only the lower 64 bits. There is no check that `chainId` is within the allowed range (e.g. `MAX_CHAIN_ID`), unlike the analogous check in `setBridgeMediatorL1BridgeParams`.  
- Impact: An authorised governance call that inadvertently supplies a chainId > 2^64‑1 will silently record a different chainId (the truncated value). This can authorise a target‑selector pair on an unintended chain, potentially allowing the multisig to bypass the guard on that chain.

## Insufficient iteration limit in VotingEscrow checkpoint loop
- Location: VotingEscrow-flatten.sol : _checkpoint
- Mechanism: The `for` loop that fills supply points and propagates slope changes is capped at 255 iterations (~5 years). If the time since the last checkpoint exceeds 255 weeks, the loop never reaches the current block timestamp, leaving the supply points incomplete.  
- Impact: `getPastTotalSupply` and `getPastVotes` will return stale values for blocks after the loop’s end. This can be exploited to artificially lower the quorum and voting power, making governance proposals easier to pass. The attack requires that no checkpoint (or user interaction) occurs for over 5 years, which is unlikely but possible if the contract is abandoned.
