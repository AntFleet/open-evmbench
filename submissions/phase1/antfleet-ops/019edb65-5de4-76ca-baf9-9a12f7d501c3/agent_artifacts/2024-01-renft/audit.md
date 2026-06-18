# Audit: 2024-01-renft

# 1. Guard policy uses wrong token ID offsets for ERC721, allowing renters to bypass rental restrictions

- **Location:** `src/libraries/RentalConstants.sol` (offsets) and `src/policies/Guard.sol` : `_checkTransaction`
- **Mechanism:** The guard inspects calldata to block transfers/approvals of rented ERC721 tokens. The hardcoded offsets for `approve(address,uint256)` and `safeTransferFrom(address,address,uint256)` are `0x44` and `0x64` respectively. The correct offsets are `0x24` (for `approve`, token ID is the second argument) and `0x44` (for `safeTransferFrom`, token ID is the third argument). Because the offsets are wrong by 32 bytes, the guard always reads the token ID from position zero (or out-of-bounds), effectively checking whether token ID 0 is rented instead of the actual token ID. As a result, any transfer or approval of an ERC721 with a token ID different from 0 is not blocked.
- **Impact:** A renter can transfer or approve a rented ERC721 NFT out of the rental safe, stealing the asset from the lender. This completely breaks the core security guarantee of the rental protocol.

# 2. PAYEE order type is not implemented, causing permanent loss of lender’s assets

- **Location:** `src/policies/Create.sol` : `_convertToItems` and `_rentFromZone`
- **Mechanism:** For PAYEE orders, `_convertToItems` only counts the number of rental and payment items but never populates the `items` array (it remains filled with default zero values). Later, `_rentFromZone` contains a branch `if (orderType.isBaseOrder() || orderType.isPayOrder())` that performs all the rental-setup logic (storage updates, escrow accounting, hook calls, event emission). Because PAYEE does not satisfy the condition, none of this logic executes. Consequently, the lender’s NFTs are transferred to the renter’s safe, the payment is sent to the escrow, but no rental order is recorded, no event is emitted, and the protocol has no way to stop the rental or reclaim the assets. The renter can permanently keep the NFTs, and the payment remains stuck in the escrow.
- **Impact:** Lenders using PAYEE orders suffer a total loss of their NFTs with no recovery path. The payment tokens are effectively locked in the escrow contract. This represents a critical loss-of-funds vulnerability.
