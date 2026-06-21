# Audit: 2025-05-blackhole

## Arbitrary token whitelisting and gauge creation via unvalidated genesis pool
- Location: contracts/GenesisPoolManager.sol : `depositToken`
- Mechanism: `depositToken(address genesisPool, uint256 amount)` never checks that `genesisPool` is a pool created by `genesisFactory`; it only requires `amount > 0` and `genesisPool != address(0)`, then trusts the return value of `IGenesisPool(genesisPool).depositToken(msg.sender, amount)`. An attacker deploys a contract that returns `true` and reports attacker-chosen `getGenesisInfo().nativeToken` and `getLiquidityPoolInfo().pairAddress`. The branch then executes `tokenHandler.whitelistToken(nativeToken)` using this contract's `GENESIS_MANAGER` privilege (whitelisting is otherwise `GovernanceOrGenesisManager`-gated) and calls `_preLaunchPool` → `gaugeManager.createGauge(pairAddress, 0)`. By pre-creating a real `PairFactory` pair of (scamToken, connectorToken) and pointing `pairAddress` at it, the `createGauge` whitelist/connector/isPair checks all pass (scamToken having just been whitelisted), so a gauge is created for the attacker's pool.
- Impact: An attacker can whitelist arbitrary tokens and stand up an official gauge for an attacker-controlled pool, then vote it up to siphon BLACK emissions.

## Bribe/fee rewards for autovoting veNFTs are permanently lost
- Location: contracts/Bribes.sol : `getReward`
- Mechanism: The recipient is resolved as `_owner = IVotingEscrow(ve).ownerOf(tokenId)`. For an NFT enrolled in autovoting the owner is the per-instance `AutoVotingEscrow` holding contract, but the guard `if(_owner == avm)` compares against `IVotingEscrow(ve).avm()` (the singleton `AutoVotingEscrowManager`), so the branch is not taken and rewards are `safeTransfer`'d to the `AutoVotingEscrow` contract, which exposes no ERC-20 withdrawal path. Even if the branch were taken, `IAutomatedVotingManager(avm).originalOwner(tokenId)` reads the public `originalOwner` mapping in `AutoVotingEscrowManager`, which is never populated (`setOriginalOwner` is an empty stub), so it returns `address(0)`. In both cases `lastEarn[tokens[i]][tokenId]` is advanced to `block.timestamp` before/around the transfer, so the epochs can never be re-claimed even after disabling autovoting.
- Impact: All internal-fee and external-bribe rewards accrued by any veNFT that uses autovoting are sent to an unrecoverable address (the holding escrow or the zero address) and the claim window is consumed, permanently destroying those rewards.

## `claim_many` misroutes rebase of AVM-held expired locks
- Location: contracts/RewardsDistributor.sol : `claim_many`
- Mechanism: For an expired, non-permanent lock, `claim()` remaps the recipient when the NFT is held by the AVM (`avm.tokenIdToAVMId(_tokenId) != 0` → `avm.getOriginalOwner(_tokenId)`), but `claim_many` omits this remap and transfers directly to `IVotingEscrow(_voting_escrow).ownerOf(_tokenId)`. When the expired NFT is owned by an `AutoVotingEscrow` holding contract, the rebase tokens are transferred there, and `token_last_balance` is decremented accordingly.
- Impact: Rebase emissions for autovoting users whose locks expired are sent to the holding escrow, which has no token-withdrawal function, permanently locking those funds.

## `recoverERC20` can drain the BLACK reward token
- Location: contracts/BlackClaims.sol : `recoverERC20`
- Mechanism: The function is documented as "Cannot be called to withdraw emissions tokens," but it transfers the full balance of any `tokenAddress_` (only checking non-zero) to the caller, with no exclusion of `token` (the BLACK reward token transferred into the contract at `finalize`). The owner can therefore call `recoverERC20(BLACK)` while a season's rewards are still claimable.
- Impact: The owner can withdraw the entire pool of season reward tokens, including amounts owed to users who have not yet claimed, directly removing user funds.

