# Audit: 2024-08-phi

**_addCredIdPerAddress and _removeCredIdPerAddress are public with no access control**  
- Location: `src/Cred.sol` : `_addCredIdPerAddress`, `_removeCredIdPerAddress` (and callers `_updateCuratorShareBalance`)  
- Mechanism: The two helper functions that mutate `_credIdsPerAddress`, `_credIdsPerAddressCredIdIndex`, `_credIdExistsPerAddress` and `_credIdsPerAddressArrLength` are declared `public` (instead of `internal`) and contain no `msg.sender` or role checks. `_updateCuratorShareBalance` (called from both single-trade and batch paths) unconditionally invokes them.  
- Impact: Any attacker can arbitrarily add/remove arbitrary credIds for any curator address, corrupting `getPositionsForCurator`, `getCuratorAddresses*`, `isShareHolder` results and the internal accounting used by `batchSell` and reward distribution.

**Missing reentrancy protection on `_handleTrade` (single buy/sell)**  
- Location: `src/Cred.sol` : `_handleTrade` (buy path: excess refund; sell path: curator payout)  
- Mechanism: The only `nonReentrant` modifier is applied to batch functions. Inside `_handleTrade` the contract performs `safeTransferETH` to `msg.sender` (buy excess) or `curator_` (sell proceeds) *before* the protocol-fee and creator-fee transfers, and without re-locking `locked`. The external `phiRewards.deposit` call follows.  
- Impact: A malicious curator or buyer contract can re-enter on ETH receipt, observe inconsistent state (shares already updated, supply updated, but fees not yet sent) and potentially cause fee theft, double-crediting, or bypass the share-lock-period check on a subsequent call.

**Creator/curator can be forced to pay protocol fee on a zero-price sell**  
- Location: `src/Cred.sol` : `_handleTrade` (sell branch) + `BondingCurve.getPriceData`  
- Mechanism: When `supply == amount` the bonding-curve price becomes zero, yet the sell path still subtracts `protocolFee` and `creatorFee` computed from the (now-zero) price and then performs `curator_.safeTransferETH(price - protocolFee - creatorFee)` (underflow risk is masked by the later `safeTransferETH` of the fees themselves). The check `price - protocolFee - creatorFee < priceLimit` can be satisfied with a zero `priceLimit`.  
- Impact: Attacker can sell the last share for free while the protocol and creator still receive (or attempt to receive) a non-zero fee, draining the contract or causing failed transfers.

**Batch sell does not enforce the share-lock period for every trade**  
- Location: `src/Cred.sol` : `_executeBatchTrade` (sell path) vs. single-trade path in `_handleTrade`  
- Mechanism: The lock-period check (`lastTradeTimestamp[credId][curator] + SHARE_LOCK_PERIOD`) exists only inside the single-trade `_handleTrade` and inside the per-cred loop of `_executeBatchTrade`. However the batch path reads `lastTradeTimestamp` *after* the first loop that already updated balances, and the check is performed with the *current* block timestamp for every item independently.  
- Impact: An attacker that buys and immediately batch-sells the same cred in one transaction (or across two calls in the same block) can bypass the intended 10-minute lock for some of the batch items because the timestamp update happens inside the same non-reentrant block.

**Signature expiration uses `block.timestamp` but is only checked at claim/create time**  
- Location: `src/Cred.sol` : `createCred`, `updateCred`; `src/PhiFactory.sol` : `signatureClaim`, `_validateArtCreationSignature`  
- Mechanism: All signed payloads contain an `expiresIn` field that is compared with `block.timestamp` only when the signature is first presented. After that point the signed data (including the credId/amount) is stored only in transient call data; nothing prevents a later replay within the same block or after a timestamp change.  
- Impact: A signature that was valid at submission time can be replayed by a front-runner or by the same caller in a subsequent transaction before the block is mined, allowing duplicate mints/claims or duplicate share purchases.

**PhiFactory `claim` / `batchClaim` allow arbitrary re-entrancy into the same contract**  
- Location: `src/PhiFactory.sol` : `claim`, `batchClaim`, `signatureClaim`, `merkleClaim`  
- Mechanism: `claim` performs an external call to `this.signatureClaim` or `this.merkleClaim` (i.e., `CALL` to self) while holding the caller's ETH value. No `nonReentrant` guard exists on these functions (only on `createArt`). The internal `_processClaim` performs further external calls to the art contract and to `phiRewards`.  
- Impact: An attacker can craft a malicious art contract or use a re-entrant token that calls back into `claim`/`batchClaim`, causing multiple mints, double fee collection, or draining of the accumulated `msg.value` before the per-art state (`artMinted`, `numberMinted`) is updated.

**No check that `curator_` in `buyShareCredFor` is not the zero address inside the batch path**  
- Location: `src/Cred.sol` : `buyShareCredFor` (explicit check) vs. `batchBuyShareCred` → `_executeBatchBuy` → `_executeBatchTrade`  
- Mechanism: The single-function `buyShareCredFor` reverts on `curator_ == address(0)`, but the batch buy path only performs the zero-address check inside `_executeBatchTrade` *after* price validation and only for the supplied `curator` argument. The batch function accepts an arbitrary `curator_` that can be zero.  
- Impact: Batch buy can be used to buy shares “for” the zero address, permanently locking the shares and protocol fees with no way to recover them.

All of the above are exploitable logic/access-control or re-entrancy issues that can result in loss of funds, corrupted state, or unauthorized minting/claiming. No other high-severity vulnerabilities (price oracle manipulation, integer overflow under 0.8.25, storage collisions, etc.) were identified.
