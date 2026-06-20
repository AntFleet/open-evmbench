# Audit: 2024-06-vultisig

## FeeTaker Steals All Accumulated Uniswap Fees From Other Users During Claim
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: When a user claims their vesting liquidity, the contract calls `pool.burn()` which adds the user's principal to the Uniswap V3 position's `tokensOwed`, while also adding the accumulated swap fees for the **entire** position (representing all users' liquidity) to `tokensOwed`. Because the contract subsequently calls `pool.collect()` with `type(uint128).max`, it collects all principal and all accumulated fees for all users. It then computes the caller's proportional principal and fee share (`amount0`), sends it to the user, and sends the entire remainder (`amountCollected0 - amount0`) to the `feeTaker`.
- Impact: The first user to call `claim()` causes all of the swap fees earned by all other users up to that point to be permanently sent to the `feeTaker`. Subsequent users will lose out on their proportional past fees.
