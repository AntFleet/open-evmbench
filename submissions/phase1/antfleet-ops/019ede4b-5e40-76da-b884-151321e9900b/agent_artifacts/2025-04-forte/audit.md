# Audit: 2025-04-forte

## EVM Execution Halt on Square Root of Zero
- Location: `src/Float128.sol` : `sqrt`
- Mechanism: Inside the inline assembly block, when the input `a` is zero, the code executes the `stop()` opcode (`if iszero(a) { stop() }`). In Yul/EVM, `stop()` immediately halts the entire EVM execution and returns a successful status with empty return data, rather than returning from the function or reverting the transaction. 
- Impact: If any smart contract logic invokes `Float128.sqrt(0)` (e.g., calculating standard deviation, variance, or any intermediate math that can evaluate to zero), the transaction will abruptly terminate at that exact instruction. All state changes made prior to the call will be permanently committed, but all subsequent execution flow—including critical balance updates, token transfers, state validations, and security checks—will be completely skipped. This silent execution halt can lead to severe state corruption, bypassed invariants, and direct loss of funds.
