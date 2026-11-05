import base64
import errno
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class DeploymentError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
            return response.status, response.headers, response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as error:
        return error.code, error.headers, b""
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise DeploymentError(
            f"Cannot connect to {urllib.parse.urlsplit(url).hostname}."
        ) from error


def api(provider, path):
    roots = {
        "cloudflare": ("https://api.cloudflare.com/client/v4", "CLOUDFLARE_API_TOKEN"),
        "hetzner": ("https://api.hetzner.cloud/v1", "HCLOUD_TOKEN"),
    }
    root, variable = roots[provider]
    token = os.environ.get(variable)
    if not token:
        raise DeploymentError(f"Set {variable}.")
    status, _, body = request(root + path, {"Authorization": f"Bearer {token}"})
    if status != 200:
        raise DeploymentError(
            f"{provider} API returned HTTP {status} for {path}; check token permissions and configuration."
        )
    try:
        data = json.loads(body)
    except ValueError as error:
        raise DeploymentError(f"Invalid response from {provider}.") from error
    if provider == "cloudflare" and not data.get("success"):
        raise DeploymentError("Cloudflare rejected the API request.")
    return data


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise DeploymentError(f"Cannot read JSON file: {path}") from error


def configuration(path):
    config = {
        "deployment_name": "ghost-blog",
        "subdomains": {"blog": "blog", "admin": "ghost-admin", "ssh": "ghost-ssh"},
        "server_type": "cx23",
        "location": "fsn1",
    }
    supplied = read_json(path)
    if not isinstance(supplied, dict):
        raise DeploymentError("Configuration must be a JSON object.")
    config.update(supplied)
    patterns = {
        "deployment_name": r"[a-z][a-z0-9-]{0,30}[a-z0-9]",
        "cloudflare_account_id": r"[a-f0-9]{32}",
        "cloudflare_zone_id": r"[a-f0-9]{32}",
        "zone_name": r"([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
        "access_team_name": r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?",
        "admin_email": r"[^@\s]+@[^@\s]+\.[^@\s]+",
        "server_type": r"[a-z0-9-]+",
        "location": r"[a-z0-9-]+",
    }
    for name, pattern in patterns.items():
        if not isinstance(config.get(name), str) or not re.fullmatch(
            pattern, config[name]
        ):
            raise DeploymentError(f"Invalid or missing configuration field: {name}")
    labels = config["subdomains"]
    if not isinstance(labels, dict) or set(labels) != {"blog", "admin", "ssh"}:
        raise DeploymentError("subdomains must contain blog, admin, and ssh.")
    if any(
        not isinstance(label, str)
        or not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels.values()
    ):
        raise DeploymentError("Use single-label subdomains.")
    if len(set(labels.values())) != 3 or any(
        len(label + "." + config["zone_name"]) > 253 for label in labels.values()
    ):
        raise DeploymentError(
            "Hostnames must be distinct and no longer than 253 characters."
        )
    key = config.get("ssh_public_key", "")
    if not isinstance(key, str) or not re.fullmatch(
        r"ssh-ed25519 [A-Za-z0-9+/]+={0,3}( [^\r\n]*)?", key
    ):
        raise DeploymentError(
            "Supply an OpenSSH Ed25519 public key without key options."
        )
    try:
        blob = base64.b64decode(key.split()[1], validate=True)
        prefix = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32)
        if not blob.startswith(prefix) or len(blob) != len(prefix) + 32:
            raise ValueError
    except ValueError as error:
        raise DeploymentError("Invalid Ed25519 public key encoding.") from error
    return config


def preflight(config_path, state_path):
    config = configuration(config_path)
    state = read_json(state_path)
    owned_dns = {
        resource["index"]: resource["values"]["id"]
        for resource in state.get("values", {})
        .get("root_module", {})
        .get("resources", [])
        if resource.get("type") == "cloudflare_dns_record"
        and resource.get("name") == "ghost"
    }
    account = config["cloudflare_account_id"]
    zone_id = config["cloudflare_zone_id"]
    zone = api("cloudflare", f"/zones/{zone_id}")["result"]
    if (
        zone["account"]["id"] != account
        or zone["name"] != config["zone_name"]
        or zone["status"] != "active"
    ):
        raise DeploymentError(
            "The Cloudflare zone must be active and belong to the configured account and domain."
        )
    organization = api("cloudflare", f"/accounts/{account}/access/organizations")[
        "result"
    ]
    if (
        organization["auth_domain"]
        != config["access_team_name"] + ".cloudflareaccess.com"
    ):
        raise DeploymentError(
            "The configured Access team does not match this Cloudflare account."
        )
    if not api("cloudflare", f"/accounts/{account}/access/identity_providers")[
        "result"
    ]:
        raise DeploymentError(
            "Configure a Cloudflare Access login method first, such as One-time PIN."
        )
    for kind, label in config["subdomains"].items():
        query = urllib.parse.urlencode({"name": label + "." + config["zone_name"]})
        records = api("cloudflare", f"/zones/{zone_id}/dns_records?{query}")["result"]
        if any(record["id"] != owned_dns.get(kind) for record in records):
            raise DeploymentError(
                f"The {kind} hostname already has DNS records outside this deployment; choose an unused hostname."
            )
    types = api(
        "hetzner",
        "/server_types?" + urllib.parse.urlencode({"name": config["server_type"]}),
    )["server_types"]
    if len(types) != 1 or types[0]["architecture"] != "x86" or types[0]["memory"] < 4:
        raise DeploymentError(
            "Select an available x86 Hetzner server type with at least 4 GB RAM."
        )
    locations = api(
        "hetzner", "/locations?" + urllib.parse.urlencode({"name": config["location"]})
    )["locations"]
    if len(locations) != 1:
        raise DeploymentError("Unknown Hetzner location.")
    print(
        "Preflight passed: zone, Access login, DNS ownership, and server configuration.",
        flush=True,
    )


def check_plan(path):
    plan = read_json(path)
    if plan.get("errored"):
        raise DeploymentError("Terraform reported an invalid plan.")
    deletions = [
        change["address"]
        for change in plan.get("resource_changes", [])
        if "delete" in change["change"]["actions"]
    ]
    if deletions:
        raise DeploymentError(
            "Refusing deletion or replacement: " + ", ".join(deletions)
        )


def check_access(hostname, team_name):
    status, headers, _ = request("https://" + hostname + "/ghost/")
    location = urllib.parse.urlsplit(headers.get("Location", ""))
    if (
        status not in (302, 303)
        or location.scheme != "https"
        or location.netloc != team_name + ".cloudflareaccess.com"
    ):
        raise DeploymentError(
            "Cloudflare Access login is not confirmed for " + hostname
        )


def check_ready(deployment):
    tunnel = api(
        "cloudflare",
        f"/accounts/{deployment['account_id']}/cfd_tunnel/{deployment['tunnel_id']}",
    )["result"]
    if tunnel.get("status") != "healthy":
        raise DeploymentError("Waiting for a healthy tunnel.")
    blog = "https://" + deployment["hostnames"]["blog"]
    status, _, _ = request(
        blog + "/?deployment_check=" + str(time.time_ns()),
        {"Cache-Control": "no-cache"},
    )
    if status != 200:
        raise DeploymentError(f"Blog readiness returned HTTP {status}.")
    status, headers, _ = request("http://" + deployment["hostnames"]["blog"] + "/")
    location = urllib.parse.urlsplit(headers.get("Location", ""))
    if (
        status not in (301, 302, 307, 308)
        or location.scheme != "https"
        or location.netloc != deployment["hostnames"]["blog"]
    ):
        raise DeploymentError("HTTP visitors must be redirected to the HTTPS blog.")
    for path in (
        "/ghost/",
        "/Ghost/",
        "/%67host/",
        "/ghost/api/admin/authentication/setup/",
    ):
        status, _, _ = request(blog + path)
        if status != 404:
            raise DeploymentError("The public blog must block Ghost admin routes.")
    for kind in ("admin", "ssh"):
        check_access(deployment["hostnames"][kind], deployment["team_name"])


def check_firewall(deployment):
    expected = int(deployment["firewall_id"])
    firewall = api("hetzner", f"/firewalls/{expected}")["firewall"]
    if firewall["rules"]:
        raise DeploymentError(
            "The deployment firewall must have no rules: inbound denied, outbound allowed."
        )
    server = api("hetzner", f"/servers/{deployment['server_id']}")["server"]
    attached = server["public_net"]["firewalls"]
    if (
        len(attached) != 1
        or attached[0]["id"] != expected
        or attached[0]["status"] != "applied"
    ):
        raise DeploymentError(
            "The expected deny-inbound firewall is not the server's only applied firewall."
        )


def check_ports(deployment):
    for key in ("ipv4", "ipv6"):
        address = deployment[key]
        for port in (22, 80, 443, 2368, 3306, 8080, 8081):
            try:
                connection = socket.create_connection((address, port), timeout=2)
            except OSError as error:
                if key == "ipv6" and error.errno in (51, 65, 101, 113):
                    print(
                        "IPv6 probes unavailable from this machine; verify them from an IPv6-capable host.",
                        flush=True,
                    )
                    break
                if error.errno not in (None, errno.ECONNREFUSED, errno.ETIMEDOUT):
                    raise DeploymentError(
                        f"Cannot probe {address}:{port}; check this machine's network connectivity."
                    ) from error
            else:
                connection.close()
                raise DeploymentError(f"Unexpected public listener: {address}:{port}")


def verify(state_path, timeout=900):
    deployment = read_json(state_path).get("deployment", {}).get("value")
    if not deployment:
        raise DeploymentError("Terraform deployment output is missing.")
    check_firewall(deployment)
    deadline = time.monotonic() + timeout
    next_report = 0
    while True:
        try:
            check_ready(deployment)
            break
        except DeploymentError as error:
            now = time.monotonic()
            if now >= deadline:
                raise DeploymentError(
                    f"Readiness timed out: {error} Resources were retained. Inspect the Hetzner console and /var/log/cloud-init-output.log; see README.md."
                ) from error
            if now >= next_report:
                print(f"Waiting for deployment: {error}", flush=True)
                next_report = now + 30
            time.sleep(5)
    check_ports(deployment)
    hosts = deployment["hostnames"]
    print(
        f"Blog: https://{hosts['blog']}\nAdmin setup: https://{hosts['admin']}/ghost/\nSSH: ssh -o 'ProxyCommand=cloudflared access ssh --hostname %h' ghostadmin@{hosts['ssh']}"
    )
    print(
        "HTTPS, Access login, public admin blocking, and the provider firewall passed verification. Complete owner setup through the protected admin URL."
    )


def main():
    try:
        action, *args = sys.argv[1:]
        if action == "preflight" and len(args) == 2:
            preflight(*args)
        elif action == "plan" and len(args) == 1:
            check_plan(*args)
        elif action == "verify" and len(args) == 1:
            verify(*args)
        else:
            raise DeploymentError(
                "Usage: checks.py preflight CONFIG STATE | plan PLAN | verify STATE"
            )
    except (DeploymentError, KeyError, ValueError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
