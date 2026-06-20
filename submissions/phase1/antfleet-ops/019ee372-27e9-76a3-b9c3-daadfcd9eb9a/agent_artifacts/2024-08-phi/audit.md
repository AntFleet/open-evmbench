# Audit: 2024-08-phi

An analysis of the codebase reveals the following security vulnerability:

## Vulnerable `claim` function allows minting with the factory's ETH balance
- Location: `src/PhiFactory.sol` : `claim`
- Mechanism: The `claim` function receives encoded claim data for either Merkle-based or Signature-based mints. It decodes the expected `mintFee` and subsequently invokes an external call to itself using `this.merkleClaim{ value: mintFee }(...)` or `this.signatureClaim{ value: mintFee }(...)`. However, the `claim` function lacks any check to ensure that the user providing the transaction actually sent at least `mintFee` in `msg.value`. Consequently, the external call pulls the `mintFee` from the `PhiFactory` contract's existing ETH balance. 
ETH can easily accumulate in the `PhiFactory` because `createArt` forwards its entire `msg.value` to `PhiNFT1155.createArtFromFactory`, which then refunds any excess ETH back to `PhiFactory` (as `_msgSender()`). Because `PhiFactory` does not return this refund to the original `createArt` caller, the funds become trapped in the factory. 
- Impact: An attacker can call `claim()` with `msg.value = 0` to mint NFTs for free, bypassing the actual cost and draining the trapped ETH funds from the `PhiFactory` contract. Any user who overpaid during art creation will permanently lose their excess ETH.
