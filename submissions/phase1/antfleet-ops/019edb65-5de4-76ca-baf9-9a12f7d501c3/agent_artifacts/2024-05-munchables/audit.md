# Audit: 2024-05-munchables

## SnuggeryManager: Duplicate NFT import allows inflating chonk and stealing rewards

- **Location:** `src/managers/SnuggeryManager.sol` : `importMunchable`
- **Mechanism:** The `importMunchable` function does not check whether the token is already present in the caller’s snuggery. An attacker can repeatedly import the same NFT (by exporting it and importing again, or by calling `importMunchable` multiple times while the NFT is already inside). Each call pushes a new `SnuggeryNFT` entry for the same `tokenId` into the `snuggeries` array. The `_recalculateChonks` function, which runs after every state‑changing action, sums the `chonks` of **all** entries, including duplicates. This inflates the player’s total chonk and the global `totalGlobalChonk`. The `ClaimManager._claimPoints` function uses these inflated totals to compute reward shares, allowing the attacker to claim a disproportionate amount of the period’s points.
- **Impact:** An attacker can siphon the majority of each claim period’s reward pool by artificially boosting their own chonk, stealing points from legitimate users.

## SnuggeryManager & AccountManager: Out‑of‑bounds array access in pagination functions

- **Location:** `src/managers/SnuggeryManager.sol` : `getSnuggery`  
  `src/managers/AccountManager.sol` : `getSubAccounts`
- **Mechanism:** Both functions return a slice of data using a fixed‑size memory array and a `_start` offset. The loop index `i` is used directly to write into the returned array (`_snuggery[i]` or `_subAccounts[i]`), but `i` begins at `_start`. If `_start` is non‑zero, the assignment writes beyond the array’s length (e.g., `_start=5` writes to index 5, then 6, …, eventually exceeding 19), causing an out‑of‑bounds revert. The correct assignment should use `i - _start`.
- **Impact:** Any off‑chain component or user that attempts to paginate results (e.g., fetching the second page of a snuggery or sub‑account list) will always hit a revert, effectively denying access to the data and breaking front‑end functionality.

## RewardsManager: WETH yield is claimed using the USDB address

- **Location:** `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- **Mechanism:** When claiming WETH yield from a contract, the code mistakenly calls  
  `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH);`  
  instead of passing `address(WETH)`. This attempts to claim USDB tokens with the WETH amount, which will almost certainly revert (or, if the contract has a permissive implementation, move USDB rather than WETH). The WETH yield remains unclaimed and is effectively lost.
- **Impact:** The protocol cannot collect WETH yield from its contracts. Unclaimed WETH accumulates and cannot be forwarded to the yield distributor, resulting in permanent loss of WETH revenue.

## SignatureVerifier library: Signature recovery condition always rejects valid signatures

- **Location:** `src/libraries/SignatureVerifier.sol` : `recover`
- **Mechanism:** The condition `if (v != 27 || v != 28)` is logically always true (a single `v` value cannot be simultaneously equal to both 27 and 28). The intended check should be `if (v != 27 && v != 28)`. As a result, **every** call to `recover` will revert with `InvalidSignature()`, even for correctly formed signatures.
- **Impact:** Although the library is not used in the current codebase, any future integration that relies on this signature verification (e.g., off‑chain reveal signatures) will be permanently broken; all valid signatures would be rejected.
