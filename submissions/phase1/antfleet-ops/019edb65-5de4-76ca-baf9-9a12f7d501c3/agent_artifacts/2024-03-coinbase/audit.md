# Audit: 2024-03-coinbase

We identified the following vulnerabilities during the audit:

---

## 1. MagicSpend: Unauthorized ETH withdrawal via invalid signature in `validatePaymasterUserOp`
- **Location:** `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`
- **Mechanism:** The function fails to revert when the provided withdraw request signature is invalid. Instead, it only sets the `validationData` result to indicate failure but continues to execute state-changing operations: it marks the request nonce as used and adds `withdrawAmount - maxCost` to the caller’s `_withdrawableETH` balance. Because the EntryPoint does not revert state changes made by a paymaster that returns a non-zero `validationData`, these side effects persist. An attacker can call `withdrawGasExcess` afterwards to withdraw the credited ETH.
- **Impact:** An attacker can drain the entire ETH balance of the paymaster contract by submitting a single user operation with a large `withdrawAmount` and any invalid signature.

## 2. MagicSpend: Nonce consumed before signature verification in `validatePaymasterUserOp`
- **Location:** `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`
- **Mechanism:** The internal `_validateRequest` function is called **before** the signature validity check. It marks the nonce as used and emits the `MagicSpendWithdrawal` event. If the signature is subsequently found to be invalid, the function does not revert, so the nonce remains permanently consumed even though the withdrawal was not authorized.
- **Impact:** An attacker can front-run a legitimate user operation that contains a valid withdraw request by submitting the same nonce with an invalid signature. This burns the nonce and prevents the legitimate user from ever using that request, causing a denial of service.

## 3. MagicSpend: `entryPointDeposit` ignores the `msg.value` supplied by the owner
- **Location:** `src/MagicSpend/MagicSpend.sol` : `entryPointDeposit`
- **Mechanism:** The function is declared `payable` but the `msg.value` sent with the call is never used. Instead, the `amount` parameter is transferred from the contract’s existing ETH balance. The intended behavior is likely to deposit the ETH sent with the call, but the current code withdraws from the contract’s balance instead.
- **Impact:** An owner attempting to deposit ETH by sending it with the function call will inadvertently withdraw the contract’s own funds and may drain the contract unintentionally.

## 4. FCL: Incorrect point‑at‑infinity detection in `ecAff_IsZero`
- **Location:** `src/FreshCryptoLib/FCL.sol` : `ecAff_IsZero`
- **Mechanism:** The function determines whether a point is the point at infinity by checking `y == 0`. In affine coordinates, a point with `y = 0` is a valid curve point of order 2 (if it exists), not the identity element. The library is intended for prime‑order curves (like secp256r1) where no such point exists, so this flaw is not currently exploitable. However, the code is incorrect and would fail catastrophically for any curve that contains a point with `y = 0`.
- **Impact:** If the library were used with a curve having a point of order 2, an attacker could craft a public key with `y = 0` that passes the `ecAff_isOnCurve` check but is misidentified as the point at infinity inside `ecAff_add`, leading to signature forgery. For the deployed secp256r1 curve the risk is only theoretical.

## 5. MagicSpend: Potential underflow in `postOp` when `actualGasCost > maxGasCost`
- **Location:** `src/MagicSpend/MagicSpend.sol` : `postOp`
- **Mechanism:** The calculation `withdrawable = _withdrawableETH[account] + (maxGasCost - actualGasCost)` uses unchecked subtraction. If the EntryPoint incorrectly reports an `actualGasCost` larger than the `maxGasCost` that was set during validation, the subtraction underflows, yielding a huge `withdrawable` amount.
- **Impact:** An attacker who can manipulate the EntryPoint’s gas accounting (or in the presence of an EntryPoint bug) could drain the paymaster’s entire ETH balance.

## 6. CoinbaseSmartWallet: Reentrancy risk via self‑call
- **Location:** `src/SmartWallet/CoinbaseSmartWallet.sol` : `execute` / `executeBatch`
- **Mechanism:** The `onlyEntryPointOrOwner` modifier permits the wallet itself (`msg.sender == address(this)`) to call `execute` and `executeBatch`. If the wallet ever makes a call to itself (e.g., via `execute` with `target = address(this)`), the execution context re‑enters the same function. Currently no state is modified during execution, so the risk is low, but future changes could introduce state‑dependent logic that becomes exploitable.
- **Impact:** Potential for unexpected reentrant behavior if the wallet’s state is ever modified before an external call.

---

*Note: The WebAuthn library intentionally does not verify the origin of the client data, as documented; this is a design choice, not a vulnerability.*
