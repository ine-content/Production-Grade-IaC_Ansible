#!/usr/bin/env python3
"""
mock_device_server.py - Production-Grade IaC with Ansible: mock RESTCONF
device fleet.

Stands in for real Cisco hardware, the same way it did in
CI-CD_Pipeline_with_Git - except this course has no iac_lib.py for it to
import from, because there is no hand-written Python pipeline here at all.
Ansible plays talk RESTCONF directly (via ansible.netcommon.restconf_config
/ restconf_get, or the uri module), against inventory/devices.py's
ansible_host/restconf_port/restconf_path host vars. This script is what
actually answers those requests - it is standalone on purpose, so it can
be started before any playbook run and needs nothing from this course's
other files except devices/*.json and sites/*.json.

At startup, this reads every devices/<site_id>.json file and, for every
device listed there, starts its own tiny HTTP server bound to exactly that
device's own ip_address:restconf_port - indistinguishable, from a
playbook's point of view, from a real device's RESTCONF API.

This is fully dynamic, on purpose, exactly like inventory/devices.py:

  - Add a new device to an existing devices/<site_id>.json file and it is
    served automatically the next time this script starts.

  - Add an entirely new site (a new devices/<site_id>.json file, plus the
    matching sites/<site_id>.json) and it is discovered the same way -
    this script globs devices/*.json and sites/*.json, it does not
    hardcode a fixed list of sites.

Placeholder IPs live in 127.0.0.0/8 (loopback) - the whole /8 is
loopback-routable on Linux, including every GitLab CI runner, with zero
extra configuration. On macOS, run `sudo ./setup_local_loopback.sh` once
per reboot before running this locally (a no-op on Linux).

This fleet's memory survives between separate runs, on purpose - state is
persisted to mock_device_state.json (git-ignored), so drift introduced by
a manual out-of-band change between two ansible-playbook runs is still
there to be caught on the next one.

Credentials are genuinely checked. Each device belongs to a site, and each
site belongs to an environment (prod or staging) - this script resolves
that chain and expects Basic Auth matching that environment's
RESTCONF_<ENV>_USERNAME / RESTCONF_<ENV>_PASSWORD environment variables -
the same names a playbook's tasks read via lookup('env', ...). A request
with no credentials, or the wrong ones, gets a real 401.

Usage:
    python mock_device_server.py
    (Ctrl+C to stop. All state is in memory + mock_device_state.json,
    and resets only if you delete that file.)
"""

import base64
import json
import os
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DEVICES_DIR = ROOT / "devices"
SITES_DIR = ROOT / "sites"
STATE_FILE = ROOT / "mock_device_state.json"

# device_id -> last pushed payload (dict). Shared across every per-device
# server thread. Loaded from STATE_FILE at startup, written back after
# every successful PATCH.
STATE = {}
STATE_LOCK = threading.Lock()


def _load_dotenv(env_path=None):
    """Minimal, dependency-free .env loader for local runs only - same
    pattern CI-CD_Pipeline_with_Git's iac_lib.py used, ported here since
    this course has no shared library to put it in. A real GitLab
    pipeline never touches this - protected CI/CD variables are injected
    directly into the job's environment before Ansible even starts.
    Anything already present in os.environ always wins."""
    path = env_path or (ROOT / ".env")
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def restconf_credential_env_vars(environment_name):
    """('RESTCONF_PROD_USERNAME', 'RESTCONF_PROD_PASSWORD') for
    environment_name="prod", etc. Must match the names a playbook's tasks
    read via lookup('env', ...) - centralized here so this mock and any
    play checking for a "credentials not set" warning always agree."""
    prefix = f"RESTCONF_{environment_name.upper()}"
    return f"{prefix}_USERNAME", f"{prefix}_PASSWORD"


def restconf_path_for(platform):
    """Must match inventory/devices.py's RESTCONF_PATHS exactly - a real
    device's RESTCONF path is fixed by its own YANG model, not something
    either side invents independently."""
    if platform == "cat8k":
        return "/restconf/data/Cisco-IOS-XE-native:native/router/ospf"
    return "/restconf/data/nexus-vlan-database"


def discover_devices():
    """Every device across every devices/<site_id>.json file, discovered
    dynamically - same rule inventory/devices.py follows."""
    devices = []
    for device_file in sorted(DEVICES_DIR.glob("*.json")):
        for entry in json.loads(device_file.read_text(encoding="utf-8")):
            devices.append(entry)
    return devices


def discover_site_environments():
    """site_id -> environment name ("prod"/"staging"/...), read from
    sites/*.json. Used only to figure out which environment's credentials
    each device should be checked against."""
    environments_by_site = {}
    for site_file in sorted(SITES_DIR.glob("*.json")):
        site = json.loads(site_file.read_text(encoding="utf-8"))
        environments_by_site[site["site_id"]] = site["environment"]
    return environments_by_site


def _load_persisted_state():
    """Read mock_device_state.json from the previous run, if any. Returns
    an empty dict on first-ever run, or if the file is missing/corrupt."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _persist_state_locked():
    """Write the in-memory STATE dict to disk. Caller must already hold
    STATE_LOCK."""
    STATE_FILE.write_text(json.dumps(STATE, indent=2), encoding="utf-8")


def expected_credentials_for_environment(environment_name):
    """The (username, password) this mock expects for a given
    environment, read from the same OS environment variables (and the
    same .env file) a real playbook's tasks read. If a student hasn't set
    up credentials yet, both come back empty - and since a real device
    password is never empty, every request is correctly rejected with 401
    until real values exist."""
    username_var, password_var = restconf_credential_env_vars(environment_name)
    return os.environ.get(username_var, ""), os.environ.get(password_var, "")


def parse_basic_auth(header_value):
    """Decode an "Authorization: Basic ..." header into (username,
    password), or None if it's missing, malformed, or a different auth
    scheme entirely."""
    if not header_value or not header_value.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header_value[len("Basic "):]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in decoded:
        return None
    username, _, password = decoded.partition(":")
    return username, password


def make_handler(device_id, expected_path, expected_credentials):
    """Build a request handler class bound to one specific device."""

    class DeviceHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _write_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            provided = parse_basic_auth(self.headers.get("Authorization"))
            if provided != expected_credentials:
                self._write_json(401, {"error": "unauthorized - bad or missing RESTCONF credentials"})
                return False
            return True

        def do_PATCH(self):
            if not self._authorized():
                return

            if self.path != expected_path:
                self._write_json(404, {"error": f"unknown RESTCONF path: {self.path}"})
                return

            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw_body or b"{}")
            except json.JSONDecodeError:
                self._write_json(400, {"error": "invalid JSON body"})
                return

            with STATE_LOCK:
                STATE[device_id] = payload
                _persist_state_locked()

            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self._authorized():
                return

            if self.path != expected_path:
                self._write_json(404, {"error": f"unknown RESTCONF path: {self.path}"})
                return

            with STATE_LOCK:
                payload = STATE.get(device_id, {})
            self._write_json(200, payload)

        def log_message(self, fmt, *args):
            sys.stderr.write(f"[{device_id}] {fmt % args}\n")

    return DeviceHandler


class _NoReverseDnsHTTPServer(ThreadingHTTPServer):
    """Identical to ThreadingHTTPServer, except server_bind() skips the
    reverse DNS lookup (socket.getfqdn()) that http.server.HTTPServer
    normally does to set self.server_name. That lookup is never used by
    this mock, but in an environment with broken or absent DNS - like
    this course's offline lab VMs - it can hang for a long time per
    device, since each socket.getfqdn() call may block waiting on a DNS
    query that will never resolve. With 9 devices starting in a tight
    loop, even one slow lookup stalls every device after it - this was a
    real, previously-undiscovered bug in CI-CD_Pipeline_with_Git
    (surfaced as "Mock device fleet did not come up within Ns" in real
    GitLab CI runs), ported here from the start rather than waiting to
    hit it again. Skipping straight to socketserver.TCPServer.server_bind()
    avoids the lookup entirely and binds instantly."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def start_device_server(device, expected_credentials):
    """One _NoReverseDnsHTTPServer per device. Each push does a GET
    (drift check) immediately followed by a PATCH - two separate
    connections in quick succession - and with protocol_version =
    "HTTP/1.1", a plain HTTPServer can end up still blocked handling the
    first connection's keep-alive teardown when the second one arrives.
    ThreadingHTTPServer hands each connection its own thread, so this
    never happens."""
    handler_cls = make_handler(
        device["device_id"], restconf_path_for(device["platform"]), expected_credentials
    )
    server = _NoReverseDnsHTTPServer((device["ip_address"], device["restconf_port"]), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def main():
    devices = discover_devices()
    if not devices:
        print("No devices found under devices/*.json - nothing to serve.")
        sys.exit(1)

    with STATE_LOCK:
        STATE.update(_load_persisted_state())
    if STATE:
        print(f"[mock] restored state for {len(STATE)} device(s) from {STATE_FILE.name}", flush=True)

    environments_by_site = discover_site_environments()

    servers = []
    warned_environments = set()
    for device in devices:
        environment_name = environments_by_site.get(device["site_id"])
        if environment_name is None:
            print(
                f"[mock] WARNING: {device['device_id']} references unknown site "
                f"'{device['site_id']}' - skipping.",
                flush=True,
            )
            continue

        expected_credentials = expected_credentials_for_environment(environment_name)
        if expected_credentials == ("", "") and environment_name not in warned_environments:
            username_var, password_var = restconf_credential_env_vars(environment_name)
            print(
                f"[mock] WARNING: {username_var}/{password_var} are not set. Every "
                f"request to a '{environment_name}' device will get 401 until you "
                f"set real values (see .env.example).",
                flush=True,
            )
            warned_environments.add(environment_name)

        server, thread = start_device_server(device, expected_credentials)
        servers.append(server)
        path = restconf_path_for(device["platform"])
        print(
            f"[mock] {device['device_id']} ({device['platform']}, {environment_name}) "
            f"listening on http://{device['ip_address']}:{device['restconf_port']}{path}",
            flush=True,
        )

    print(
        f"[mock] {len(servers)} device(s) up across "
        f"{len(sorted(DEVICES_DIR.glob('*.json')))} site(s). Press Ctrl+C to stop.",
        flush=True,
    )

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[mock] shutting down.", flush=True)
        for server in servers:
            server.shutdown()


if __name__ == "__main__":
    main()
