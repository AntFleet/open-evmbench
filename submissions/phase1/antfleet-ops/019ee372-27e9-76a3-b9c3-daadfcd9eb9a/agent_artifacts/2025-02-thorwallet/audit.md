# Audit: 2025-02-thorwallet

## Unbounded TGT deposits can lead to contract insolvency
- Location: `MergeTgt.sol` : `onTokenTransfer`
- Mechanism: The `onTokenTransfer` function lacks a hard cap on the total amount of TGT tokens that can be exchanged for TITN. It calculates the `titnOut` proportionally based on `TITN_ARB` and `TGT_TO_EXCHANGE`. If the total circulating supply of TGT (which the codebase explicitly states is larger than `TGT_TO_EXCHANGE` in the constant's comment) is deposited, the total `titnOut` promised (`totalTitnClaimable`) will exceed the actual TITN balance deposited into the contract (`TITN_ARB`). 
- Impact: Late withdrawers or claimants will be unable to retrieve their TITN tokens. Since the contract will not have sufficient TITN reserves to honor all the newly generated claims, it leads to insolvency and arbitrary loss of funds for users who attempt to claim after the contract is drained.
