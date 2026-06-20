# Audit: 2024-03-coinbase

I audited the four contracts (the FCL secp256r1 library and the WebAuthn wrapper appear to be the standard, audited implementations and I found no exploitable deviation in them). The genuine issues are in the wallet/ownership and paymaster logic.

## Removal of the last owner permanently bricks the wallet
- Location: `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex`
- Mechanism: `removeOwnerAtIndex` deletes `isOwner[owner]` and `ownerAtIndex[index]` with the only precondition being that some owner exists at that index. There is no tracking of how many owners remain and no guard preventing removal of the final owner. Once the last owner is removed, `_checkOwner()` can never succeed again (no `isOwnerAddress(msg.sender)` will ever be true and `msg.sender == address(this)` only happens via a self-call that must itself pass `onlyEntryPointOrOwner`/`onlyEntryPoint` + a validated signature, which requires an owner). The account also cannot be re-initialized because `initialize()` reverts whenever `nextOwnerIndex() != 0`.
- Impact: All `onlyOwner` functionality (`execute`, `executeBatch`, `addOwner*`, `upgradeToAndCall`) becomes permanently unreachable, locking the account and any assets it holds forever. This is reachable both directly and — because `removeOwnerAtIndex.selector` is whitelisted in `canSkipChainIdValidation` — via cross-chain–replayable user operations.

## Any single owner can unilaterally evict all co-owners
- Location: `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex` (combined with `addOwnerAddress`/`addOwnerPublicKey`)
- Mechanism: Ownership is a flat set with no threshold, no role separation, and no protection of co-owners. A single owner (or anyone who compromises one key) can call `removeOwnerAtIndex` for every other owner's index and then add their own key, with no consent from the other owners.
- Impact: In a multi-owner ("shared custody") configuration this is a full account takeover by one party — they can remove all other owners and then drain the account via `execute`/`executeBatch`. There is no on-chain mechanism for the displaced owners to prevent or recover from this.

## Cross-chain replay of `upgradeToAndCall` (and all owner-management ops)
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `validateUserOp` / `executeWithoutChainIdValidation` (whitelist in `canSkipChainIdValidation`)
- Mechanism: For calldata targeting `executeWithoutChainIdValidation`, `validateUserOp` validates against `getUserOpHashWithoutChainId(userOp)`, which deliberately omits `block.chainid`. The whitelist permits `upgradeToAndCall`, `addOwnerAddress`, `addOwnerPublicKey`, and `removeOwnerAtIndex`. Consequently a single owner signature over one of these operations is valid on **every** chain where the account exists at the same address, and anyone observing the op can resubmit it through the EntryPoint elsewhere; the only sequencing control is the shared `REPLAYABLE_NONCE_KEY` (8453) counter, which is independent per chain.
- Impact: A signature intended for one chain (e.g. upgrading the implementation, or rotating/removing an owner) can be force-applied on other chains without the owner re-authorizing it. If the target implementation address has no code or different code on another chain, replaying `upgradeToAndCall` there can brick the account; replaying owner removals can desynchronize or lock accounts. This is an intentional design feature for state syncing, but the lack of any per-chain expiry/binding makes leaked or stale signatures dangerous.

---

Notes on things I checked and consider sound: the MagicSpend paymaster accounting (`validatePaymasterUserOp` credits `withdrawAmount - maxCost`, `postOp` adds `maxGasCost - actualGasCost`, with `delete` before transfer) conserves value and follows checks-effects-interactions; nonces are bound per `(nonce, account)` and consumed before transfer in both `withdraw()` and the paymaster path, and `getHash` binds `address(this)`, `account`, and `chainid`, so I found no replay or double-spend there. The WebAuthn `s > n/2` malleability guard covers both the RIP-7212 and FCL paths, and FCL's curve constants/range checks are correct.

