# Audit: 2025-02-thorwallet

## Lack of Deposit Cap Leading to Insolvency
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`
- Mechanism: The `onTokenTransfer` function calculates the `titn` payout using a fixed exchange rate via `quoteTitn()` without verifying if the cumulative `titn` credited exceeds the contract's actual `titn` reserve (`TITN_ARB`). Because there is no cap on the total amount of `tgt` that can be deposited into the contract, if users collectively deposit more than `TGT_TO_EXCHANGE` (579,000,000) tokens, the total claimable `titn` will mathematically exceed the 173,700,000 `titn` reserve held by the contract.
- Impact: The contract becomes insolvent. Early users who claim their `titn` will drain the reserve, causing `claimTitn` and `withdrawRemainingTitn` to revert for all subsequent users due to an insufficient `titn` balance in the contract. This results in a permanent loss of funds for later participants who deposited `tgt` but cannot withdraw their proportional `titn`.
