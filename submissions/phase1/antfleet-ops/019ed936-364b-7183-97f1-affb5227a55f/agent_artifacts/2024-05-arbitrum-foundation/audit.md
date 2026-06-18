# Audit: 2024-05-arbitrum-foundation

## Merge note

Report A (Claude) reported **no vulnerabilities** — it explicitly reviewed several of the same code paths Report B flags and judged them clean. Report B (Codex) reported four findings. Because a consensus finding requires *both* reports to describe the same issue *as a finding*, and Report A affirmatively rejected (rather than raised) these issues, there are **no consensus findings**. All four are single-reviewer (Reviewer B), and where Reviewer A explicitly examined and disputed the same path, that disagreement is recorded.

---

## Consensus findings

*None.* Report A concluded the codebase is a faithful reproduction of upstream Arbitrum `nitro-contracts`/BOLD with no exploitable vulnerability. None of Reviewer B's findings were independently raised as findings by Reviewer A; three of the four were explicitly examined by Reviewer A and judged non-exploitable (noted inline below).

---

## Additional findings (single-reviewer)

## Prefunded ERC20 inbox balance can be stolen
*(Reviewer B only)*
- Location: src/bridge/ERC20Inbox.sol : `_deliverToBridge`
- Mechanism: The function pays `tokenAmount` from the inbox's current `nativeToken` balance before pulling funds from the caller. Because that balance is global and not accounted per depositor, any idle or accidentally pre-funded tokens in the inbox are treated as payment for the next caller's deposit or retryable ticket.
- Impact: If the inbox holds native tokens, an attacker can call `depositERC20` or `createRetryableTicket` and receive L2 credit while paying only the shortfall — or nothing if the inbox balance is sufficient. Preconditions: the ERC20 inbox has a positive native-token balance not meant for the attacker.
- Reviewer disagreement: Reviewer A examined this exact path (`_deliverToBridge` shortfall-pull vs. L2 credit) and judged it correct/faithful to upstream.

## Force inclusion ignores timestamp delay
*(Reviewer B only)*
- Location: src/bridge/SequencerInbox.sol : `forceInclusion`
- Mechanism: `forceInclusion` enforces only the block delay with `l1BlockAndTime[0] + delayBlocks_ >= block.number`. It never checks `l1BlockAndTime[1] + delaySeconds` against `block.timestamp`, even though `delaySeconds` is part of the configured max time variation and `ForceIncludeTimeTooSoon` exists.
- Impact: A delayed message can be force-included as soon as the block-delay condition passes, even if the configured wall-clock delay has not elapsed. On chains or periods with faster-than-expected blocks, this shortens the sequencer-only/censorship window below the intended seconds-based bound.
- Reviewer disagreement: Reviewer A reviewed the same block-only gate and considers it intentional in the BOLD delay-buffer refactor, with `ForceIncludeTimeTooSoon` being leftover-but-unused dead code rather than a missing check.

## Staking pool over-credits non-standard ERC20 deposits
*(Reviewer B only)*
- Location: src/assertionStakingPool/AbsBoldStakingPool.sol : `depositIntoPool`
- Mechanism: The pool increments `depositBalance[msg.sender]` by the requested `amount` before verifying how many stake tokens were actually received. For fee-on-transfer, rebasing, or otherwise non-standard stake tokens, the contract can receive less than `amount` while still crediting the depositor for the full amount.
- Impact: The pool can become insolvent and early withdrawers can externalize the shortfall onto later depositors. Preconditions: the configured `stakeToken` takes fees, rebases, or otherwise transfers less than the nominal `amount`.
- Reviewer disagreement: Reviewer A judged the pool deposit/withdraw accounting strictly 1:1 with correct CEI ordering, treating standard-ERC20 behavior as a documented trust assumption rather than a flaw.

## Blob batch event can emit the wrong sequence number
*(Reviewer B only)*
- Location: src/bridge/SequencerInbox.sol : `addSequencerL2BatchFromBlobsImpl`
- Mechanism: Blob batch submission allows `sequenceNumber == type(uint256).max` as a sentinel to skip the exact sequence check, but the function emits `SequencerBatchDelivered(sequenceNumber, ...)` instead of the actual `seqMessageIndex`. The calldata path emits `seqMessageIndex`, so this creates an event/storage desync only for blob batches.
- Impact: An authorized batch poster can submit a valid blob batch with the sentinel and cause off-chain consumers that key by `batchSequenceNumber` to observe `type(uint256).max` instead of the canonical batch index, potentially breaking indexing or synchronization for that batch.
- Reviewer note: Not addressed by Reviewer A.

