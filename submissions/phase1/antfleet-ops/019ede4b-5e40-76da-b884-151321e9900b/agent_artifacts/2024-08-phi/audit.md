# Audit: 2024-08-phi

## Reentrancy in `buyShareCred` Bypasses Share Lock Period
- Location: `src/Cred.sol` : `buyShareCred` / `_handleTrade`
- Mechanism: The `buyShareCred` and `sellShareCred` functions lack a `nonReentrant` modifier. In `_handleTrade`, when executing a buy, the user's share balance is updated and any excess ETH is refunded to `_msgSender()` *before* the `lastTradeTimestamp` is updated. An attacker can use a smart contract to receive the refund and re-enter `sellShareCred` during the same transaction. Because `lastTradeTimestamp` hasn't been updated yet, the `SHARE_LOCK_PERIOD` check uses the old timestamp (or 0), allowing the attacker to immediately sell the newly purchased shares.
- Impact: Complete bypass of the 10-minute share lock period. An attacker can instantly buy and sell shares in a single transaction, enabling price manipulation or draining of the contract's ETH balance if the sell price is favorable.

## Reentrancy in `claim` Allows Infinite Minting and Bypasses `tx.origin` Check
- Location: `src/PhiFactory.sol` : `claim` / `signatureClaim` / `merkleClaim`
- Mechanism: The `claim` function lacks a `nonReentrant` modifier and makes an external call to `this.signatureClaim` or `this.merkleClaim`. These internal external-calls pass the `tx.origin` protection check because `msg.sender == address(this)`. Furthermore, `_validateAndUpdateClaimState` does not revert if `artMinted` or `credMinted` is already true, nor does it consume a nonce. `_processClaim` sends a refund to `_msgSender()` before making the external call to the art contract. An attacker contract can call `claim`, receive the refund, and re-enter `claim` repeatedly. This bypasses the `tx.origin` smart-contract restriction and allows the attacker to reuse the same signature or Merkle proof.
- Impact: An attacker can drain the entire NFT supply of an art collection up to `maxSupply` using a single valid signature or Merkle proof, completely breaking minting limits and fairness.

## Denial of Service in `CuratorRewardsDistributor` due to `EnumerableMap` Key Accumulation
- Location: `src/Cred.sol` : `_updateCuratorShareBalance`
- Mechanism: When a user sells all their shares, `_updateCuratorShareBalance` calls `shareBalance[credId_].set(sender_, 0)`. OpenZeppelin's `EnumerableMap.set` does not remove the key from the underlying `EnumerableSet` when the value is set to 0; it merely updates the value. The key remains in the map, meaning `shareBalance[credId_].length()` will monotonically increase and never decrease. When `CuratorRewardsDistributor.distribute` calls `getCuratorAddresses`, the view function iterates over all historical keys (including those with 0 balance) to filter them out. 
- Impact: As the number of historical holders grows, the iteration in `getCuratorAddresses` will eventually exceed the block gas limit. This will cause `distribute` to permanently revert with an Out-of-Gas error, permanently locking all curator rewards for that specific `credId`. The contract should use `shareBalance[credId_].remove(sender_)` instead of setting the value to 0.
