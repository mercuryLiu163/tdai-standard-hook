from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from install import command, verify_config_identity


class InstallIdentityTests(unittest.TestCase):
    def test_command_can_select_client_without_environment_variable(self) -> None:
        self.assertTrue(command(Path("/tmp/tdai"), "zcode").endswith(" --client zcode"))

    def test_apply_corrects_stale_user_id_without_changing_key(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/v3/meta/auth/verify":
                    data = {"valid": True, "user": {"user_id": "usr-owner", "username": "demo"}}
                elif self.path == "/v3/meta/agent/get" and body.get("agent_id") == "agt-test":
                    data = {
                        "agent_id": "agt-test",
                        "team_id": "team-test",
                        "owner_user_id": "usr-owner",
                    }
                else:
                    data = {}
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
                path = Path(directory) / "config.json"
                path.write_text(json.dumps({
                    "endpoint": f"http://127.0.0.1:{server.server_address[1]}",
                    "service_id": "default",
                    "user_key": "secret-key",
                    "user_id": "usr-stale",
                    "team_id": "team-test",
                    "agent_id": "agt-test",
                }), encoding="utf-8")
                ok, detail = verify_config_identity(path, apply=True)
                self.assertTrue(ok, detail)
                updated = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(updated["user_id"], "usr-owner")
                self.assertEqual(updated["user_key"], "secret-key")
                self.assertEqual(len(list(path.parent.glob("config.json.bak-identity-*"))), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
