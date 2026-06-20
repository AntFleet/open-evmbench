# Audit: 2024-06-vultisig

Here is the security audit report for the provided Solidity codebase.

## Whitelist Bypass via Logical Validation Error
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: The check `_allowedWhitelistIndex == 0 || _whitelistIndex[to] > _allowedWhitelistIndex` is used to validate if a buyer is on the whitelist. However, if a user is not whitelisted, their `_whitelistIndex[to]` is defaulted to `0`. If `_allowedWhitelistIndex` has been set to a positive value (e.g., `5`), then for a non-whitelisted user, `_allowedWhitelistIndex == 0` is false, and `0 > 5` is also false. Thus, the check evaluates to `false` and does not revert. 
- Impact: Non-whitelisted addresses can bypass the whitelist check entirely and buy VULT tokens from the pool, rendering the whitelist restriction useless.

## Systemic Fee Collection Flaw Leading to Claim Insolvency
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: All individual token positions are managed under a single unified Uniswap V3 position belonging to the `ILOPool` contract address. When calling `pool.collect` with `type(uint128).max` to retrieve fees, the contract physically collects the *entire* pool's accrued fees across all users. The contract then incorrectly calculates the `feeTaker`'s portion as `amountCollected - amount0`. Since `amount0` only includes the single claimant's share of fees, all prior accumulated fees belonging to other (non-claiming) users are prematurely swept and sent to the `feeTaker`.
- Impact: The first user to claim will succeed, but they will trigger the transfer of all other users' fees to the `feeTaker`. Subsequent claims by other users will try to claim their expected fees, but since those fees are already gone from the Uniswap V3 position, the contract will either revert due to subtraction underflow or fail to transfer the tokens, permanently bricking claims and locking remaining users' liquidity and principal.

## Denial of Service (DoS) on Project Launching
- Location: `src/ILOManager.sol` : `launch`
- Mechanism: The `launch` function requires that the Uniswap V3 pool's current active price exactly matches the preconfigured initial price: `require(_cachedProject[uniV3PoolAddress].initialPoolPriceX96 == sqrtPriceX96, "UV3P")`. Because Uniswap V3 pools are public, any actor can perform a tiny swap of 1 wei on the pool prior to launch, shifting the active pool price by a negligible fraction and permanently breaking the equality requirement.
- Impact: An attacker can easily block any project from launching at a near-zero cost, bricking the pool and forcing all raised funds into the refund flow.

## Bypass of `maxCapPerUser` limit via ERC721 Transfers
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: The contract restricts contribution-per-user by evaluating whether an address already owns an NFT via `balanceOf(recipient) == 0`. If the user already owns an NFT, it retrieves the current token ID and checks the contribution limit. However, ERC721 transfer functions are not overridden or disabled. An investor can purchase up to `maxCapPerUser`, transfer their newly minted position NFT to a secondary wallet setting their `balanceOf` back to `0`, and then immediately buy again.
- Impact: A single user can easily circumvent the `maxCapPerUser` contribution limits and acquire an unlimited portion of the token sale, defeating the fair-launch design.

## Pool Bricking via Missing Upper Bound Price Check in `initILOPool`
- Location: `src/ILOManager.sol` : `initILOPool`
- Mechanism: The function checks `require(sqrtRatioLowerX96 < _project.initialPoolPriceX96 && sqrtRatioLowerX96 < sqrtRatioUpperX96, "RANGE");` but fails to verify that the initial price is strictly bounded below the upper tick (`_project.initialPoolPriceX96 < sqrtRatioUpperX96`). If a project admin initializes a pool where the initial price is greater than or equal to the upper tick, the actual Uniswap position requires zero `token0` (raise token). Meanwhile, the contract's custom `_saleAmountNeeded` routine assumes the price is in-range, attempting to mint with full `raiseAmount`.
- Impact: The project will fail to launch because the actual pool minting amounts do not align with the pre-calculated expectations, causing the slippage checks inside `addLiquidity` to always revert and bricking the pool.

## Hardcoded Gas Dependency with `transfer()` in Whitelisting
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `receive`
- Mechanism: The contract refunds ETH to the sender during self-whitelisting using Solidity's built-in `transfer()` method: `payable(_msgSender()).transfer(msg.value);`. This method restricts the forwarded gas limit to exactly 2,300 gas.
- Impact: Smart contracts with complex fallback/receive logic, such as multisigs (Gnosis Safe), will consume more than 2,300 gas and fail to receive the refund, making them entirely unable to self-whitelist.
