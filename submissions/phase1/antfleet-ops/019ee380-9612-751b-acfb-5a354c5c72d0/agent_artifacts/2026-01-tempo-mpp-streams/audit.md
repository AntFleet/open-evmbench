# Audit: 2026-01-tempo-mpp-streams

Below are the genuine security vulnerabilities I found in `TempoStreamChannel.sol`.

## Voucher signatures can be forged when `authorizedSigner` is the zero address
- Location: `contracts/TempoStreamChannel.sol` : `openChannel` / `settle` / `_recoverSigner`
- Mechanism: `openChannel` never validates `authorizedSigner != address(0)`, so a channel can be created with `authorizedSigner == address(0)`. `_recoverSigner` returns `address(0)` for any signature that `ecrecover` cannot resolve (e.g. an out-of-range `v`, or any garbage 65-byte blob), and it never rejects that result. In `settle` the only authorization check is `if (signer != channel.authorizedSigner) revert InvalidSigner();`. When `authorizedSigner` is zero, a forged/garbage signature recovering to `address(0)` satisfies this equality check.
- Impact: For any channel opened with a zero `authorizedSigner` (an easy footgun, since the field is meant to be an optional delegate), `settle` is fully permissionless and the signature gate is bypassed. An attacker can submit a forged voucher with `cumulativeAmount == deposit` and drain the entire deposit to `channel.payee`. The same `address(0)` acceptance flaw also applies to the `close` path.

## `initiateClose` has no access control
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose`
- Mechanism: The function only checks that the channel exists, is not finalized, and has no active grace period. It does not verify that `msg.sender` is the payer or payee. Any external account can call it for any channel.
- Impact: An arbitrary third party can force any active streaming channel into its closure grace period at will. This caps the payee’s settlement window to `GRACE_PERIOD` (1 hour) without the payer’s or payee’s intent, enabling griefing of long-lived streaming channels and pushing channels toward premature finalization/refund.

## `deadline` parameter in `openChannel` is never enforced
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`
- Mechanism: `openChannel` accepts a `uint256 deadline` argument and the contract even defines a `DeadlineExpired()` error, but the function body never compares `block.timestamp` against `deadline`. The intended staleness protection is silently dropped.
- Impact: A signed/pending channel-open transaction provides no expiry guarantee. It can be mined arbitrarily late (e.g. after sitting in the mempool), opening a channel and pulling `deposit` tokens from the payer at a time the payer no longer intends, with no way to bound execution timing as the API contract implies.

## `close` skips voucher expiry and nonce validation (and uses a domain-less payer signature)
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: Unlike `settle`, the cooperative `close` path verifies neither `voucher.expiry` (no `block.timestamp > expiry` check) nor `voucher.nonce` against `settledNonces`. It therefore accepts expired and out-of-order vouchers. Additionally, the payer authorization is a non-EIP-712 message `keccak256("CLOSE", channelId, cumulativeAmount)` that omits any chainId, contract address, nonce, or expiry.
- Impact: The cooperative-close guarantees are weaker than the streaming path: stale/expired vouchers can be replayed into a final settlement, and the payer’s `CLOSE` authorization is a long-lived, non-expiring approval bound only to `(channelId, cumulativeAmount)`. Because `channelId` is derived from `block.timestamp`/`channelCounter` it is effectively chain-specific, but the missing domain binding and missing expiry still allow a previously issued payer close-authorization to be redeemed later than the payer intended.

## Signature malleability in `_recoverSigner`
- Location: `contracts/TempoStreamChannel.sol` : `_recoverSigner`
- Mechanism: The raw `ecrecover` is used with no low-`s` normalization and no validation that `v ∈ {27,28}`. This is the well-known ECDSA malleability: for a valid signature `(r,s,v)` a second valid signature `(r, n−s, v′)` exists for the same message.
- Impact: Limited here because vouchers are guarded by strictly increasing `settledNonces`, so a malleated duplicate cannot be replayed for extra payment. It is reported for completeness; it would become exploitable if any caller (or off-chain infra) used the signature bytes as a uniqueness/idempotency key.

---

Note on accounting: I specifically checked the cumulative settlement math in `settle`, `finalize`, and `close`. The incremental `delta = cumulativeAmount - settled` with the `deposit - settled` bound, plus Solidity 0.8 underflow reverts on `cumulativeAmount < settled` and `cumulativeAmount > deposit`, keep total payouts equal to `deposit` across the channel lifetime — I did not find an over-withdrawal or double-payment path there.

