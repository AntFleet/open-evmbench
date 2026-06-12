"""Acceptance-key launch guardrail.

`antfleet.public_key.pem` is the trust anchor for every accepted record in
the public log. If it ever drifts from the pinned launch fingerprint, every
previously-signed record becomes unverifiable. This test fails loudly when
the committed public key changes — accidental DEV-key carryover, an
unintended rotation, or a corrupted commit all surface here before reaching
production.

Rotation procedure (docs/KEYS.md):
1. Generate the new keypair on a trusted machine.
2. Commit the new public key in place of the current one.
3. Update LAUNCH_PUBLIC_KEY_FINGERPRINT in openevmbench/constants.py to the
   new fingerprint, and move the old key to docs/retired_keys/.
4. This test will then pass; old records signed by the retired key remain
   verifiable against their copies in docs/retired_keys/, by their stored
   antfleet_acceptance.public_key_fingerprint.
"""

from pathlib import Path

from openevmbench import constants
from openevmbench.signing import public_key_fingerprint


def test_committed_public_key_matches_launch_pin():
    repo_root = Path(__file__).parent.parent
    pem_path = repo_root / "antfleet.public_key.pem"
    assert pem_path.is_file(), f"{pem_path} missing"

    actual = public_key_fingerprint(pem_path.read_bytes())
    assert actual == constants.LAUNCH_PUBLIC_KEY_FINGERPRINT, (
        f"antfleet.public_key.pem fingerprint drift!\n"
        f"  committed: {actual}\n"
        f"  pinned   : {constants.LAUNCH_PUBLIC_KEY_FINGERPRINT}\n"
        "If this is an intentional rotation, follow the procedure in "
        "docs/KEYS.md and update LAUNCH_PUBLIC_KEY_FINGERPRINT."
    )


def test_retired_keys_are_preserved():
    """Retired keys stay in docs/retired_keys/ so old records remain verifiable."""
    retired_dir = Path(__file__).parent.parent / "docs" / "retired_keys"
    if not retired_dir.is_dir():
        return  # no rotations yet
    for pem in retired_dir.glob("*.pem"):
        fp_short = pem.name.split(".")[-2]
        actual = public_key_fingerprint(pem.read_bytes())
        assert actual.startswith(f"sha256:{fp_short}"), (
            f"{pem.name}: filename fingerprint segment does not match key contents"
        )
        assert actual != constants.LAUNCH_PUBLIC_KEY_FINGERPRINT, (
            f"{pem.name} is in retired_keys/ but equals the current launch key"
        )
