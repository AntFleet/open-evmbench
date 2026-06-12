"""CLI credential storage.

Credentials live at `$OPENEVMBENCH_HOME/credentials.json` (default
`~/.config/openevmbench/`), mode 0600. The stored token is the API token
created after GitHub OAuth login (SPEC §3: 30-day, renewable, revocable);
during the pre-launch window the CLI also accepts a GitHub personal access
token, which it verifies against api.github.com/user to bind the operator
identity.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("OPENEVMBENCH_HOME")
    if override:
        return Path(override)
    return Path.home() / ".config" / "openevmbench"


@dataclass(frozen=True)
class Credentials:
    github_username: str
    github_id: int
    token: str


def save_credentials(creds: Credentials) -> Path:
    cdir = config_dir()
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / "credentials.json"
    path.write_text(
        json.dumps(
            {
                "github_username": creds.github_username,
                "github_id": creds.github_id,
                "token": creds.token,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def load_credentials() -> Credentials | None:
    path = config_dir() / "credentials.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Credentials(
        github_username=data["github_username"],
        github_id=int(data["github_id"]),
        token=data["token"],
    )
