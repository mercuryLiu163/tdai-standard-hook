from __future__ import annotations

import json
import os
import threading
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "tdai-hook.py"


class StandardHookProtocolTests(unittest.TestCase):
    def run_hook(
        self, event: dict, state: Path, config: Path, *args: str,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[dict, str]:
        env = os.environ.copy()
        env.update({"TDAI_CONFIG": str(config), "TDAI_STATE_DIR": str(state)})
        env.update(extra_env or {})
        result = subprocess.run(
            [sys.executable, str(ENTRY), *args],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        return (json.loads(result.stdout) if result.stdout.strip() else {}, result.stderr)

    def test_normal_prompt_is_fail_open_and_does_not_recall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            config = root / "config.json"
            config.write_text(json.dumps({
                "endpoint": "http://127.0.0.1:1",
                "user_key": "test",
                "user_id": "usr-test",
                "team_id": "team-test",
                "agent_id": "agt-test",
                "team_name": "test",
                "agent_name": "test",
                "require_task_selection": False,
            }), encoding="utf-8")
            state.mkdir()
            (state / "s1.json").write_text(json.dumps({
                "task_binding": {"mode": "task", "task_id": "task-1", "title": "test"},
                "binding_announced": True,
            }), encoding="utf-8")
            output, _ = self.run_hook({
                "hook_event_name": "UserPromptSubmit",
                "session_id": "s1",
                "prompt": "写一个偶数判断函数",
                "client": "codex",
            }, state, config)
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn("tdai-task-binding", context)
            self.assertNotIn("tdai-memory", context)
            log = (state / "hook.log").read_text(encoding="utf-8")
            self.assertIn("enabled=false", log)
            self.assertIn("memory=0", log)

    def test_aliases_and_escaped_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            state = root / "state"
            config.write_text(json.dumps({
                "endpoint": "http://127.0.0.1:1", "user_key": "x", "user_id": "u",
                "team_id": "t", "agent_id": "a", "require_task_selection": False,
            }), encoding="utf-8")
            state.mkdir()
            (state / "s2.json").write_text(json.dumps({
                "task_binding": {"mode": "agent", "title": "跨 Task"},
                "binding_announced": True,
            }), encoding="utf-8")
            output, _ = self.run_hook({
                "hookEventName": "UserPromptSubmit", "sessionId": "s2",
                "userPrompt": "hello", "client": "zcode",
            }, state, config)
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
            self.assertIn("Agent:", output["hookSpecificOutput"]["additionalContext"])

    def test_cli_client_selects_profile_without_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            state = root / "state"
            config.write_text(json.dumps({
                "endpoint": "http://127.0.0.1:1", "user_key": "x", "user_id": "u",
                "team_id": "t", "agent_id": "a", "agent_name": "root-agent",
                "require_task_selection": False,
                "profiles": {"zcode": {"client": "zcode", "agent_name": "zcode-profile-agent"}},
            }), encoding="utf-8")
            state.mkdir()
            (state / "s-cli.json").write_text(json.dumps({
                "task_binding": {"mode": "agent", "title": "跨 Task"},
                "binding_announced": True,
            }), encoding="utf-8")
            output, _ = self.run_hook({
                "hook_event_name": "UserPromptSubmit", "session_id": "s-cli",
                "prompt": "hello",
            }, state, config, "--client", "zcode", extra_env={
                "TDAI_PROFILE": "legacy-global", "TDAI_CLIENT": "legacy-global",
            })
            self.assertIn("zcode-profile-agent", output["hookSpecificOutput"]["additionalContext"])
            log = (state / "hook.log").read_text(encoding="utf-8")
            self.assertIn("client=zcode", log)

    def test_recall_and_stop_use_task_isolation(self) -> None:
        calls: list[tuple[str, dict]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib protocol name
                length = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                calls.append((self.path, body))
                if self.path == "/v3/atomic/search":
                    data = {"items": [{"type": "episodic", "content": "remembered"}]}
                elif self.path == "/v3/core/read":
                    data = {"content": "persona"}
                elif self.path == "/v3/scenario/ls":
                    data = {"entries": [{"path": "scene/demo"}]}
                else:
                    data = {"accepted_ids": ["msg-test"]}
                payload = json.dumps({"code": 0, "data": data}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = root / "state"
                state.mkdir()
                config = root / "config.json"
                config.write_text(json.dumps({
                    "endpoint": f"http://127.0.0.1:{server.server_address[1]}",
                    "user_key": "test", "user_id": "usr-test", "team_id": "team-test",
                    "agent_id": "agt-test", "require_task_selection": False,
                }), encoding="utf-8")
                (state / "s3.json").write_text(json.dumps({
                    "task_binding": {"mode": "task", "task_id": "task-7", "title": "demo"},
                    "binding_announced": True,
                }), encoding="utf-8")
                output, _ = self.run_hook({
                    "hook_event_name": "UserPromptSubmit", "session_id": "s3",
                    "prompt": "请回忆之前的 demo 约定", "client": "deepseek",
                }, state, config)
                self.assertIn("remembered", output["hookSpecificOutput"]["additionalContext"])
                self.run_hook({
                    "hook_event_name": "Stop", "session_id": "s3",
                    "last_assistant_message": "done", "client": "deepseek",
                }, state, config)
                self.assertEqual([path for path, _ in calls], [
                    "/v3/atomic/search", "/v3/core/read", "/v3/scenario/ls", "/v3/conversation/add",
                ])
                for _path, body in calls:
                    self.assertEqual(body["team_id"], "team-test")
                    self.assertEqual(body["agent_id"], "agt-test")
                    self.assertEqual(body.get("task_id"), "task-7")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_stop_falls_back_to_last_binding_and_event_prompt(self) -> None:
        calls: list[tuple[str, dict]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib protocol name
                length = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                calls.append((self.path, body))
                payload = json.dumps({"code": 0, "data": {"accepted_ids": ["msg-fallback"]}}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = root / "state"
                state.mkdir()
                (state / "last-binding.json").write_text(json.dumps({
                    "mode": "task", "task_id": "task-last", "title": "last task",
                }), encoding="utf-8")
                config = root / "config.json"
                config.write_text(json.dumps({
                    "endpoint": f"http://127.0.0.1:{server.server_address[1]}",
                    "user_key": "test", "user_id": "usr-test", "team_id": "team-test",
                    "agent_id": "agt-test", "require_task_selection": False,
                }), encoding="utf-8")
                output, _ = self.run_hook({
                    "hook_event_name": "Stop", "session_id": "new-session",
                    "prompt": "来自 Stop 事件的真实请求",
                    "last_assistant_message": "来自 Stop 事件的真实回复",
                    "client": "agy",
                }, state, config)
                self.assertEqual(output, {})
                self.assertEqual([path for path, _ in calls], ["/v3/conversation/add"])
                body = calls[0][1]
                self.assertEqual(body["task_id"], "task-last")
                self.assertEqual(body["session_id"], "new-session")
                self.assertEqual(body["messages"], [
                    {"role": "user", "content": "来自 Stop 事件的真实请求"},
                    {"role": "assistant", "content": "来自 Stop 事件的真实回复"},
                ])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
