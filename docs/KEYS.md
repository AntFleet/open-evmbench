# AntFleet Acceptance Key

The AntFleet acceptance key is an Ed25519 keypair (SPEC §5). The public key
is published as `antfleet.public_key.pem` at the repo root and is the trust
anchor for every accepted record in the public log.

## Current key

```text
Status:      v1 launch key
Generated:   2026-06-12
Fingerprint: sha256:d0ad47a590f27d40d89f7bd7008bc3330a46d47101580baead7b959ebd51221b
```

The fingerprint is pinned in `openevmbench/constants.py` as
`LAUNCH_PUBLIC_KEY_FINGERPRINT` and verified by `tests/test_acceptance_key.py`
on every CI run.

## Retired keys

Keys retired by rotation remain in `docs/retired_keys/` so records signed
under them continue to verify against the fingerprint they were signed under
(carried in `antfleet_acceptance.public_key_fingerprint` on every record).

| Fingerprint | Status | Retired | File |
|---|---|---|---|
| `sha256:5395ddeb...7965391d` | retired pre-launch dev key | 2026-06-12 | `docs/retired_keys/antfleet.public_key.5395ddeb.pem` |

## Verifying any accepted record

```bash
openevmbench verify --record submissions/phase1/<handle>/<id>/record.json
```

Or follow the manual recipe in SPEC §4: omit `antfleet_acceptance` from the
record, JCS-canonicalize, compare the SHA256 against
`acceptance_record_hash`, and verify the Ed25519 signature against
`antfleet.public_key.pem`. For promoted or yanked records, first normalize
the payload to the acceptance-time form (strip `promoted_at` and
`promoted_commit_sha`, set `state = "accepted"`, `state_reason = null`).
