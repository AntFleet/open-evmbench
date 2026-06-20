# Audit: 2026-01-tempo-mpp-streams

## Payer Can Unilaterally Execute the “Cooperative” Close
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: `close` is described as a cooperative path, but it validates only a voucher signed by `channel.authorizedSigner` and a `payerSignature` over `("CLOSE", channelId, cumulativeAmount)`. In this design the authorized signer is the payer or the payer’s delegate, so both required signatures are under payer control. There is no payee signature, no `msg.sender == payee` requirement, and no requirement to respect the grace-period close flow. The payer can therefore manufacture a fresh low-value voucher, sign the close message themselves, and finalize the channel immediately.
- Impact: A malicious payer can reclaim the remaining deposit before the payee settles the latest off-chain voucher, permanently denying payment for already delivered service.

## Zero `authorizedSigner` Lets Invalid Signatures Pass Authorization
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `_recoverSigner`, `settle`
- Mechanism: `openChannel` never rejects `authorizedSigner == address(0)`. `_recoverSigner` returns `address(0)` for malformed signatures or wrong-length signatures, and `settle` only checks `signer == channel.authorizedSigner`. If a channel is opened with the zero address as signer, any junk signature satisfies the authorization check.
- Impact: A malicious payee can settle arbitrary vouchers up to the full channel balance without any valid payer authorization, draining the payer’s deposit immediately on misconfigured channels.

## Anyone Can Force Any Channel Into Closure
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose`, `finalize`
- Mechanism: `initiateClose` has no caller authorization at all. Any external account can start the grace period for any live channel. After that timer expires, `finalize` can be called and the channel is permanently closed. Even though the fund split in `finalize` is mechanically correct, the closure decision itself is completely public.
- Impact: Any attacker can grief active streams, force channels into timeout, and, if the payee misses the grace window, strand unpaid off-chain vouchers by making them permanently unsettleable after finalization.

## Higher Nonce, Lower Amount Vouchers Can Invalidate Legitimate Unpaid Vouchers
- Location: `contracts/TempoStreamChannel.sol` : `settle`
- Mechanism: `settle` enforces only `voucher.nonce > settledNonces[channelId]`; it does not require the new voucher amount to be at least as large as the best unpaid voucher the payee may already hold. Because anyone can call `settle`, the payer can submit a newer voucher whose `cumulativeAmount` is merely equal to current `channel.settled` or only slightly above it, advancing `settledNonces` while paying little or nothing.
- Impact: After receiving service, a malicious payer can burn the nonce frontier with a zero-delta or low-delta voucher and cause the payee’s older higher-value voucher to revert with `NonceTooLow`, denying payment for service already rendered.

## Nominal Deposit Accounting Makes Fee-On-Transfer Tokens Cross-Drain Channels
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `addDeposit`, `settle`, `finalize`, `close`
- Mechanism: The contract credits `deposit` using the requested `amount`, not the actual tokens received. Since all channels share one pooled token balance, a fee-on-transfer, deflationary, or rebasing token can make a channel appear fully funded when the contract received less than that amount. Later settlements and refunds are checked only against the channel’s recorded `deposit`, so payouts come out of the shared pool rather than the channel’s real backing.
- Impact: A channel funded with an under-received token can withdraw more than it actually deposited, consuming liquidity that belongs to other channels and eventually causing honest users’ settlements or refunds to fail.

