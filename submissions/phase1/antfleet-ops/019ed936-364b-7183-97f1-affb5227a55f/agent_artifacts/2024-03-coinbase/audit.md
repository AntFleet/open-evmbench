# Audit: 2024-03-coinbase

## Consensus findings

## Chain-agnostic operation signatures are replayable across chains via `executeWithoutChainIdValidation`
*(consensus — Reviewer A framed via owner removal, Reviewer B framed via upgrade; same root cause and code path)*
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `executeWithoutChainIdValidation` (A ~213–221 / B ~184–193), `canSkipChainIdValidation` (A ~272–284 / B ~238–247); downstream `MultiOwnable.removeOwnerAtIndex` / `MultiOwnable._addOwner` (A) and `_authorizeUpgrade` / `UUPSUpgradeable.upgradeToAndCall` (B ~316–319)
- Mechanism: `executeWithoutChainIdValidation` validates the op against `getUserOpHashWithoutChainId` with `block.chainid` stripped, so any signed op invoking it is replayable on every chain where the account exists at the same address. `canSkipChainIdValidation` whitelists `addOwnerAddress`, `addOwnerPublicKey`, `removeOwnerAtIndex(uint256)`, and `UUPSUpgradeable.upgradeToAndCall.selector`. Both reviewers identify this chain-id omission as the root cause; each follows it down a different whitelisted selector:
  - (Reviewer A) `_addOwner` assigns indices from a per-chain `nextOwnerIndex` counter, so owner→index mappings diverge across chains whenever any prior owner action was not applied identically everywhere. A replayed `removeOwnerAtIndex(n)` then deletes whatever owner happens to occupy index `n` on each chain — possibly a different owner (or none) per chain — and a replayed add can land at a different index than intended.
  - (Reviewer B) The signed `upgradeToAndCall` calldata contains only the implementation address, with no code hash or chain-specific binding. The same address can hold benign code on one chain and attacker-controlled code on another.
- Impact: A single valid owner signature (not attacker-forgeable), once it exists, can be replayed by anyone on other chains where the account is deployed at the same address, producing outcomes the signer did not authorize:
  - (A) Owner sets silently diverge across chains; a removal intended for one key can drop a different key on another chain, potentially removing the only remaining valid owner there (bricking that instance — see the single-reviewer finding below).
  - (B) The wallet can be upgraded to attacker-controlled implementation code on a chain where the implementation address resolves to unsafe code, enabling full account takeover.

## Additional findings (single-reviewer)

## Wallet can be permanently bricked by removing the last owner
*(Reviewer A only)*
- Location: `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex` (whole function, ~lines 120–129)
- Mechanism: `removeOwnerAtIndex` deletes `isOwner[owner]` and `ownerAtIndex[index]` with no invariant that at least one owner must remain — there is no owner count and no "is this the last owner" guard. Once the final owner is removed, `_checkOwner()` reverts for every external caller and `_validateSignature` reverts with `InvalidOwnerBytesLength` (because `ownerAtIndex` returns empty), so `validateUserOp`, `execute`, `executeBatch`, `addOwner*`, and `_authorizeUpgrade` (UUPS) can never again succeed.
- Impact: The account becomes permanently inoperable and any ETH/tokens it holds are irrecoverable. Reachable by a single owner action — or, notably, by a self-call routed through `executeWithoutChainIdValidation`, which whitelists `removeOwnerAtIndex.selector` (compounding with the consensus replay finding above). Not externally exploitable by a non-owner, but it is an unguarded total-loss path with no recovery.

## Paymaster gas allowance can be withdrawn directly
*(Reviewer B only)*
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `withdraw`, `getHash` (~113–148, ~188–201, ~267–281)
- Mechanism: The same signed `WithdrawRequest` hash is accepted by both the ERC-4337 paymaster flow and the direct `withdraw()` flow. In `validatePaymasterUserOp`, `amount` is treated as a total budget where up to `maxCost` pays gas and only the remainder is credited to the user. In `withdraw()`, the exact same signed request transfers the full `amount` directly to `msg.sender`, with no domain separation or field indicating "paymaster-only" use. (Note: Reviewer A assessed this same area and judged it sound, citing nonce burning in `_validateRequest` as blocking double-spend between the two paths; B's claim is not a double-spend but a path-selection bypass, which the nonce burn does not prevent.)
- Impact: A user holding a valid owner-signed request intended to sponsor a UserOperation can bypass the paymaster path and call `withdraw()` instead, receiving the gas reserve as spendable ETH. Preconditions: the signer issues requests where `amount` includes a gas budget that was not intended to be paid directly to the user.

