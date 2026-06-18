# Audit: 2024-06-vultisig

## Whitelist index bypass allows any address to buy tokens
- Location: `Whitelist.sol` : `checkWhitelist`
- Mechanism: The whitelist check uses `_allowedWhitelistIndex == 0 || _whitelistIndex[to] > _allowedWhitelistIndex` to revert. If `_allowedWhitelistIndex > 0`, an address with `_whitelistIndex[to] == 0` (i.e. not whitelisted) will not satisfy `0 > X`, so the check passes. This allows any unwhitelisted address to bypass the whitelist entirely and purchase tokens from the Uniswap pool.
- Impact: An attacker can freely buy tokens during the whitelist period without being whitelisted, defeating the entire purpose of the whitelist and potentially front-running legitimate participants.

## Reentrancy in `buy` allows bypassing per-user contribution cap
- Location: `ILOPool.sol` : `buy`
- Mechanism: The function increments `totalRaised` and mints an NFT (which triggers an external call to the recipient via `onERC721Received`) before updating `_position.raiseAmount`. A malicious recipient contract can re-enter `buy` during the mint callback. In the re-entered call, `_position.raiseAmount` is still 0, so the per-user cap check passes. The original call then adds its `raiseAmount` on top of the already increased value, causing the total per-user contribution to exceed the cap.
- Impact: An attacker can exceed the per-user cap, buying more tokens than allowed and potentially draining the allocation pool.

## TWAP oracle manipulation can bypass ETH contribution cap
- Location: `Whitelist.sol` : `checkWhitelist` (uses `UniswapV3Oracle.peek`)
- Mechanism: The contract relies on a 30-minute Uniswap V3 TWAP to estimate the ETH value of the bought VULT tokens and enforce a per-address ETH cap. An attacker can manipulate the pool price over the observation window (e.g. with large swaps or flash loans) to make the oracle return a significantly lower ETH estimate. This allows the attacker to buy more tokens while staying under the cap, effectively bypassing the contribution limit.
- Impact: An attacker can bypass the per-address contribution cap, accumulating more tokens than intended at a potentially favorable price.

## Denial of service in `launch` via strict pool price check
- Location: `ILOManager.sol` : `launch`
- Mechanism: The `launch` function requires the Uniswap V3 pool’s current `sqrtPriceX96` to be **exactly equal** to the `initialPoolPriceX96` set during project initialization. Since the pool is a public Uniswap V3 pool, anyone can add liquidity and execute a swap to change the price even by a tiny amount. This causes the `launch` call to revert permanently, and there is no way to reset the price to the exact initial value.
- Impact: An attacker can grief any ILO project by performing a minimal swap to shift the pool price, making the launch impossible forever. This leads to complete failure of the ILO and potential financial loss for the project and investors.
