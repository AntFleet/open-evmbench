# Audit: 2024-08-phi

## Signed claims can mint arbitrary quantities and be replayed across chains
- Location: `src/PhiFactory.sol : claim -> signatureClaim`
- Mechanism: `claim()` decodes `quantity_` and `imageURI_`, but rebuilds `claimData` for signature verification without either field. `signatureClaim()` then verifies only `(expiresIn, minter, ref, verifier, artId, chainId, data)` and even ignores the decoded `chainId` field after verification. On top of that, `_validateAndUpdateClaimState()` sets `artMinted` / `credMinted` but never checks them, so the same signed authorization is never consumed. A claimant can therefore reuse one valid signature repeatedly, choose any `quantity_` each time, and replay the same signature on another deployment/chain that uses the same signer.
- Impact: Any holder of one valid signature can mint arbitrary amounts up to the collection max supply, exhaust scarcity, and replay the same authorization on unintended chains.

## Merkle claims are unlimited and quantity-unbound
- Location: `src/PhiFactory.sol : merkleClaim`
- Mechanism: The Merkle leaf is verified only over `keccak256(abi.encode(minter_, leafPart_))`. The claimed `quantity_`, `artId_`, `ref_`, and `imageURI_` are not bound into the proven leaf. `_validateAndUpdateClaimState()` again records `artMinted` / `credMinted` without enforcing one-time use. A whitelisted address can therefore submit the same proof over and over, and can choose any `quantity_` on each call.
- Impact: Any allowlisted address can mint far more NFTs than intended, including draining the full remaining supply of a drop.

## Merkle eligibility for one art can be overwritten by creating another art on the same cred
- Location: `src/PhiFactory.sol : _initializePhiArt`
- Mechanism: Merkle roots are stored in `credMerkleRoot[credChainId][credId]`, while `merkleClaim()` reads the root back using only that cred-level key. The root is not stored per `artId`. Creating a later art for the same `(credChainId, credId)` overwrites the root used by all prior MERKLE-gated arts tied to that cred.
- Impact: A later art creator can replace the allowlist for an existing drop, either locking out legitimate claimants or authorizing a different set of addresses to claim an older art.

## Anyone can corrupt curator position bookkeeping and block full exits
- Location: `src/Cred.sol : _addCredIdPerAddress / _removeCredIdPerAddress`
- Mechanism: Both bookkeeping helpers are `public` and mutate another user’s `_credIdsPerAddress` / index mappings with no authorization, but they do not update the real share balance or `_credIdExistsPerAddress`. An attacker can call `_removeCredIdPerAddress(credId, victim)` while the victim still holds shares. Later, when the victim tries to sell their final share, `_updateCuratorShareBalance()` calls `_removeCredIdPerAddress()` again and hits `EmptyArray`, `IndexOutofBounds`, or `WrongCredId`, reverting the exit.
- Impact: Any account can grief holders, corrupt portfolio views, and trap victims in positions they cannot fully close.

## Historical shareholders are never removed from the share map
- Location: `src/Cred.sol : _updateCuratorShareBalance`
- Mechanism: When a holder sells down to zero, the contract calls `shareBalance[credId_].set(sender_, 0)` instead of removing the key from the `EnumerableMap`. As a result, `shareBalance[credId].length()` grows monotonically with every historical holder. `_getCuratorData()` and downstream consumers such as `CuratorRewardsDistributor.distribute()` must iterate that ever-growing map, even though most entries are zero-balance ghosts.
- Impact: An attacker can sybil-buy and later exit from many addresses to permanently bloat a cred’s holder set, eventually making shareholder enumeration and curator reward distribution too expensive or impossible to execute.

## Buy refunds allow same-transaction reentrancy to bypass the share lock
- Location: `src/Cred.sol : _handleTrade`
- Mechanism: Single-share trades are not protected by `nonReentrant`. In the buy path, the contract updates the buyer’s balance and `currentSupply`, then sends any excess ETH refund to `_msgSender()`, and only after that writes `lastTradeTimestamp[credId_][curator_] = block.timestamp`. A contract buyer can intentionally overpay by 1 wei, reenter from its refund fallback, and call `sellShareCred()` before the timestamp is set, so the `SHARE_LOCK_PERIOD` check still sees zero/old state.
- Impact: A contract buyer can buy and immediately sell in the same transaction, defeating the intended 10-minute holding lock and enabling same-tx supply/position manipulation.

