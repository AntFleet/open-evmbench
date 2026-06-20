# Audit: 2024-08-wildcat

 Here is the security audit of the provided smart-contract codebase, detailing the vulnerabilities discovered.

---

## 1. Compliance and Freezing DOS inside `nukeFromOrbit` for Fixed-Term Markets
- Location: `WildcatMarketConfig.sol : nukeFromOrbit` & `WildcatMarketWithdrawals.sol : _queueWithdrawal`
- Mechanism: The function `nukeFromOrbit` is designed to be called by the `sentinel` to immediately freeze and sequester a sanctioned lender's balance, moving it to a safe escrow. However, `_blockAccount` implements this by programmatically calling the internal `_queueWithdrawal` function to force-withdraw the block list target's full balance. If the market is utilizing the `FixedTermLoanHooks` template, this force-withdrawal interacts with `onQueueWithdrawal`, which unconditionally restricts withdrawals before the loan fixed term has elapsed (`market.fixedTermEndTime > block.timestamp`).
- Impact: A sanctioned entity's funds cannot be frozen or sequestered during the active fixed-term phase of the loan. The call to `nukeFromOrbit` will always revert when triggered, completely bypassing the regulatory compliance requirements promised by the Wildcat protocol.

---

## 2. Denial of Service on Contiguous Protocol Fee Updates due to closed or unchanged markets
- Location: `HooksFactory.sol : pushProtocolFeeBipsUpdates`
- Mechanism: The factory allows the administrator to push protocol fee adjustments to existing markets deployed from a specified template in contiguous ranges using `pushProtocolFeeBipsUpdates`. During the loop, the factory makes an external call to `setProtocolFeeBips()` on each market. If any single market in the range reverts (which occurs if the market has already been closed via `closeMarket` or if its fee remains unchanged and throws `ProtocolFeeNotChanged`), the entire transaction reverts.
- Impact: If even a single market in the historical deployment list is closed or already possesses the identical fee rate, updating any contiguous array of markets that spans across it is completely blocked. This forces the protocol admin to parse and split updates into disjoint, highly inefficient sub-intervals, creating a permanent barrier to global updates.

---

## 3. Storage Corruption in `LibTransientBytesArray` due to dirty padding bytes
- Location: `TransientBytesArray.sol : LibTransientBytesArray : write`
- Mechanism: In `write`'s `case 1` (which handles short byte arrays with lengths $< 32$), the library reads the first 32 bytes of the array data from memory via `let data := mload(memoryPointer)` and attempts to bitwise-OR it with the length byte (`or(data, lengthByte)`). Because the last byte of `data` (where `lengthByte` resides) is not masked out to zero before performing the OR operation, any dirty memory or uninitialized padding bytes residing at the end of the short array in memory will be preservation-ORed into the slot.
- Impact: If the 32nd byte of the source memory contains a non-zero value where the least significant bit is set (`1`), reading the array back via `readToPointer` will erroneously treat the short array as an out-of-place long byte array. This causes its internal logic helper `extractByteArrayLength` to evaluate `eq(outOfPlaceEncoding, lt(length, 32))` as true, generating an immediate transaction panic revert (`0x22`), and permanently preventing reads of the transient storage slot.
