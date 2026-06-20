# Audit: 2026-01-tempo-mpp-streams

 ## Missing deadline enforcement in `openChannel`
- Location: contracts/TempoStreamChannel.sol : openChannel
- Mechanism: `openChannel` accepts a `deadline` parameter and defines a `DeadlineExpired` error, but the function body never checks `block.timestamp <= deadline` before performing the `safeTransferFrom` and writing the new channel to storage.
- Impact: A delayed `openChannel` transaction (e.g., due to mempool backlog, sequencer reordering, or block reorg) can be executed after the user-specified deadline, opening a channel and locking the payer’s deposit under terms they expected to expire.

## Zero-address authorized signer bypasses ECDSA verification
- Location: contracts/TempoStreamChannel.sol : openChannel / settle
- Mechanism: `openChannel` does not require `authorizedSigner != address(0)`. `_recoverSigner` returns `address(0)` for invalid or malformed signatures, and `settle` compares the recovered signer to `channel.authorizedSigner` without first rejecting `address(0)`. If a channel is created with `authorizedSigner == address(0)`, any invalid signature recovers `address(0)` and passes the signer check.
- Impact: The payee can settle arbitrary vouchers—including one that drains the full deposit—on a zero-signer channel without any valid payer authorization.

## `close` leaves channel accounting state inconsistent
- Location: contracts/TempoStreamChannel.sol : close
- Mechanism: `close` transfers `delta` to the payee and `payerRefund` to the payer, sets `finalized = true`, but never updates `channel.settled`, `channel.deposit`, or `settledNonces` to reflect the voucher. The on-chain ledger therefore no longer matches the actual token distribution.
- Impact: View functions such as `getChannel` and `getAvailableBalance` report stale, non-zero balances for a finalized channel, and the emitted `ChannelFinalized` event cannot be reconciled with `channel.settled`, allowing accounting deception or integration failures.

## Close authorization is not domain-bound and ignores voucher expiry/nonce
- Location: contracts/TempoStreamChannel.sol : close
- Mechanism: The payer’s close signature is an Ethereum Signed Message over `keccak256(abi.encodePacked("CLOSE", channelId, cumulativeAmount))`, omitting the EIP-712 domain separator, `chainId`, contract address, voucher nonce, and expiry. The function also does not validate the voucher’s `expiry` or `nonce`.
- Impact: A leaked or observed close signature can be replayed on a chain fork or on a redeployed contract (e.g., same address via CREATE2) where a matching `channelId` can be recreated, forcing unwanted closure and payment to the payee. It also lets the payee execute the close at any time using any voucher with the authorized amount, regardless of the voucher’s expiration or replay nonce.
