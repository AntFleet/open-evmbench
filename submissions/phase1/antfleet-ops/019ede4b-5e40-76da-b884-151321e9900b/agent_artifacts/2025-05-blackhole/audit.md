# Audit: 2025-05-blackhole

## GenesisPoolManager Router Update Bricked by Zero-Address Requirement
- Location: `contracts/GenesisPoolManager.sol` : `setRouter`
- Mechanism: The `setRouter` function contains a logic error in its require statement: `require(_router == address(0), "ZA");`. This enforces that the new router address *must* be the zero address, rather than checking that it is *not* the zero address (`!=`). 
- Impact: If the protocol ever needs to upgrade or change the router address, the owner is forced to set it to `address(0)`. This will permanently brick the `launch` function for all genesis pools, as it relies on calling `addLiquidity` on the router, resulting in failed pool launches and locked genesis funds.

## RewardsDistributor `claim_many` Misroutes Expired AVM Lock Rewards
- Location: `contracts/RewardsDistributor.sol` : `claim_many`
- Mechanism: When an NFT lock has expired, the distributor transfers the rebase rewards directly to the NFT owner. The `claim` function correctly checks if the NFT is managed by the AutoVotingEscrowManager (AVM) and redirects the payout to the `originalOwner`. However, `claim_many` omits this AVM check and simply calls `IVotingEscrow.ownerOf(_tokenId)`, which returns the AVM contract address for delegated locks.
- Impact: Users who have expired NFTs locked in the AVM and use `claim_many` to batch-claim their rebase rewards will have their tokens permanently sent to the AVM contract. Since the AVM lacks a mechanism to recover or forward these base tokens, the users' rewards are irrecoverably lost.

## GaugeFactoryCL Missing Upper Bound on Referral Fee Causes Fee Claim DoS
- Location: `contracts/AlgebraCLVe33/GaugeFactoryCL.sol` : `setReferralFee`
- Mechanism: The `setReferralFee` function allows an admin to set `dibsPercentage` to any arbitrary value without validating it against the `REFERRAL_FEE_DENOMINATOR` (1000). In `GaugeCL._claimFees()`, the protocol fee is calculated as `claimed0 * referralFee / 1000`. If `referralFee` is set greater than 1000 (e.g., 2000 for 200%), the calculated fee will exceed the actual claimed amount. The subsequent subtraction `claimed0 -= _dibsFeeToken0` will then underflow and revert.
- Impact: An administrative mistake or a malicious insider can set the referral fee above 100%, which will cause all subsequent `claimFees` and `stakedFees` calls on the Concentrated Liquidity gauges to permanently revert. This effectively locks all accrued trading fees inside the gauge contracts, denying LPs and bribe contracts their revenue.
