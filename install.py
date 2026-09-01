[ERROR] - (starship::print): Under a 'dumb' terminal (TERM=dumb).

#!/usr/bin/env python3
"""Install or print TDAI standard-hook snippets without clobbering config."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


EVENTS = ("UserPromptSubmit", "Stop")


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
    if not args.apply:
        print("Dry-run only. Add --apply to merge existing JSON configs with timestamped backups.")
        for path in (
            Path.home() / ".codex" / "hooks.json",
            Path.home() / ".claude" / "settings.json",
            Path.home() / ".zcode" / "hooks" / "hooks.json",
        ):
            print(f"  {path}: {'present' if path.is_file() else 'missing'}")
        return 0
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
