# Audit: 2024-07-benddao

## Missing Reentrancy Guard in FlashLoanERC20
- **Location:** `src/modules/FlashLoan.sol` : `flashLoanERC20`
- **Mechanism:** The `flashLoanERC20` function is not protected by the `nonReentrant` modifier, while every other state‑changing function in the protocol uses it (including `flashLoanERC721`). During the flash‑loan callback the receiver can call `flashLoanERC20` again, re‑entering the same function. This allows multiple flash loans to be outstanding simultaneously or lets the attacker call other state‑modifying functions (deposit, borrow, etc.) in an inconsistent context.
- **Impact:** An attacker can exploit the reentrancy to drain pool funds or manipulate the protocol’s accounting by repeatedly borrowing without returning the first loan, because the function does not enforce the reentrancy lock that the rest of the system relies on.

## Oracle Staleness Not Sufficiently Checked
- **Location:** `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- **Mechanism:** The function only checks `updatedAt != 0` and `answeredInRound >= roundId`. It does not verify that `updatedAt` is within a reasonable heartbeat window. If Chainlink stops updating a price feed, the oracle would return a stale price indefinitely.
- **Impact:** An attacker can use an outdated price to borrow against overvalued collateral or to liquidate healthy positions, potentially causing loss of funds.

## Incorrect Event Emitted in AddressProvider
- **Location:** `src/AddressProvider.sol` : `setDelegateRegistryV2`
- **Mechanism:** The function emits `YieldRegistryUpdated` instead of a dedicated event for the delegate registry update.
- **Impact:** Off‑chain monitoring systems that rely on the correct event may fail to detect when the delegate registry is changed, which could lead to missed updates and integration issues.
