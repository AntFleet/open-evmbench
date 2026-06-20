# Audit: 2024-05-arbitrum-foundation

## Allowlist Bypass Via `tx.origin`
- Location: `src/bridge/AbsInbox.sol : onlyAllowed`
- Mechanism: The inbox allowlist is enforced against `tx.origin` instead of `msg.sender`. Any contract can therefore call protected inbox entrypoints as long as the outer transaction was originated by an allowlisted EOA. Because `_deliverToBridge` still aliases and records the intermediary contract as the L2 sender, this is not just relaying the EOA’s access; it lets a non-allowlisted contract use the inbox under its own identity.
- Impact: An unallowlisted contract can bypass the allowlist and enqueue arbitrary L2 messages, retryables, or deposits whenever it can get any allowlisted EOA to originate the transaction, defeating the intended access-control boundary.

## Force Inclusion Ignores The Configured Time Window
- Location: `src/bridge/SequencerInbox.sol : forceInclusion`
- Mechanism: `forceInclusion` enforces only the block-based delay (`l1BlockAndTime[0] + delayBlocks_ < block.number`) and never enforces the timestamp-based delay from `delaySeconds`, even though the protocol tracks both dimensions in `MaxTimeVariation` and defines `ForceIncludeTimeTooSoon`. This lets the force-inclusion gate open as soon as the block threshold passes, regardless of whether the configured time threshold has passed.
- Impact: Anyone can force delayed messages into the inbox earlier than intended by the time-based censorship/finality window, weakening sequencer-delay guarantees and potentially forcing inclusion before the protocol expected the message to be eligible.

## Rival Edge Time Can Be Misattributed Across Claim Chains
- Location: `src/challengeV2/libraries/EdgeChallengeManagerLib.sol : updateTimerCacheByClaim`
- Mechanism: `updateTimerCacheByClaim` relies on `checkClaimIdLink`, but that check only verifies that the claiming edge’s `originId` matches the lower edge’s `mutualId` and that the level is correct. It never verifies `claimingEdge.claimId == edgeId`. Since rival edges share the same `mutualId`, a zero-layer edge built on rival branch `B` can be used to update the timer cache of rival branch `A`, even though `A` was never actually claimed by that upper-level edge.
- Impact: An attacker can transfer accumulated unrivaled time from one rival branch onto another, propagate that forged timer cache upward, and eventually satisfy `confirmEdgeByTime` for the wrong edge or ancestor chain, breaking challenge resolution.

