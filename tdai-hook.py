#!/usr/bin/env python3
"""TDAI Standard Hook v1.

This file is the provider-neutral sidecar for Tencent Agent Memory.  Agents
that implement a JSON stdin/stdout hook (Codex, Claude Code, ZCode, Grok and
similar harnesses) can call it directly.  Provider-specific plugins should
translate their native event to the small event contract documented in
``README.md`` and translate the returned ``additionalContext`` back.

The hook is deliberately fail-open: a missing backend, malformed event, or
state write failure is logged and never blocks the host agent.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "1.0.3"
MAX_PROMPT = 4000
MAX_RECALL = 1800
TASK_SELECTION_VERSION = 2

DEFAULT_RECALL_HINTS = (
    "之前", "上次", "以前", "此前", "以往", "当时", "记得", "回忆",
    "我们说过", "我们决定", "我们定过", "之前决定", "之前约定", "继续上次",
    "沿用之前", "沿用原来", "原来的方案", "历史结论", "历史决定", "对话历史",
    "偏好", "习惯", "previous", "last time", "remember", "earlier",
    "we decided", "we agreed", "prior decision", "conversation history",
    "preference", "as before",
)
DEFAULT_CONFIRM_LAST = {
    "保持", "继续", "是", "对", "用上次", "yes", "y", "ok", "好", "确认",
    "不变", "就这个", "这个", "keep", "same", "上次", "沿用",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:100]


def cli_value(name: str) -> str:
    """Return a small launcher option without requiring host env support."""
    flag = f"--{name}"
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == flag and index + 1 < len(args):
            return args[index + 1].strip()
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1].strip()
    return ""


class Hook:
    """Provider-neutral implementation; no agent SDK is imported here."""

    def __init__(self, event: dict[str, Any] | None = None) -> None:
        self.event = event or {}
        self.config_path = self.resolve_config_path()
        self.cfg = self.load_config(self.config_path)
        self.client = self.client_name(self.event)
        self.state_dir = self.resolve_state_dir(self.cfg, self.config_path)
        self.log_path = Path(
            os.environ.get("TDAI_LOG_PATH") or self.state_dir / "hook.log"
        )
        self.json_log_path = Path(
            os.environ.get("TDAI_JSON_LOG_PATH") or self.state_dir / "hook.jsonl"
        )

    @staticmethod
    def resolve_config_path() -> Path:
        explicit = os.environ.get("TDAI_CONFIG") or os.environ.get("TDAI_CONFIG_PATH")
        if explicit:
            return Path(explicit).expanduser()
        home = Path.home()
        tdai_home = Path(os.environ.get("TDAI_HOME") or home / ".tdai")
        candidates = (
            tdai_home / "config.json",
            tdai_home / "tdai-memory.json",
        )
        for path in candidates:
            if path.is_file():
                return path
        return candidates[0]

    @staticmethod
    def load_config(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as stream:
            raw = json.load(stream)
        if not isinstance(raw, dict):
            raise RuntimeError("TDAI config must be a JSON object")

        # Profiles let one installation serve many hosts without copying the
        # secret or changing the core.  TDAI_PROFILE takes precedence over the
        # provider's name so CI/harnesses can select a deterministic profile.
        profile_name = (
            cli_value("profile")
            or cli_value("client")
            or os.environ.get("TDAI_PROFILE")
            or os.environ.get("TDAI_CLIENT")
            or str(raw.get("client") or "")
        ).strip()
        profiles = raw.get("profiles")
        profile = profiles.get(profile_name) if isinstance(profiles, dict) else None
        if isinstance(profile, dict):
            merged = dict(raw)
            merged.update(profile)
            raw = merged

        for key in ("endpoint", "user_key", "user_id", "team_id", "agent_id"):
            if not raw.get(key):
                raise RuntimeError(f"missing {key} in {path}")
        return raw

    @staticmethod
    def resolve_state_dir(cfg: dict[str, Any], config_path: Path) -> Path:
        value = os.environ.get("TDAI_STATE_DIR") or cfg.get("state_dir")
        return Path(value).expanduser() if value else config_path.parent / "tdai-memory-state"

    def client_name(self, event: dict[str, Any]) -> str:
        value = (
            cli_value("client")
            or os.environ.get("TDAI_CLIENT")
            or event.get("client")
            or event.get("provider")
            or self.cfg.get("client")
            or "generic"
        )
        return safe_name(str(value).lower()) or "generic"

    def log(self, event_name: str, **fields: Any) -> None:
        """Write a grep-friendly log and a machine-readable JSONL companion."""
        fields = {"client": self.client, **fields}
        text_fields = []
        for key, value in fields.items():
            if isinstance(value, bool):
                value = str(value).lower()
            text_fields.append(f"{key}={value}")
        line = f"{utc_now()} {event_name} " + " ".join(text_fields)
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
            record = {"timestamp": utc_now(), "event": event_name, **fields}
            with self.json_log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=True) + "\n")
        except OSError:
            # Logging must never change the host agent's result.
            pass

    @staticmethod
    def event_name(event: dict[str, Any]) -> str:
        return str(
            event.get("hookEventName")
            or event.get("hook_event_name")
            or event.get("event")
            or os.environ.get("TDAI_HOOK_EVENT")
            or ""
        ).strip().lower()

    @staticmethod
    def session_id(event: dict[str, Any]) -> str:
        return str(
            event.get("sessionId")
            or event.get("session_id")
            or event.get("sessionID")
            or os.environ.get("TDAI_SESSION_ID")
            or os.environ.get("GROK_SESSION_ID")
            or "tdai-unknown"
        )

    @staticmethod
    def text_value(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts).strip()
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            return value["text"].strip()
        return ""

    @classmethod
    def prompt_from(cls, event: dict[str, Any]) -> str:
        for key in (
            "prompt", "userPrompt", "user_prompt", "text", "content", "message",
        ):
            value = cls.text_value(event.get(key))
            if value:
                return value
        return ""

    @classmethod
    def assistant_from(cls, event: dict[str, Any]) -> str:
        for key in (
            "lastAssistantMessage", "last_assistant_message", "assistant_message",
            "assistantMessage", "response", "result",
        ):
            value = cls.text_value(event.get(key))
            if value:
                return value
        return ""

    @staticmethod
    def clip(value: str, limit: int) -> str:
        value = (value or "").strip()
        return value if len(value) <= limit else value[: limit - 1] + "…"

    def state_path(self, sid: str) -> Path:
        return self.state_dir / f"{safe_name(sid)}.json"

    def load_state(self, sid: str) -> dict[str, Any]:
        path = self.state_path(sid)
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def save_state(self, sid: str, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_path(sid)
        fd, temp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(self.state_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=True)
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass

    def update_state(self, sid: str, **changes: Any) -> dict[str, Any]:
        state = self.load_state(sid)
        for key, value in changes.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value
        self.save_state(sid, state)
        return state

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = str(self.cfg["endpoint"]).rstrip("/") + path
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg['user_key']}",
                "x-tdai-user-key": str(self.cfg["user_key"]),
                "x-tdai-service-id": str(self.cfg.get("service_id") or "default"),
            },
        )
        timeout = float(self.cfg.get("timeout_sec") or 4)
        attempts = 2
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                if not isinstance(data, dict):
                    raise RuntimeError(f"bad response from {path}")
                if data.get("code") not in (0, None):
                    raise RuntimeError(f"{path} code={data.get('code')}")
                result = data.get("data")
                return result if isinstance(result, dict) else {}
            except urllib.error.HTTPError as exc:
                if exc.code >= 500 and attempt == 0:
                    continue
                raise RuntimeError(f"{path} http={exc.code}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"{path} unavailable: {type(exc).__name__}") from exc
        return {}

    def isolation(self, sid: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "team_id": self.cfg["team_id"],
            "agent_id": self.cfg["agent_id"],
            "user_id": self.cfg["user_id"],
        }
        if task_id:
            body["task_id"] = task_id
        if sid:
            body["session_id"] = sid
        return body

    @staticmethod
    def binding(state: dict[str, Any]) -> dict[str, Any] | None:
        value = state.get("task_binding")
        if not isinstance(value, dict) or value.get("mode") not in ("task", "agent"):
            return None
        if value.get("mode") == "task" and not value.get("task_id"):
            return None
        return value

    @staticmethod
    def task_id(binding: dict[str, Any] | None) -> str | None:
        if binding and binding.get("mode") == "task":
            value = str(binding.get("task_id") or "")
            return value or None
        return None

    def bind(self, sid: str, task: dict[str, Any] | None, *, legacy: bool = False) -> dict[str, Any]:
        if task is None:
            value: dict[str, Any] = {"mode": "agent", "title": "跨 Task（Agent 全部记忆）"}
        else:
            value = {
                "mode": "task",
                "task_id": str(task["task_id"]),
                "title": str(task.get("title") or task["task_id"]),
                "status": str(task.get("status") or ""),
            }
        if legacy:
            value["legacy"] = True
        self.update_state(
            sid,
            task_binding=value,
            task_selection_version=TASK_SELECTION_VERSION,
            awaiting_task=False,
            need_announce=False,
            binding_announced=True,
        )
        if not legacy:
            self.save_last_binding(value)
        return value

    def last_binding_path(self) -> Path:
        return self.state_dir / "last-binding.json"

    def load_last_binding(self) -> dict[str, Any] | None:
        path = self.last_binding_path()
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value = None
            if isinstance(value, dict) and value.get("mode") in ("task", "agent"):
                return value
        newest: tuple[float, dict[str, Any]] | None = None
        try:
            for candidate in self.state_dir.glob("*.json"):
                if candidate.name == path.name or candidate.name.endswith(".tmp"):
                    continue
                try:
                    state = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                value = self.binding(state) if isinstance(state, dict) else None
                if value:
                    mtime = candidate.stat().st_mtime
                    if newest is None or mtime > newest[0]:
                        newest = (mtime, value)
        except OSError:
            return None
        return newest[1] if newest else None

    def save_last_binding(self, binding: dict[str, Any]) -> None:
        value = {
            **binding,
            "team_name": str(self.cfg.get("team_name") or ""),
            "team_id": str(self.cfg.get("team_id") or ""),
            "agent_name": str(self.cfg.get("agent_name") or ""),
            "agent_id": str(self.cfg.get("agent_id") or ""),
            "bound_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            path = self.last_binding_path()
            fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(self.state_dir))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2)
                os.replace(temp_name, path)
            finally:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
        except OSError as exc:
            self.log("save_last_binding_failed", error=type(exc).__name__)

    def list_tasks(self) -> list[dict[str, Any]]:
        data = self.post(
            "/v3/meta/task/list",
            {"team_id": self.cfg["team_id"], "page": 1, "page_size": 100},
        )
        values = data.get("items") or data.get("records") or []
        tasks = [v for v in values if isinstance(v, dict) and v.get("task_id")]
        tasks.sort(
            key=lambda item: (
                str(item.get("status") or "") != "running",
                str(item.get("title") or item.get("task_id") or "").casefold(),
            )
        )
        return tasks

    @staticmethod
    def parse_task_command(prompt: str) -> tuple[str, str, str] | None:
        stripped = prompt.strip()
        lowered = stripped.casefold()
        exact = {
            "/tdai-task list": "list", "/tdai-task current": "current",
            "/tdai-task switch": "switch", "切换任务": "switch",
            "查看任务": "list", "当前任务": "current",
        }
        if lowered in exact:
            return exact[lowered], "", ""
        first, separator, rest = stripped.partition("\n")
        match = re.match(r"^(?:@task|/tdai-task)\s+(.+?)\s*$", first, re.I)
        if not match:
            return None
        selector = match.group(1).strip()
        action = selector.casefold()
        if action in ("list", "current", "switch"):
            return action, "", rest.strip() if separator else ""
        return "select", selector, rest.strip() if separator else ""

    def confirm_words(self) -> set[str]:
        values = self.cfg.get("confirm_last")
        if isinstance(values, list) and values:
            return {str(v).casefold() for v in values}
        return {v.casefold() for v in DEFAULT_CONFIRM_LAST}

    def split_confirm_last(self, prompt: str) -> tuple[str, str] | None:
        stripped = prompt.strip()
        lowered = stripped.casefold()
        words = sorted(self.confirm_words(), key=len, reverse=True)
        for word in words:
            if lowered == word:
                return stripped, ""
            if not lowered.startswith(word):
                continue
            boundary = stripped[len(word):len(word) + 1]
            if boundary and boundary in " \t\r\n,，:：;；":
                return stripped[:len(word)], stripped[len(word):].lstrip(" \t\r\n,，:：;；")
        return None

    @staticmethod
    def looks_like_work(value: str) -> bool:
        value = value.strip()
        return bool(value) and ("\n" in value or len(value) > 24)

    @staticmethod
    def select_task(selector: str, tasks: list[dict[str, Any]]) -> dict[str, Any] | None | bool:
        value = selector.strip().strip("\"'")
        folded = value.casefold()
        if folded in {"0", "none", "agent", "all", "全部", "全部记忆", "跨task", "跨 task", "不绑定"}:
            return None
        if value.isdigit():
            index = int(value) - 1
            return tasks[index] if 0 <= index < len(tasks) else False
        for task in tasks:
            if folded in {
                str(task.get("task_id") or "").casefold(),
                str(task.get("title") or "").casefold(),
            }:
                return task
        partial = [task for task in tasks if folded and folded in str(task.get("title") or "").casefold()]
        return partial[0] if len(partial) == 1 else False

    def identity_lines(self) -> list[str]:
        return [
            f"Team: {self.cfg.get('team_name') or self.cfg['team_id']} ({self.cfg['team_id']})",
            f"Agent: {self.cfg.get('agent_name') or self.cfg['agent_id']} ({self.cfg['agent_id']})",
        ]

    def format_binding(self, binding: dict[str, Any], pending: str = "", announce: bool = False) -> str:
        title = str(binding.get("title") or binding.get("task_id") or "跨 Task")
        lines = ["<tdai-task-binding>", *self.identity_lines(), f"当前 {self.client} 会话已绑定 Task：{title}"]
        lines.append(f"task_id: {binding.get('task_id')}" if binding.get("task_id") else "task_id: none（跨 Task）")
        if announce:
            lines.extend([
                "必须在本轮对用户的回复开头用一两句话说明上述 Agent 和 Task，并询问是否继续使用；要换就说「切换任务」。",
                "不要把这段指令当成已经问过；不要复述 L1/L2/L3 记忆正文。",
            ])
        if pending:
            lines.extend(["Task 选择前暂存的原始请求如下；现在继续处理它，不要要求用户重发：", pending])
        lines.append("</tdai-task-binding>")
        return "\n".join(lines)

    def format_choices(self, tasks: list[dict[str, Any]], error: str = "", required: bool = True, pending: str = "") -> str:
        lines = ["<tdai-task-selection>", *self.identity_lines()]
        last = self.load_last_binding()
        if last:
            lines.append(f"上次绑定 Task：{last.get('title') or last.get('task_id') or '跨 Task'} ({last.get('task_id') or 'none'})")
            lines.append("用户回复「保持」即沿用上次 Task。")
        lines.append(
            f"当前 {self.client} 会话尚未绑定 Tencent Memory Task。"
            if required else "当前请求是查看可选 Tencent Memory Task；现有绑定不变。"
        )
        if error:
            lines.append(f"选择未生效：{error}")
        lines.append("可选 Task：")
        for index, task in enumerate(tasks, 1):
            lines.append(f"{index}. {task.get('title') or task.get('task_id')} [{task.get('status') or 'unknown'}] ({task['task_id']})")
        lines.append("0. 不绑定 Task（跨 Task 读取 Agent 全部 L0/L1）")
        if required:
            lines.extend(["请让用户回复「保持」、序号、Task 名称或 Task ID。", "在用户完成选择前，不要处理其待办请求。"])
        else:
            lines.append("仅展示列表；不要改变当前绑定。")
        if pending:
            lines.extend(["\n待处理原始请求：", pending])
        lines.append("</tdai-task-selection>")
        return "\n".join(lines)

    def format_recall(self, atomic: dict[str, Any], core: dict[str, Any], scenes: dict[str, Any]) -> str:
        lines: list[str] = []
        items = atomic.get("items") or atomic.get("hits") or []
        if isinstance(items, list):
            for item in items[:5]:
                if isinstance(item, dict):
                    content = item.get("content") or item.get("text") or item.get("snippet")
                    if content:
                        lines.append(f"- [{item.get('type') or 'note'}] {self.clip(str(content), 280)}")
        persona = core.get("content")
        if isinstance(persona, str) and persona.strip():
            lines.append("- [persona] " + self.clip(persona, 400))
        entries = scenes.get("entries") or scenes.get("items") or []
        if isinstance(entries, list):
            names = [str(item.get("path") or item.get("name")) for item in entries[:6] if isinstance(item, dict) and (item.get("path") or item.get("name"))]
            if names:
                lines.append("- [scenes] " + ", ".join(names))
        return self.clip("<tdai-memory>\n" + "\n".join(lines) + "\n</tdai-memory>", MAX_RECALL) if lines else ""

    def recall(self, query: str, task_id: str | None) -> str:
        atomic: dict[str, Any] = {}
        core: dict[str, Any] = {}
        scenes: dict[str, Any] = {}
        try:
            atomic = self.post("/v3/atomic/search", {**self.isolation(task_id=task_id), "query": self.clip(query, 400), "limit": 5})
        except Exception as exc:
            self.log("recall_atomic_failed", error=type(exc).__name__)
        try:
            core = self.post("/v3/core/read", self.isolation(task_id=task_id))
        except Exception as exc:
            self.log("recall_core_failed", error=type(exc).__name__)
        try:
            scenes = self.post("/v3/scenario/ls", {**self.isolation(task_id=task_id), "path_prefix": ""})
        except Exception as exc:
            self.log("recall_scenes_failed", error=type(exc).__name__)
        return self.format_recall(atomic, core, scenes)

    def recall_decision(self, prompt: str) -> tuple[bool, str, str]:
        forced = re.match(r"^(?:/tdai-recall|@recall)\s+(.+)$", prompt.strip(), re.I | re.S)
        if forced:
            return True, "forced", forced.group(1).strip()
        hints = self.cfg.get("recall_hints")
        values = tuple(str(v) for v in hints) if isinstance(hints, list) and hints else DEFAULT_RECALL_HINTS
        normalized = " ".join(prompt.casefold().split())
        for hint in values:
            if hint.casefold() in normalized:
                return True, f"hint:{hint}", prompt
        return False, "no-memory-hint", prompt

    def conditional_recall(self, prompt: str, task_id: str | None, sid: str) -> str:
        enabled, reason, query = self.recall_decision(prompt)
        self.log("recall_decision", session=sid, task=task_id or "agent-wide", enabled=enabled, reason=reason, query_chars=len(query))
        return self.recall(query, task_id) if enabled else ""

    def compose(self, sid: str, task_id: str | None, binding: str, memory: str = "", capability: str = "") -> str:
        context = "\n".join(part for part in (binding, memory, capability) if part)
        self.log("injected_chars", session=sid, task=task_id or "agent-wide", binding=len(binding), memory=len(memory), capability=len(capability), total=len(context))
        return context

    def emit(self, text: str, event_name: str) -> None:
        if not text:
            return
        mode = str(os.environ.get("TDAI_OUTPUT_MODE") or self.cfg.get("output_mode") or "hookSpecificOutput")
        if mode == "plain":
            sys.stdout.write(text)
            return
        payload: dict[str, Any] = {
            "hookSpecificOutput": {"hookEventName": event_name or "UserPromptSubmit", "additionalContext": text}
        }
        if mode in ("all", "compat"):
            payload["additionalContext"] = text
            payload["additional_context"] = text
        sys.stdout.write(json.dumps(payload, ensure_ascii=True))

    def require_task(self) -> bool:
        value = self.cfg.get("require_task_selection", True)
        return not (value is False or str(value).casefold() in {"0", "false", "no"})

    def emit_choices(self, sid: str, *, pending: str = "", error: str = "", event_name: str = "UserPromptSubmit") -> None:
        self.update_state(sid, task_selection_version=TASK_SELECTION_VERSION, awaiting_task=True, pending_prompt=pending or None, skip_capture_once=True, need_announce=True, binding_announced=False)
        try:
            tasks = self.list_tasks()
            self.emit(self.format_choices(tasks, error=error, pending=pending), event_name)
            self.log("task_selection_requested", session=sid, choices=len(tasks))
        except Exception as exc:
            self.emit("<tdai-task-selection>\n" + "\n".join(self.identity_lines()) + "\nTencent Memory Task 列表读取失败，请稍后重试。\n</tdai-task-selection>", event_name)
            self.log("task_list_failed", session=sid, error=type(exc).__name__)

    def mark_announced(self, sid: str, state: dict[str, Any]) -> bool:
        value = bool(state.get("need_announce")) or not state.get("binding_announced")
        if value:
            self.update_state(sid, need_announce=False, binding_announced=True)
        return value

    def on_session_start(self, event: dict[str, Any]) -> None:
        sid = self.session_id(event)
        state = self.load_state(sid)
        binding = self.binding(state)
        self.update_state(sid, task_selection_version=TASK_SELECTION_VERSION, need_announce=True, binding_announced=False)
        if binding:
            self.emit(self.format_binding(binding, announce=True), "SessionStart")
            self.log("session_start_announce", session=sid, task=self.task_id(binding) or "agent-wide")
        elif self.require_task():
            self.emit_choices(sid, event_name="SessionStart")
        else:
            binding = self.bind(sid, self.load_last_binding())
            self.emit(self.format_binding(binding, announce=True), "SessionStart")

    def resolve_last(self, tasks: list[dict[str, Any]]) -> dict[str, Any] | None | bool:
        last = self.load_last_binding()
        if not last:
            return False
        if last.get("mode") == "agent" or not last.get("task_id"):
            return None
        for task in tasks:
            if str(task.get("task_id")) == str(last.get("task_id")):
                return task
        return False

    def on_prompt(self, event: dict[str, Any]) -> None:
        prompt = self.prompt_from(event)
        sid = self.session_id(event)
        hook_event = str(event.get("hookEventName") or event.get("hook_event_name") or "UserPromptSubmit")
        if not prompt:
            self.log("empty_prompt", session=sid)
            return
        state = self.load_state(sid)
        binding = self.binding(state)
        command = self.parse_task_command(prompt)
        action = command[0] if command else ""

        if action == "switch":
            self.update_state(sid, task_binding=None, pending_prompt=None, awaiting_task=True, task_selection_version=TASK_SELECTION_VERSION, skip_capture_once=True, need_announce=True, binding_announced=False)
            self.emit_choices(sid, event_name=hook_event)
            return
        if action == "list":
            try:
                self.emit(self.format_choices(self.list_tasks(), required=False), hook_event)
            except Exception as exc:
                self.log("task_list_failed", session=sid, error=type(exc).__name__)
            self.update_state(sid, skip_capture_once=True)
            return
        if action == "current":
            text = self.format_binding(binding, announce=True) if binding else "<tdai-task-binding>当前对话尚未绑定 Task。</tdai-task-binding>"
            self.emit(text, hook_event)
            self.update_state(sid, skip_capture_once=True)
            return

        if binding is None and not self.require_task():
            last = self.load_last_binding()
            binding = self.bind(sid, last if last else None)
            state = self.load_state(sid)

        if binding is None:
            pending = str(state.get("pending_prompt") or "")
            selector = ""
            remaining = ""
            if action == "select" and command:
                selector, remaining = command[1], command[2]
            elif state.get("awaiting_task"):
                confirmation = self.split_confirm_last(prompt)
                if confirmation:
                    selector, remaining = confirmation
                else:
                    selector = prompt.strip()
            if not selector:
                self.emit_choices(sid, pending=prompt, event_name=hook_event)
                return
            try:
                tasks = self.list_tasks()
            except Exception as exc:
                self.log("task_list_failed", session=sid, error=type(exc).__name__)
                self.emit_choices(sid, pending=pending or remaining, event_name=hook_event)
                return
            if self.split_confirm_last(selector) or selector.casefold() in self.confirm_words():
                selected = self.resolve_last(tasks)
            else:
                selected = self.select_task(selector, tasks)
            if selected is False:
                if self.looks_like_work(selector) and not remaining:
                    self.emit_choices(sid, pending=pending or selector, event_name=hook_event)
                else:
                    self.emit_choices(sid, pending=pending or remaining, error=f"未找到唯一匹配项：{selector}", event_name=hook_event)
                return
            binding = self.bind(sid, selected if isinstance(selected, dict) else None)
            actual = remaining or pending
            self.update_state(sid, pending_prompt=None, awaiting_task=False, skip_capture_once=False if actual else True)
            if actual:
                prompt = actual
            task_id = self.task_id(binding)
            memory = self.conditional_recall(prompt, task_id, sid)
            context = self.compose(sid, task_id, self.format_binding(binding, actual, announce=True), memory)
            self.emit(context, hook_event)
            self.log("task_bound", session=sid, task=task_id or "agent-wide", recalled=len(memory))
            return

        if action == "select" and command:
            try:
                selected = self.select_task(command[1], self.list_tasks())
            except Exception as exc:
                self.log("task_select_failed", session=sid, error=type(exc).__name__)
                selected = False
            if selected is False:
                try:
                    visible_tasks = self.list_tasks()
                except Exception:
                    visible_tasks = []
                self.emit(self.format_choices(visible_tasks, error=f"未找到唯一匹配项：{command[1]}；现有绑定未改变", required=False), hook_event)
                self.update_state(sid, skip_capture_once=True)
                return
            binding = self.bind(sid, selected if isinstance(selected, dict) else None)
            prompt = command[2]
            if not prompt:
                self.emit(self.compose(sid, self.task_id(binding), self.format_binding(binding, announce=True)), hook_event)
                self.update_state(sid, skip_capture_once=True)
                return

        self.update_state(sid, prompt=prompt, at=datetime.now(timezone.utc).isoformat())
        task_id = self.task_id(binding)
        memory = self.conditional_recall(prompt, task_id, sid)
        announce = self.mark_announced(sid, state)
        capability = str(self.cfg.get("capability_hint") or "") if self.cfg.get("include_capability") else ""
        context = self.compose(sid, task_id, self.format_binding(binding, announce=announce), memory, capability)
        self.emit(context, hook_event)
        self.log("recalled" if memory else "no_recall_hits", session=sid, task=task_id or "agent-wide", announce=announce, chars=len(memory))

    def on_stop(self, event: dict[str, Any]) -> None:
        reason = str(event.get("reason") or "")
        if reason and reason not in ("end_turn", "completed", ""):
            return
        sid = self.session_id(event)
        state = self.load_state(sid)
        if state.get("skip_capture_once"):
            self.update_state(sid, skip_capture_once=None)
            self.log("skip_capture", session=sid, reason="control_turn")
            return
        binding = self.binding(state) or self.load_last_binding()
        if not binding:
            self.log("skip_capture", session=sid, reason="task_not_bound")
            return
        prompt = str(state.get("prompt") or self.prompt_from(event) or "")
        reply = self.assistant_from(event)
        if not prompt or not reply:
            self.log("skip_capture", session=sid, prompt=bool(prompt), reply=bool(reply))
            return
        if self.cfg.get("capture_enabled", True) is False:
            self.log("skip_capture", session=sid, reason="disabled")
            return
        try:
            result = self.post(
                "/v3/conversation/add",
                {**self.isolation(sid, self.task_id(binding)), "messages": [
                    {"role": "user", "content": self.clip(prompt, MAX_PROMPT)},
                    {"role": "assistant", "content": self.clip(reply, MAX_PROMPT)},
                ]},
            )
            self.log("captured", session=sid, accepted=result.get("accepted_ids"))
        except Exception as exc:
            self.log("capture_failed", session=sid, error=type(exc).__name__)

    def run(self) -> int:
        name = self.event_name(self.event)
        try:
            if name in ("session_start", "sessionstart"):
                self.on_session_start(self.event)
            elif name in ("user_prompt_submit", "userpromptsubmit", "before_submit_prompt"):
                self.on_prompt(self.event)
            elif name in ("stop", "session_end", "sessionend"):
                self.on_stop(self.event)
            else:
                self.log("ignore_event", event_name=name or "empty", keys=sorted(self.event.keys()))
        except Exception as exc:
            self.log("hook_crashed", error=type(exc).__name__)
        return 0


def read_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        value = json.loads(raw) if raw.strip() else {}
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def status() -> int:
    try:
        cfg_path = Hook.resolve_config_path()
        cfg = Hook.load_config(cfg_path)
        print(f"TDAI Standard Hook {VERSION}")
        print(f"Config: {cfg_path}")
        print(f"Team: {cfg.get('team_name') or cfg['team_id']} ({cfg['team_id']})")
        print(f"Agent: {cfg.get('agent_name') or cfg['agent_id']} ({cfg['agent_id']})")
        print(f"State: {Hook.resolve_state_dir(cfg, cfg_path)}")
        return 0
    except Exception as exc:
        print(f"tdai-hook status failed: {type(exc).__name__}: {exc}")
        return 1


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg]
    if any(arg in ("--version", "version") for arg in args):
        print(VERSION)
        return 0
    if any(arg in ("--status", "status") for arg in args):
        return status()
    if any(arg in ("--contract", "contract") for arg in args):
        print("JSON stdin -> hookSpecificOutput.additionalContext JSON stdout; events: SessionStart, UserPromptSubmit, Stop")
        return 0
    if any(arg in ("--list", "list") for arg in args):
        try:
            hook = Hook({"client": os.environ.get("TDAI_CLIENT") or cli_value("client") or "generic"})
            print(hook.format_choices(hook.list_tasks(), required=False))
            return 0
        except Exception as exc:
            print(f"task list failed: {type(exc).__name__}: {exc}")
            return 1
    event = read_event()
    try:
        return Hook(event).run()
    except Exception:
        # Config errors are fail-open for hook runners.  No traceback/secret is
        # printed to stdout because some hosts treat any output as context.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
