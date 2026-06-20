# Audit: 2023-10-nextgen

**Reentrancy in claim/refund paths (external calls in loop)**  
- Location: AuctionDemo.sol : claimAuction, cancelBid, cancelAllBids  
- Mechanism: claimAuction performs safeTransferFrom + multiple .call{value} (to owner + all non-winning bidders) inside a single loop after setting auctionClaim[_tokenid]=true; cancel* functions do the same .call without any ReentrancyGuard or CEI ordering. Recipients (including onERC721Received) can re-enter.  
- Impact: Attacker-controlled bidder can re-enter to manipulate bid status, cause duplicate refunds, or grief the auction settlement; funds can be drained or left inconsistent.

**Unchecked .call success allows stuck/lost funds**  
- Location: AuctionDemo.sol : claimAuction (owner payout + refunds), cancelBid, cancelAllBids  
- Mechanism: All payable sends use `(bool success,)=payable(...).call{value:...}("")` and only emit the boolean; no `require(success)` or fallback handling.  
- Impact: If any recipient reverts or has a failing fallback, the corresponding ETH is left in the contract (or the winning bidder receives the token while the artist receives nothing), resulting in permanent loss or stuck funds.

**returnHighestBidder can revert inside WinnerOrAdminRequired**  
- Location: AuctionDemo.sol : WinnerOrAdminRequired modifier + claimAuction  
- Mechanism: Modifier evaluates `msg.sender == returnHighestBidder(_tokenId)` first; returnHighestBidder reverts with "No Active Bidder" when the array contains only inactive bids.  
- Impact: A global/function admin cannot call claimAuction (or other protected functions) on an auction that has no active bidder, even though the admin check should have succeeded.

**No access-control on mintAndAuction (only function-admin gated)**  
- Location: MinterContract.sol : mintAndAuction  
- Mechanism: Function is protected solely by FunctionAdminRequired; once the minter contract is set, any function admin can mint an unlimited number of tokens directly into the auction flow and set arbitrary auctionEndTime values.  
- Impact: Privilege escalation or unauthorized high-value mints/auctions if the function-admin role is compromised or granted too broadly.

**Royalty payment re-ordering / partial failure**  
- Location: MinterContract.sol : payArtist  
- Mechanism: Zeroes collectionTotalAmount before five separate .call payouts; no reentrancy guard and no rollback on partial failure.  
- Impact: Malicious primary royalty receiver can re-enter and cause subsequent team/artist payments to be skipped or to send duplicate amounts; funds accounting becomes inconsistent.

**Oracle / randomizer trust assumption (no verification of returned hash)**  
- Location: NextGenCore.sol + Randomizer*.sol (calculateTokenHash / fulfill paths)  
- Mechanism: Core blindly accepts whatever bytes32 the configured randomizer returns and stores it in tokenToHash; no on-chain verification that the value actually came from the expected VRF/arrng response for that requestId.  
- Impact: A compromised or malicious randomizer contract can supply deterministic/predictable hashes, enabling targeted mints or front-running of reveal-dependent logic.

**Missing reentrancy protection on external collection burn/swap**  
- Location: MinterContract.sol : burnOrSwapExternalToMint  
- Mechanism: Performs IERC721.safeTransferFrom to an arbitrary burnOrSwapAddress before minting and crediting value; no guard around the external call.  
- Impact: Malicious ERC-721 implementation can re-enter and cause multiple mints or incorrect accounting for the same tokenId.

**Unbounded loops on user-controlled arrays (gas grief)**  
- Location: AuctionDemo.sol : returnHighestBid / returnHighestBidder / claimAuction / cancelAllBids (and similar loops in MinterContract)  
- Mechanism: All bid-iteration functions walk auctionInfoData[_tokenid] whose length is controlled by participants; no gas limit or pagination.  
- Impact: Attacker can submit many tiny bids to make view functions and claimAuction uncallable, permanently locking an auction.

All other findings are either style/gas or already mitigated by existing admin checks.
