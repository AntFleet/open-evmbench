# Phase 3 Prize

Phases 1 and 2 are reputation-only. The single $1000 prize attaches to
Phase 3 Exploit (SPEC §10).

## Prize conditions (all must hold)

1. 30-day prize window from Phase 3 launch.
2. ≥ 50 counted Phase 3 operators under the anti-sybil rule (SPEC §10):
   GitHub account ≥ 90 days old at Phase 3 launch, ≥ 1 accepted Phase 3
   submission with ≥ 1 solve, distinct operator-of-record, AntFleet members
   excluded, coordinated sybil clusters excludable with public reasons.
3. Highest-scoring eligible submission solves ≥ 17 of 23 runnable Exploit
   vulnerabilities (17/23 = 73.9%, the first integer score clearing the
   72.2% GPT-5.3-Codex reference).
4. AntFleet manual review of the prize claim (identity, payout eligibility,
   source pin, deterministic replay, threshold, artifact safety).
5. AntFleet and its reference submissions are excluded from eligibility.

## AntFleet commitment (binding, public)

AntFleet commits, as a public and irrevocable statement made before any
Phase 1 submissions are accepted:

1. **$1000 will be funded into escrow no later than 30 days before the
   Phase 3 prize window opens.** Funding details (custodian or on-chain
   address, transaction reference) will be published in this file at that
   time, in a Git commit anyone can verify.
2. **Once the Phase 3 prize window opens, the $1000 never returns to
   AntFleet's account.** It pays out under exactly one of the paths below.
3. **The choice of payout path is announced no later than 30 days before
   the Phase 3 prize window opens**, in this file, alongside the funded
   escrow details. The choice is between:
   - **Winner path**: highest-scoring eligible submission at window close,
     after manual review.
   - **Rollover path**: if the operator gate or threshold fails, the full
     amount rolls into a future Open EVMBench prize round (Phase 4 or
     equivalent) under the same prize model.
   - **Partial-credit path**: distributed pro-rata to the top-N submitters
     who attempted Phase 3 without clearing 17/23. If chosen, the value of
     N and the weighting (equal vs solved-count) are stated here at the
     same time.
4. **The escrow mechanism is published with the Phase 3 terms.** It will
   be one of: a segregated AntFleet account with a public commitment
   statement and custodian disclosure, or an on-chain escrow address
   (multisig or contract) verifiable on a block explorer.

This commitment is binding because it is committed to the public Git log
before Phase 1 submissions open.
