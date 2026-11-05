import base64
import contextlib
import errno
import http.server
import importlib.util
import io
import json
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


def load_module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parents[1] / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load_module("checks")
configure = load_module("configure").configure


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        key = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(32)
        self.config = {
            "cloudflare_account_id": "a" * 32,
            "cloudflare_zone_id": "b" * 32,
            "zone_name": "example.com",
            "access_team_name": "test-team",
            "admin_email": "admin@example.com",
            "ssh_public_key": "ssh-ed25519 " + base64.b64encode(key).decode(),
        }
        self.deployment = {
            "account_id": "a" * 32,
            "tunnel_id": "tunnel-id",
            "hostnames": {
                "blog": "blog.example.com",
                "admin": "ghost-admin.example.com",
                "ssh": "ghost-ssh.example.com",
            },
            "team_name": "test-team",
            "server_id": "789",
            "firewall_id": "123",
            "ipv4": "192.0.2.1",
            "ipv6": "2001:db8::1",
        }

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    def test_valid_configuration(self):
        result = checks.configuration(self.write("config.json", self.config))
        self.assertEqual(result["server_type"], "cx23")

    def test_rejects_untrusted_names_and_keys(self):
        for key, value in (
            ("cloudflare_account_id", "../accounts/other"),
            ("zone_name", "example.com/attack"),
            ("zone_name", "example.com\n"),
            ("access_team_name", "team.cloudflareaccess.com.attacker.test"),
            ("ssh_public_key", "ssh-ed25519 AAAA"),
            ("ssh_public_key", self.config["ssh_public_key"] + "\ncommand=evil"),
            ("subdomains", {"blog": "same", "admin": "same", "ssh": "ssh"}),
            ("subdomains", {"blog": "a.b", "admin": "admin", "ssh": "ssh"}),
        ):
            with (
                self.subTest(field=key, value=value),
                self.assertRaises(checks.DeploymentError),
            ):
                checks.configuration(
                    self.write("invalid.json", {**self.config, key: value})
                )

    def test_refuses_destruction_and_replacement(self):
        for actions in (["delete"], ["delete", "create"], ["create", "delete"]):
            plan = {
                "resource_changes": [
                    {"address": "hcloud_server.ghost", "change": {"actions": actions}}
                ]
            }
            with (
                self.subTest(actions=actions),
                self.assertRaisesRegex(checks.DeploymentError, "Refusing"),
            ):
                checks.check_plan(self.write("plan.json", plan))
        for actions in (["create"], ["update"], ["no-op"]):
            checks.check_plan(
                self.write(
                    "plan.json",
                    {
                        "resource_changes": [
                            {"address": "resource", "change": {"actions": actions}}
                        ]
                    },
                )
            )

    def fake_api(self, provider, path):
        if path.startswith("/zones/") and "/dns_records" not in path:
            return {
                "result": {
                    "account": {"id": "a" * 32},
                    "name": "example.com",
                    "status": "active",
                }
            }
        if path.endswith("/access/organizations"):
            return {"result": {"auth_domain": "test-team.cloudflareaccess.com"}}
        if path.endswith("/access/identity_providers"):
            return {"result": [{"type": "onetimepin"}]}
        if "/dns_records" in path:
            return {"result": []}
        if path.startswith("/server_types"):
            return {"server_types": [{"architecture": "x86", "memory": 4}]}
        if path.startswith("/locations"):
            return {"locations": [{"name": "fsn1"}]}
        self.fail(f"Unexpected API request: {provider} {path}")

    def test_preflight_dns_ownership_and_resume(self):
        config = self.write("config.json", self.config)
        state = self.write("state.json", {})
        with (
            patch.object(checks, "api", side_effect=self.fake_api),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            checks.preflight(config, state)

        def occupied(provider, path):
            if "/dns_records" in path:
                return {"result": [{"id": "existing"}]}
            return self.fake_api(provider, path)

        with patch.object(checks, "api", side_effect=occupied):
            with self.assertRaisesRegex(
                checks.DeploymentError, "outside this deployment"
            ):
                checks.preflight(config, state)
            owned = {
                "values": {
                    "root_module": {
                        "resources": [
                            {
                                "type": "cloudflare_dns_record",
                                "name": "ghost",
                                "index": kind,
                                "values": {"id": "existing"},
                            }
                            for kind in ("blog", "admin", "ssh")
                        ]
                    }
                }
            }
            with contextlib.redirect_stdout(io.StringIO()):
                checks.preflight(config, self.write("state.json", owned))

    def test_rejects_inactive_zone(self):
        with (
            patch.object(
                checks,
                "api",
                return_value={
                    "result": {
                        "account": {"id": "a" * 32},
                        "name": "example.com",
                        "status": "pending",
                    }
                },
            ),
            self.assertRaisesRegex(checks.DeploymentError, "must be active"),
        ):
            checks.preflight(
                self.write("config.json", self.config), self.write("state.json", {})
            )

    def test_access_requires_real_login_redirect(self):
        for status, location in (
            (200, ""),
            (403, ""),
            (302, "http://test-team.cloudflareaccess.com/login"),
            (302, "https://test-team.cloudflareaccess.com.attacker.test/login"),
            (302, "https://test-team.cloudflareaccess.com:8443/login"),
            (302, "https://user@test-team.cloudflareaccess.com/login"),
        ):
            with (
                self.subTest(status=status, location=location),
                patch.object(
                    checks,
                    "request",
                    return_value=(status, {"Location": location}, b""),
                ),
                self.assertRaises(checks.DeploymentError),
            ):
                checks.check_access("ghost-admin.example.com", "test-team")
        with patch.object(
            checks,
            "request",
            return_value=(
                302,
                {
                    "Location": "https://test-team.cloudflareaccess.com/cdn-cgi/access/login"
                },
                b"",
            ),
        ):
            checks.check_access("ghost-admin.example.com", "test-team")

    def test_rejects_extra_firewalls_or_inbound_rules(self):
        for rules, attached in (
            ([{"direction": "in", "port": "22"}], [{"id": 123, "status": "applied"}]),
            ([], [{"id": 123, "status": "pending"}]),
            ([], [{"id": 123, "status": "applied"}, {"id": 999, "status": "applied"}]),
        ):
            with (
                patch.object(
                    checks,
                    "api",
                    side_effect=[
                        {"firewall": {"rules": rules}},
                        {"server": {"public_net": {"firewalls": attached}}},
                    ],
                ),
                self.assertRaises(checks.DeploymentError),
            ):
                checks.check_firewall(self.deployment)

    def test_readiness_rejects_exposed_admin(self):
        with (
            patch.object(checks, "api", return_value={"result": {"status": "healthy"}}),
            patch.object(
                checks,
                "request",
                side_effect=[
                    (200, {}, b""),
                    (308, {"Location": "https://blog.example.com/"}, b""),
                    (200, {}, b""),
                ],
            ),
            self.assertRaisesRegex(checks.DeploymentError, "block Ghost admin"),
        ):
            checks.check_ready(self.deployment)

    def test_bootstrap_preserves_database_credentials(self):
        self.write("config.base.json", {"database": {"connection": {"host": "db"}}})
        with patch("os.chown"):
            configure(self.root)
            original = (self.root / ".env").read_bytes()
            first_config = json.loads(
                (self.root / "config.production.json").read_text()
            )
            (self.root / "config.production.json").unlink()
            configure(self.root)
        self.assertEqual((self.root / ".env").read_bytes(), original)
        self.assertEqual(
            json.loads((self.root / "config.production.json").read_text()), first_config
        )
        self.assertEqual((self.root / ".env").stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.root / "config.production.json").stat().st_mode & 0o777, 0o400
        )

    def test_readiness_timeout_retains_resources(self):
        state = self.write("state.json", {"deployment": {"value": self.deployment}})
        with (
            patch.object(checks, "check_firewall"),
            patch.object(
                checks, "check_ready", side_effect=checks.DeploymentError("Tunnel down")
            ),
            self.assertRaisesRegex(checks.DeploymentError, "Resources were retained"),
        ):
            checks.verify(state, timeout=0)

    def test_open_public_port_fails(self):
        with (
            patch.object(checks.socket, "create_connection"),
            self.assertRaisesRegex(
                checks.DeploymentError, "Unexpected public listener"
            ),
        ):
            checks.check_ports(self.deployment)

    def test_local_network_failure_is_not_a_successful_port_check(self):
        with (
            patch.object(
                checks.socket,
                "create_connection",
                side_effect=OSError(errno.EACCES, "Blocked locally"),
            ),
            self.assertRaisesRegex(checks.DeploymentError, "Cannot probe"),
        ):
            checks.check_ports(self.deployment)

    def test_reports_unavailable_ipv6(self):
        def connect(address, timeout):
            if ":" in address[0]:
                raise OSError(errno.ENETUNREACH, "No IPv6")
            raise TimeoutError

        output = io.StringIO()
        with (
            patch.object(checks.socket, "create_connection", side_effect=connect),
            contextlib.redirect_stdout(output),
        ):
            checks.check_ports(self.deployment)
        self.assertIn("IPv6 probes unavailable", output.getvalue())

    def test_credentials_are_not_forwarded_on_redirect(self):
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                self.send_response(302)
                self.send_header("Location", "/credential-sink")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            status, _, _ = checks.request(
                f"http://127.0.0.1:{server.server_port}/api",
                {"Authorization": "Bearer test-secret"},
            )
            self.assertEqual(status, 302)
            self.assertEqual(seen, [("/api", "Bearer test-secret")])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
