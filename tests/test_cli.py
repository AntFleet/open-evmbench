import json

import pytest

from conftest import load_fixture
from openevmbench.cli import _parse_judge_params, build_parser, main
from openevmbench.config import Credentials, load_credentials, save_credentials


def test_parser_covers_all_commands():
    parser = build_parser()
    for argv in (
        ["login", "tok"],
        ["clone"],
        ["submit", "--package", "p"],
        ["verify", "--record", "r"],
        ["check-pr", "--changed-files", "x"],
        ["admin", "keygen", "--out-private", "k"],
        ["admin", "accept", "--record", "r"],
        ["admin", "reject", "--record", "r", "--reason", "x"],
        ["admin", "promote", "--record", "r", "--commit", "c"],
        ["admin", "yank", "--record", "r", "--reason", "x"],
    ):
        args = parser.parse_args(argv)
        assert callable(args.func)


def test_parse_judge_params_json_coercion():
    params = _parse_judge_params(["reasoning_effort=high", "temperature=0", "top_p=0.9", "seed=42"])
    assert params == {"reasoning_effort": "high", "temperature": 0, "top_p": 0.9, "seed": 42}
    with pytest.raises(ValueError):
        _parse_judge_params(["no-equals-sign"])


def test_credentials_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENEVMBENCH_HOME", str(tmp_path))
    assert load_credentials() is None
    path = save_credentials(Credentials("alice", 1, "tok"))
    assert path.stat().st_mode & 0o777 == 0o600
    creds = load_credentials()
    assert creds == Credentials("alice", 1, "tok")


def test_keygen_verify_accept_cycle(tmp_path, capsys):
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    assert main(["admin", "keygen", "--out-private", str(private), "--out-public", str(public)]) == 0
    assert private.stat().st_mode & 0o777 == 0o600

    # keygen refuses to overwrite an existing private key
    assert main(["admin", "keygen", "--out-private", str(private), "--out-public", str(public)]) == 1

    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(load_fixture("submitted_valid")))

    assert main([
        "admin", "accept", "--record", str(record_path),
        "--private-key", str(private), "--public-key", str(public),
    ]) == 0
    accepted = json.loads(record_path.read_text())
    assert accepted["state"] == "accepted"

    assert main(["verify", "--record", str(record_path), "--public-key", str(public)]) == 0

    assert main(["admin", "promote", "--record", str(record_path), "--commit", "a" * 40]) == 0
    promoted = json.loads(record_path.read_text())
    assert promoted["state"] == "promoted"
    # signature still verifies after promotion
    assert main(["verify", "--record", str(record_path), "--public-key", str(public)]) == 0

    assert main(["admin", "yank", "--record", str(record_path), "--reason", "test yank"]) == 0
    assert main(["verify", "--record", str(record_path), "--public-key", str(public)]) == 0

    out = capsys.readouterr().out
    assert "fingerprint: sha256:" in out


def test_verify_fails_on_tamper(tmp_path):
    private = tmp_path / "k.pem"
    public = tmp_path / "p.pem"
    main(["admin", "keygen", "--out-private", str(private), "--out-public", str(public)])
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(load_fixture("submitted_valid")))
    main(["admin", "accept", "--record", str(record_path),
          "--private-key", str(private), "--public-key", str(public)])

    record = json.loads(record_path.read_text())
    record["score"]["official_score"] = 1.0
    record_path.write_text(json.dumps(record))
    assert main(["verify", "--record", str(record_path), "--public-key", str(public)]) == 1
