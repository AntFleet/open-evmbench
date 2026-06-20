# Audit: 2025-05-blackhole

## Bypassing Maximum NFTs Per Wallet via Reentrancy
- Location: `contracts/Thenian.sol` : `mintPublic`
- Mechanism: The `mintPublic` function limits the number of NFTs a user can mint by checking `require(balanceOf(msg.sender).add(amount) <= 15)`. However, the minting process itself (`_mintTo`) uses `_safeMint(account, totalSupply())` inside a loop, which calls the `onERC721Received` hook on the receiver (if it is a smart contract) after each individual NFT is minted. A malicious contract can exploit this callback: during the first iteration of the `_mintTo` loop, the contract calls back into `mintPublic`. Because the remaining NFTs from the initial transaction have not yet been minted, the attacker's `balanceOf` is low enough to successfully pass the wallet limit check again.
- Impact: A malicious actor can bypass the maximum limit of 15 NFTs per wallet, allowing them to mint significantly more NFTs than intended and monopolizing tokens during the public sale.
