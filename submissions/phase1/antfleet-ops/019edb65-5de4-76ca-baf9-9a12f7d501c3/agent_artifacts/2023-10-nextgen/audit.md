# Audit: 2023-10-nextgen

## Auction Claim Denial of Service via `returnHighestBidder` revert
- Location: `AuctionDemo.sol` : `returnHighestBidder`, `claimAuction`
- Mechanism: The `returnHighestBidder` function does not handle the case of zero active bids. If the `auctionInfoData` array is empty or all bids are inactive (e.g., the only bidder cancels before auction end), accessing `auctionInfoData[_tokenid][index]` reverts. This revert propagates through the `WinnerOrAdminRequired` modifier, permanently blocking `claimAuction`. The auction cannot be settled, and the NFT remains locked.
- Impact: An attacker (or lack of bids) can permanently lock the auctioned NFT and all associated funds, causing a complete denial of service.

## Reentrancy in `mint` Allows Bypassing Per-Address Limits
- Location: `MinterContract.sol` : `mint`
- Mechanism: The `mint` function calls `gencore.mint`, which internally calls `_safeMint`. This triggers `_checkOnERC721Received` on the recipient address. Since the per‑address mint counter (`tokensMintedPerAddress`) is updated *after* the external call, an attacker can re‑enter the `mint` function during the callback. The re‑entered call sees the still‑unchanged counter, passes the `maxAllowance` check, and mints additional tokens. The process can be repeated until the total supply is exhausted.
- Impact: An attacker can mint far more tokens than the per‑address allowance, effectively draining the entire collection supply.

## Division by Zero When `timePeriod` Is Set to Zero
- Location: `MinterContract.sol` : `getPrice`, `mint`
- Mechanism: The `setCollectionCosts` function allows an admin to set `_timePeriod` to 0. Both `getPrice` and the sales‑option‑3 logic in `mint` perform division by `timePeriod` without a zero check. Any call to `getPrice` or a mint transaction for such a collection will revert.
- Impact: Minting on the affected collection becomes permanently impossible, causing a denial of service.

## Predictable Randomness in `NextGenRandomizerNXT`
- Location: `RandomizerNXT.sol` : `calculateTokenHash`, `XRandoms.sol` : `randomNumber`, `randomWord`
- Mechanism: The randomness source relies on `block.prevrandao`, `blockhash(block.number - 1)`, and `block.timestamp`. These values are known or manipulable by miners, making the resulting token hash predictable.
- Impact: Miners can influence or predict the generated randomness, compromising the fairness of the token attribute distribution.
