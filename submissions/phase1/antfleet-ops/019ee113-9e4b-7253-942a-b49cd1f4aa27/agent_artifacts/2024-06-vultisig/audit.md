# Audit: 2024-06-vultisig

## Unprotected `ILOManager.initialize` enables ownership hijack
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: The `initialize` function is marked `whenNotInitialized()` but has **no access control** (no `onlyOwner`, no `tx.origin` check). The constructor only does `transferOwnership(tx.origin)`, relying on the deployer to call `initialize` in a separate transaction. Because the implementation contract is deployed publicly and `_initialized` is `false` until the first call, any attacker can front-run the deployer's transaction and pass their own `initialOwner` (and any `_feeTaker`, `iloPoolImplementation`, etc.) into `initialize`. The state is then frozen — subsequent calls revert with `whenNotInitialized`.
- Impact: Complete takeover of the manager. The attacker becomes the owner, can change the platform/performance fees, replace the ILO pool implementation with a malicious one, redirect fees to themselves, and create or hijack projects.

## Reentrancy in `Whitelist.checkWhitelist` (oracle called before state update)
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: The function calls `IOracle(_oracle).peek(amount)` and only then performs the effect `_contributed[to] += estimatedETHAmount`. Solidity's `view` keyword is not enforced at the EVM level, so a malicious or compromised oracle contract can implement `peek` as a state-mutating function that re-enters `checkWhitelist` (or even back into `VultisigWhitelisted._beforeTokenTransfer` while the original transfer is still in flight). On re-entry, `_contributed[to]` is still the old value, so the cap check is evaluated against stale state.
- Impact: The per-address contribution cap (`_maxAddressCap`) and the cumulative `_contributed` accounting can be bypassed/double-counted. An attacker paired with a malicious oracle (or a hijacked upgradeable oracle) can purchase unlimited tokens, exceeding the intended 3 ETH cap per address.

## Cap-bypass via TWAP underestimate of actual ETH spent
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist` (combined with `UniswapV3Oracle.peek`)
- Mechanism: The cap check uses `IOracle(_oracle).peek(amount)`, which is the 30-minute TWAP **with an extra 5 % discount** applied. The actual ETH a buyer pays is determined by the pool's *spot* price at execution time, which is strictly higher than the TWAP for a buy (and higher still with price impact on a low-liquidity pool). The check passes whenever `0.95 * TWAP <= _maxAddressCap`, so a user can spend materially more than `_maxAddressCap` of real ETH while the on-chain check passes and `_contributed[to]` records only the discounted TWAP value.
- Impact: The advertised 3 ETH per-address cap is not enforced against real ETH. A user can repeat buy/sell cycles (selling does not reset `_contributed`, so each round only the small TWAP-discounted amount is recorded) and drain the pool well beyond the intended per-address limit. On a low-liquidity VULT/WETH pool, the gap between TWAP and spot can be large.

## `ILOManager.initILOPool` does not validate the upper tick bound against the initial price
- Location: `src/ILOManager.sol` : `initILOPool`
- Mechanism: The check is `sqrtRatioLowerX96 < _project.initialPoolPriceX96 && sqrtRatioLowerX96 < sqrtRatioUpperX96`. It enforces that the *lower* bound is below the initial price, but it never checks that the *upper* bound is above it. A project admin can therefore pass a range entirely below the initial price (e.g. `tickLower=-887272, tickUpper=-800000` while `initialPoolPriceX96` corresponds to tick 0).
- Impact: The range is one-sided relative to the launch price. `ILOPool._saleAmountNeeded` and `addLiquidity` then compute amounts using a price outside the range, which can either revert at launch (DoS / loss of all raised ETH) or — depending on Uniswap V3 math — succeed with an entirely one-sided position where the project is forced to provide the wrong token mix, diluting investors or losing funds to the pool.

## Fee-on-transfer / rebasing raise token breaks `ILOPool.buy` accounting
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: The function credits the buyer with `raiseAmount` and computes the corresponding `liquidityDelta` *before* pulling tokens via `TransferHelper.safeTransferFrom(RAISE_TOKEN, msg.sender, address(this), raiseAmount)`. If `RAISE_TOKEN` charges a transfer fee, rebases, or has callbacks that reduce the received amount, the contract records the full nominal `raiseAmount` in `totalRaised` and in `_position.raiseAmount` while actually receiving fewer tokens.
- Impact: Buyers receive sale tokens / liquidity corresponding to more raise tokens than were actually paid in. On launch, `addLiquidity` (which calls `pool.mint` with the nominal amount) will revert because the Uniswap pool will not receive the full amount, permanently locking all raised funds and sale tokens in the ILO pool. The same applies to any token whose `transferFrom` does not move exactly `value` tokens.

## `Whitelist.receive()` uses `.transfer()` with the 2300-gas stipend
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `receive`
- Mechanism: After whitelisting the sender, the contract returns the ETH with `payable(_msgSender()).transfer(msg.value)`. Solidity's `transfer` forwards only 2300 gas, which is insufficient for any smart-contract wallet or smart account that wants to self-whitelist (most post-Istanbul contracts exceed this, e.g. wallets that emit an event, update storage, or call back into the contract).
- Impact: Smart accounts that send ETH to self-whitelist will revert on the refund step. Although the whitelist entry is only persisted if the refund succeeds, the practical effect is that smart-contract users cannot use the self-whitelist flow at all, and the function can be griefed by sending ETH from a contract whose receive consumes more than 2300 gas (DoS for that user's refund / temporary ETH lock).

## `Vultisig.approveAndCall` performs the external call after setting allowance
- Location: `hardhat-vultisig/contracts/Vultisig.sol` : `approveAndCall`
- Mechanism: The function sets `_approve(msg.sender, spender, amount)` and *then* calls `IApproveAndCallReceiver(spender).receiveApproval(...)`. The spender is an arbitrary user-supplied address and the call is not protected by a reentrancy guard. In the same call the spender can re-enter the token (e.g. `transferFrom`, or `approveAndCall` again) and is trusted only to be well-behaved.
- Impact: If a user is socially engineered or phished into approving a malicious `spender` through `approveAndCall`, the spender can chain arbitrary re-entered actions (including draining the user's balance via the freshly granted allowance) before the outer call returns. This is an unavoidable property of the approve-and-call pattern, but it is worsened here because the contract does not document the trust assumption and the spender can also re-enter `VultisigWhitelisted._beforeTokenTransfer` if it is the configured `_whitelistContract`, chaining whitelist-state mutations.
