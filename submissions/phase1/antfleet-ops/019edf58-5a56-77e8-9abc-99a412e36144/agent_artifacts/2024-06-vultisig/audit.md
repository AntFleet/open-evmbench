# Audit: 2024-06-vultisig

# Security Audit Report

## 1. Broken Fee Accounting in ILOPool.claim() — Subsequent Users Cannot Claim

- **Location:** `src/ILOPool.sol` : `claim()`
- **Mechanism:** All investors' liquidity is deposited into a single Uniswap V3 position (same owner = ILOPool contract, same tick range). When `claim()` is called, it burns liquidity and calls `pool.collect(type(uint128).max, …)`, which drains **all** accumulated fees from the shared position into the contract. The function then distributes fees to the caller based on an internal `feeGrowthInside0LastX128` that starts at **0** for every NFT and is never seeded with the pool position's initial `feeGrowthInside` at launch time. After the first user claims and collects all pool fees, the pool's `tokensOwed` is empty. When a second user calls `claim()`, `pool.collect()` returns only the principal (zero fees), but the internal calculation still yields `fees = (currentFeeGrowth − 0) × userLiquidity / Q128 > 0`. The subsequent `amountCollected0 − amount0` (and `amountCollected1 − amount1`) **underflows** and reverts.
- **Impact:** After the first investor claims, no other investor can ever claim their vested liquidity and fees. All remaining investors' funds are permanently locked. Additionally, the first claimant receives a fee share calculated against the **entire** pool's fee growth (from position creation) rather than only their pro-rata portion, so fees are misallocated.

---

## 2. Permanent DoS of Project Launch via Uniswap Pool Price Manipulation

- **Location:** `src/ILOManager.sol` : `launch()` and `_initUniV3PoolIfNecessary()`
- **Mechanism:** `initProject()` creates and initializes a Uniswap V3 pool with `initialPoolPriceX96` but adds **no liquidity** until `launch()` is called later. Between these two transactions the pool has zero liquidity. An attacker can deploy a trivial callback contract and call `pool.swap()` with a non-zero `amountSpecified` and `sqrtPriceLimitX96 = MIN_SQRT_RATIO` (or `MAX_SQRT_RATIO`). With zero liquidity, `SwapMath.computeSwapStep` moves `sqrtPriceX96` to the limit with zero token input/output—the attacker pays nothing. The `launch()` function requires `_cachedProject[uniV3PoolAddress].initialPoolPriceX96 == sqrtPriceX96` (read from `slot0`), which now permanently fails. Uniswap V3 pools can only be initialized once, and `initProject` prevents re-caching, so the DoS is irreversible.
- **Impact:** An attacker can permanently prevent any project from launching at zero cost, trapping all investor raise funds until the refund deadline.

---

## 3. Self-Whitelist DoS for Contract Addresses via 2300-Gas `transfer()`

- **Location:** `hardhat-vultisig/contracts/Whitelist.sol` : `receive()`
- **Mechanism:** The `receive()` function refunds the sent ETH using `payable(_msgSender()).transfer(msg.value)`, which forwards only 2300 gas. If the caller is a contract whose `receive()`/`fallback()` requires more than 2300 gas (e.g., a multisig wallet, proxy, or contract with logging), the transfer reverts and the entire self-whitelist transaction fails.
- **Impact:** Contract addresses (multisigs, smart wallets) cannot self-whitelist, denying them participation in the token sale.

---

## 4. Token Recipient Mismatch via Reentrancy in claim()

- **Location:** `src/ILOPool.sol` : `claim()`
- **Mechanism:** `claim()` transfers token0 and token1 to `ownerOf(tokenId)` in two separate `safeTransfer` calls, reading `ownerOf` inline each time rather than caching the owner. If token0 is a non-standard ERC20/ERC777 with transfer callbacks (or the recipient is a contract that receives tokens via a hook), the recipient can reenter during the first `safeTransfer` and transfer the NFT to a different address. The second `safeTransfer` then sends token1 to the new owner. There is no reentrancy guard and no owner caching. State updates (liquidity/feeGrowth) do occur before transfers, preventing double-claiming, but the recipient divergence is not prevented.
- **Impact:** If token0 has transfer hooks or the NFT owner is a malicious contract, token1 can be diverted to an address that did not own the position at the start of `claim()`, causing loss of funds for the legitimate owner.

---

## 5. approveAndCall Silently Succeeds for EOA Spenders

- **Location:** `hardhat-vultisig/contracts/Vultisig.sol` : `approveAndCall()`
- **Mechanism:** `approveAndCall` calls `IApproveAndCallReceiver(spender).receiveApproval(…)` without verifying that `spender` has code. A low-level `call` to an EOA (address with no code) returns `success = true` and empty data, so the function sets the approval and returns `true` even though the intended callback was never executed. The caller may believe the spender contract received and processed the approval when it did not.
- **Impact:** Users interacting with an incorrectly-specified EOA address will have their tokens approved for that address without the expected callback logic executing, potentially leading to unintended approvals to arbitrary addresses.
