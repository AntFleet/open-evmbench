# Audit: 2024-07-basin

## 1. Shift function allows theft via donation attack
- Location: `src/Well.sol` : `shift()`
- Mechanism: The `shift` function reads the actual token balances of the Well and uses them as the current reserves. It then computes the new reserve of the output token via the Well function and transfers the difference (`balance - computedReserve`) to the caller. An attacker can send a large amount of one token to the Well (inflating its balance), then call `shift` with another token. The inflated balance skews the Well function, making the computed reserve of the output token very small, so the attacker receives the entire balance of that token. The function does not verify that the caller is the one who provided the tokens, making it exploitable by anyone who can transfer tokens to the Well.
- Impact: An attacker can drain one token from the pool entirely by donating another token, stealing all liquidity provider funds.

## 2. Inflation attack via sync function
- Location: `src/Well.sol` : `sync()`
- Mechanism: The `sync` function computes the LP token supply from the current token balances. If the new supply exceeds the old total supply, it mints the difference to the caller. An attacker can donate tokens to the Well (inflating balances), then call `sync` to mint a large amount of LP tokens at a massively discounted rate. The attacker can then remove liquidity to obtain a disproportionate share of the pool, stealing value from existing liquidity providers.
- Impact: An attacker can steal funds from the pool by minting LP tokens and subsequently withdrawing the underlying assets.

## 3. Stable2 decodeWellData incorrectly handles default decimals
- Location: `src/functions/Stable2.sol` : `decodeWellData()`
- Mechanism: The function intends to default missing decimals to 18, but contains a copy‑paste error: it checks `if (decimal0 == 0)` twice instead of checking `decimal1 == 0`. As a result, if the Well data provides `0` for the second token’s decimals (intending to use the default 18), the token’s decimals remain `0`. This causes the reserve scaling `10 ** (18 - decimals)` to multiply by `10^18`, massively inflating the effective reserve of that token.
- Impact: A pool deployed with such data will be severely mispriced, allowing attackers to exploit the incorrect scaling to drain funds from liquidity providers.
