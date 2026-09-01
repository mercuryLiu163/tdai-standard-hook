#!/usr/bin/env python3
"""Install or print TDAI standard-hook snippets without clobbering config."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


EVENTS = ("UserPromptSubmit", "Stop")


def post_data(cfg: dict[str, Any], path: str, body: dict[str, Any]) -> dict[str, Any]:
    endpoint = str(cfg["endpoint"]).rstrip("/")
    user_key = str(cfg["user_key"])
    request = urllib.request.Request(
        endpoint + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_key}",
            "x-tdai-user-key": user_key,
            "x-tdai-service-id": str(cfg.get("service_id") or "default"),
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        envelope = json.loads(response.read().decode("utf-8"))
    if not isinstance(envelope, dict) or envelope.get("code") not in (0, None):
        raise RuntimeError(f"{path} rejected")
    data = envelope.get("data")
    return data if isinstance(data, dict) else {}


def verify_config_identity(path: Path, apply: bool) -> tuple[bool, str]:
    """Verify that configured user_id and Agent owner match the user_key."""
    if not path.is_file():
        return False, "config missing"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid config ({type(exc).__name__})"
    if not isinstance(cfg, dict):
        return False, "config root is not an object"
    required = ("endpoint", "user_key", "team_id", "agent_id")
    missing = [key for key in required if not cfg.get(key)]
    if missing:
        return False, f"config missing {', '.join(missing)}"
    if any("REPLACE" in str(cfg.get(key, "")) for key in required):
        return False, "config still contains template placeholders"

    try:
        auth = post_data(cfg, "/v3/meta/auth/verify", {"user_key": cfg["user_key"]})
        if auth.get("valid") is not True:
            return False, "user_key verification failed"
        user = auth.get("user") if isinstance(auth.get("user"), dict) else {}
        authenticated_id = str(user.get("user_id") or user.get("id") or "")
        agent = post_data(cfg, "/v3/meta/agent/get", {"agent_id": cfg["agent_id"]})
    except (OSError, RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return False, f"identity verification unavailable ({type(exc).__name__})"

    owner_id = str(agent.get("owner_user_id") or "")
    if not authenticated_id:
        return False, "user_key did not resolve to a user_id"
    if not owner_id:
        return False, "Agent did not return owner_user_id"
    if str(agent.get("team_id") or "") != str(cfg["team_id"]):
        return False, "Agent does not belong to the configured team_id"
    if owner_id != authenticated_id:
        return False, (
            f"Agent owner mismatch: authenticated={authenticated_id}, owner={owner_id}; "
            "use the Agent owner's user_key"
        )

    configured_id = str(cfg.get("user_id") or "")
    if configured_id == authenticated_id:
        return True, f"identity verified ({authenticated_id})"
    if not apply:
        return False, (
            f"user_id mismatch: configured={configured_id or '(missing)'}, "
            f"authenticated={authenticated_id}; --apply will correct it"
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + f".bak-identity-{stamp}")
    shutil.copy2(path, backup)
    cfg["user_id"] = authenticated_id
    staged = path.with_name(path.name + ".tmp-tdai-identity")
    staged.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staged, path)
    return True, f"corrected user_id to {authenticated_id}; backup={backup}"


def command(root: Path) -> str:
    runner = 'py -3' if os.name == "nt" else 'python3'
    return f'{runner} "{root / "tdai-hook.py"}"'


def hook_entry(cmd: str, timeout: int) -> dict:
    return {"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]}


def merge_file(path: Path, cmd: str) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON ({type(exc).__name__})"
    if not isinstance(data, dict):
        return False, "root is not an object"
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return False, "hooks is not an object"
    changed = False
    for event in EVENTS:
        values = hooks.setdefault(event, [])
        if not isinstance(values, list):
            return False, f"{event} is not an array"
        kept = []
        standard_present = False
        for value in values:
            serialized = json.dumps(value, ensure_ascii=False)
            # Replace only this integration's previous entries; unrelated
            # hooks and matchers stay byte-for-byte represented in JSON.
            if "tdai-memory.py" in serialized or "tdai-hook.py" in serialized:
                encoded_cmd = json.dumps(cmd, ensure_ascii=False)[1:-1]
                if (cmd in serialized or encoded_cmd in serialized) and not standard_present:
                    kept.append(value)
                    standard_present = True
                else:
                    changed = True
                continue
            kept.append(value)
        if not standard_present:
            timeout = 10 if event == "Stop" else 8
            kept.append(hook_entry(cmd, timeout))
            changed = True
        if kept != values:
            changed = True
        hooks[event] = kept
    if not changed:
        return False, "already installed"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + f".bak-tdai-{stamp}")
    shutil.copy2(path, backup)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True, str(backup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write configs after making timestamped backups")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--config", type=Path, default=None, help="TDAI config path shown in the plan")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    cfg = (args.config or Path.home() / ".tdai" / "config.json").expanduser()
    cmd = command(root)
    print(f"TDAI root: {root}")
    print(f"TDAI config: {cfg}")
    print(f"Command: {cmd}")
    print("Clients: Codex, Claude Code, ZCode, Grok, agy, DeepSeek Harness; OpenCode uses adapters/opencode-plugin.ts")
    identity_ok, identity_detail = verify_config_identity(cfg, apply=args.apply)
    print(f"Identity: {identity_detail}")
    if not args.apply:
        print("Dry-run only. Add --apply to merge existing JSON configs with timestamped backups.")
        for path in (
            Path.home() / ".codex" / "hooks.json",
            Path.home() / ".claude" / "settings.json",
            Path.home() / ".zcode" / "hooks" / "hooks.json",
        ):
            print(f"  {path}: {'present' if path.is_file() else 'missing'}")
        return 0
    if not identity_ok:
        print("Installation stopped: fix the TDAI identity configuration first.")
        return 2
    for path in (
        Path.home() / ".codex" / "hooks.json",
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".zcode" / "hooks" / "hooks.json",
    ):
        changed, detail = merge_file(path, cmd)
        print(f"{path}: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
