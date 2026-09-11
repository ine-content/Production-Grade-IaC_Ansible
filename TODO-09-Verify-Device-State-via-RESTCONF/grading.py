#!/usr/bin/env python3

"""
Production-Grade IaC with Ansible - Coaching-Style Grader (Rich terminal UI)

This grader validates the course one TODO at a time, always starting from
TODO 01, and stops at the first incomplete one - even though TODO 01, 02,
and 03 are already solved for you in this folder, it re-checks them live
every run, so you always see real, current proof that nothing earlier
broke, not a cached checkmark.

TODO 04 is checked by running the real playbook and confirming render_context
was assembled correctly - the right hostname and the right (already-resolved)
vlans - for every one of the 9 devices.

TODO 05 is checked by clearing output/*.cfg, running the real playbook, and
comparing each device's rendered output/<device_id>.cfg against its
reference golden/<site_id>/<device_id>.cfg byte for byte.

TODO 06 is checked three ways: (1) a clean run must report both checks
passing for every device, (2) the grader temporarily corrupts one device's
golden reference and confirms only that device's own task fails while
every other device is unaffected, then restores it, and (3) the grader
injects the same disabled-VLAN marker into a staging device's golden file
AND its own already-rendered output (identical bytes, so the golden
compare alone would trivially pass) and re-runs starting at the
verification tasks only, confirming the independent policy re-check still
catches it on its own.

TODO 07 is checked three ways: (1) a first run must report exactly one
changed task per device (TODO 05's fresh render), (2) a second run right
after must report exactly zero changed tasks per device - proof TODO 07's
own re-render genuinely found nothing left to do, and (3) the grader
deliberately corrupts one device's already-rendered output and re-runs
starting at TODO 07's own re-render task for just that device, confirming
Ansible's own changed counter flips to true and the assert task genuinely
fails - proof the assert is really checking republish_result.changed and
not just a no-op that always succeeds.

TODO 08 is checked two ways. First, a clean run: starts the mock RESTCONF
device fleet, clears output/*.cfg, runs the real playbook, and then -
independently of whatever the playbook itself reported - sends a GET to
every device's own RESTCONF endpoint and confirms the config it actually
stored matches the exact file TODO 05 rendered (staging devices) or that
nothing was stored at all (production devices). Second, fault injection:
writes a fault-injection file the mock fleet reads at startup
(mock_fault_injection.json - see mock_device_server.py), making one
staging device fail its first 2 PATCH attempts with a transient 503 and
the other always fail with a permanent 422, then running the playbook and
checking two independent things per device: whether it ended up correctly
pushed (or correctly not pushed), and - straight from the fleet's own
attempt counter (mock_attempt_counts.json) - exactly how many times it
was actually hit. The transient device must show exactly 3 attempts (2
failures + 1 success); the permanent device must show exactly 1 (never
retried). Both fault files are always removed afterward, and a final
clean run re-confirms both staging devices push correctly with no faults
injected. This grader supplies its own fixed test credentials for the
mock fleet (see GRADING_CREDENTIALS below), so a push is graded the same
way whether or not you've created your own .env yet.

TODO 09 is checked by making one staging device "lie" - it accepts every
PATCH with a completely normal 204 but never actually stores it (see
mock_device_server.py's do_PATCH). Unlike every other TODO's check, this
one reads the real playbook's own stdout directly rather than sending an
independent GET itself - the whole point of TODO 09 is that the pipeline
has to catch this on its own, not that this grader catches it from
outside afterward. The lying device's own verification task must fail;
the other (truthful) staging device must still report success normally.
The fault file is always removed afterward, and a final clean run
(reusing check_todo_8) confirms both staging devices push and verify
correctly with nothing faked.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.rule import Rule
from rich.syntax import Syntax
from rich.bar import Bar

ROOT = Path(__file__).parent
INTENT_FILE = ROOT / "intent" / "retail_branch_service.yml"
SITE_FILE = ROOT / "site.yml"
INVENTORY_FILE = ROOT / "inventory" / "devices.py"
STAGING_FILE = ROOT / "group_vars" / "staging.yml"
OUTPUT_DIR = ROOT / "output"
GOLDEN_DIR = ROOT / "golden"
MOCK_SERVER_FILE = ROOT / "mock_device_server.py"
MOCK_STATE_FILE = ROOT / "mock_device_state.json"
FAULT_FILE = ROOT / "mock_fault_injection.json"
ATTEMPT_FILE = ROOT / "mock_attempt_counts.json"

# Fixed test credentials this grader uses for every run, regardless of
# whether you've created your own .env yet - overrides any real .env for
# the lifetime of this process only (never written back to disk), so
# TODO 08 is graded the same way every time, for everyone.
GRADING_CREDENTIALS = {
    "RESTCONF_PROD_USERNAME": "grading-user",
    "RESTCONF_PROD_PASSWORD": "grading-pass",
    "RESTCONF_STAGING_USERNAME": "grading-user",
    "RESTCONF_STAGING_PASSWORD": "grading-pass",
}
os.environ.update(GRADING_CREDENTIALS)

console = Console(markup=False, highlight=False)

BOLD = "bold "
DIM = "dim"
RED = "red"
GREEN = "green"
YELLOW = "yellow"
CYAN = "cyan"

# Set to False, or run with CAPSTONE_INTERACTIVE=0, to disable ENTER pauses.
INTERACTIVE_MODE = os.environ.get("CAPSTONE_INTERACTIVE", "1") != "0"

TOTAL_TODOS = 9

TODO_NAMES = {
    1: "Author the Declarative Service Intent",
    2: "Load the Declarative Service Intent",
    3: "Run Pre-Flight Validation",
    4: "Build Environment- and Site-Aware Render Facts",
    5: "Render Multi-Platform Artifacts",
    6: "Run Post-Render Correctness Verification",
    7: "Publish Idempotently",
    8: "Build, Push, and Retry RESTCONF Configuration",
    9: "Verify Device State via RESTCONF",
}

SUCCESS_MESSAGES = {
    1: "intent/retail_branch_service.yml captures the business requirements correctly.",
    2: "service_intent was loaded correctly and is visible, correctly resolved, on every one of the 9 devices.",
    3: "Pre-flight validation is running and correctly catches a bad cross-file reference.",
    4: "render_context was assembled correctly for every one of the 9 devices.",
    5: "Every device's rendered artifact matches its golden reference config exactly.",
    6: "Post-render verification is running and independently catches both a corrupted golden reference and a leaked disabled VLAN.",
    7: "Publishing is proven idempotent - a second run of the whole pipeline makes zero changes on any device.",
    8: "Staging was pushed correctly and production was correctly held back for approval, and transient RESTCONF failures are retried until they succeed while permanent failures stop immediately without wasting a single retry.",
    9: "Live device state is independently verified after every push - a device that lies about applying a change is caught, not trusted.",
}

FAIL_MESSAGES = {
    1: "The pipeline cannot continue because the declarative service intent has not been authored correctly yet.",
    2: "The pipeline cannot continue because the declarative service intent has not been loaded yet.",
    3: "The pipeline cannot continue because pre-flight validation is not actually being executed.",
    4: "The pipeline cannot continue because render_context has not been built yet.",
    5: "The pipeline cannot continue because no device configuration has been rendered yet.",
    6: "The pipeline cannot continue because post-render verification is not actually being executed, or does not independently catch a leaked disabled VLAN.",
    7: "The pipeline cannot continue because publishing has not been proven idempotent - a second run should make zero changes, on every device.",
    8: "The pipeline cannot continue because staging devices have not been pushed to correctly, production devices are not being held for approval, or a transient failure isn't being retried the right number of times.",
    9: "The pipeline cannot continue because a device's live state after a push is not being independently re-verified via a real GET.",
}

HINTS = {
    1: "Create intent/retail_branch_service.yml by hand. Match the shape in TASK.md (tenant, service, vlans: [{role, name, enabled}]) using the business requirements table exactly - YAML, not JSON.",
    2: "Use the include_vars module. Point its file: option at intent/retail_branch_service.yml (playbook_dir is the directory site.yml lives in), and set name: service_intent so the whole file lands under one variable instead of three separate loose variables.",
    3: "First build a plain list of every valid role with a set_fact (service_intent.vlans | map(attribute='role') | list). Then write one assert task, looped with loop: \"{{ disabled_roles }}\", whose that: condition is simply `item in valid_roles` - true when the current disabled role is one of the real ones. Add register: preflight_result on this assert task too - the guard task right after STUDENT WORK AREA - TODO 03 checks for it to confirm this task actually ran at all.",
    4: "Use set_fact to build a dict named render_context with exactly these keys: site_id, environment_name, tenant (from service_intent.tenant), service (from service_intent.service), hostname, platform, and vlans (= resolved_vlans). Every value on the right already exists as a variable - this task only combines them.",
    5: "Use the template module with src: chosen by render_context.platform (cat8k -> cat8k_ospf.j2, nexus9k -> nexus_vlan.j2) and dest: output/<device_id>.cfg. The templates expect plain hostname and vlans variables, not render_context.hostname/render_context.vlans - use this task's own vars: to expose them under those exact names.",
    6: "Write two assert tasks. First: lookup('file', ...output.../<device_id>.cfg) equals lookup('file', ...golden.../<device_id>.cfg). Second: loop over disabled_vlan_markers (already computed for you in inventory/devices.py) and assert item not in <that same rendered text> for each one - the Jinja 'in' test does substring containment when the right side is a string, so this finds any disabled VLAN marker that leaked into the rendered text, independently of golden - register: policy_check_result on this second task only (if it runs at all, the first one already passed).",
    7: "Copy TODO 05's template task exactly (same src, dest, vars), register: it under a descriptive name (e.g. republish_result - TODO 05's own task doesn't register anything at all, so there's nothing to collide with), then assert not republish_result.changed. ansible.builtin.template already checksums content before writing, so a correct re-render of identical content reports changed: false with no extra code from you.",
    8: "Use the uri module, gated with when: auto_deploy. PATCH to \"http://{{ ansible_host }}:{{ restconf_port }}{{ restconf_path }}\", body_format: json, body: {config: <rendered file via lookup('file', ...)>}. Auth via url_username/url_password from lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME'/'_PASSWORD'), force_basic_auth: true. Widen status_code: to cover every status you want to inspect, not just success. Add failed_when: false as a task-level keyword (sibling of register:, not a module param), register: push_result, then retry with until: push_result.status | default(0) in [...], retries: 3, delay: 2 - default(0) matters because a connection that fails outright leaves push_result with no .status key at all.",
    9: "Use the uri module with method: GET on the same URL the push just used, return_content: true, register: verify_result - gated behind when: auto_deploy and (push_result.status | default(0)) in [200, 204] (only devices that were actually pushed to have anything to verify). Then assert verify_result.json.config == lookup('file', ...output.../<device_id>.cfg) - the same lookup the push task itself used, so both sides go through the same one-trailing-newline stripping.",
}

SOLUTIONS = {
    1: '''tenant: "Meridian Retail"
service: "branch-network-standard"
vlans:
  - role: users
    name: RTL-USERS
    enabled: true
  - role: voice
    name: RTL-VOICE
    enabled: true
  - role: wifi
    name: RTL-WIFI
    enabled: true
  - role: guest
    name: RTL-GUEST
    enabled: true
  - role: unused
    name: UNUSED
    enabled: false''',
    2: '''- name: load the declarative service intent
  ansible.builtin.include_vars:
    file: "{{ playbook_dir }}/intent/retail_branch_service.yml"
    name: service_intent''',
    3: '''- name: build the list of valid network names
  ansible.builtin.set_fact:
    valid_roles: "{{ service_intent.vlans | map(attribute='role') | list }}"

- name: pre-flight validation
  ansible.builtin.assert:
    that:
      - item in valid_roles
    fail_msg: "{{ item }} is not a real network."
    success_msg: "{{ item }} is a real network - OK to disable."
  loop: "{{ disabled_roles }}"
  register: preflight_result''',
    4: '''- name: build render context
  ansible.builtin.set_fact:
    render_context:
      site_id: "{{ site_id }}"
      environment_name: "{{ environment_name }}"
      tenant: "{{ service_intent.tenant }}"
      service: "{{ service_intent.service }}"
      hostname: "{{ hostname }}"
      platform: "{{ platform }}"
      vlans: "{{ resolved_vlans }}"''',
    5: '''- name: render the platform-specific configuration
  ansible.builtin.template:
    src: "{{ platform_templates[render_context.platform] }}"
    dest: "{{ playbook_dir }}/output/{{ device_id }}.cfg"
  vars:
    platform_templates:
      cat8k: cat8k_ospf.j2
      nexus9k: nexus_vlan.j2
    hostname: "{{ render_context.hostname }}"
    vlans: "{{ render_context.vlans }}"''',
    6: '''- name: verify rendered artifact against golden reference
  ansible.builtin.assert:
    that:
      - lookup('file', playbook_dir + '/output/' + device_id + '.cfg')
        == lookup('file', playbook_dir + '/golden/' + site_id + '/' + device_id + '.cfg')
    fail_msg: "Rendered artifact for {{ device_id }} does not match golden/{{ site_id }}/{{ device_id }}.cfg."

- name: independently verify no disabled vlan leaked into the rendered output
  ansible.builtin.assert:
    that:
      - item not in lookup('file', playbook_dir + '/output/' + device_id + '.cfg')
    fail_msg: "{{ item }} was found in output/{{ device_id }}.cfg but should have been disabled."
    success_msg: "{{ item }} is correctly absent from output/{{ device_id }}.cfg."
  loop: "{{ disabled_vlan_markers }}"
  register: policy_check_result''',
    7: '''- name: re-render the platform-specific configuration to confirm publishing is idempotent
  ansible.builtin.template:
    src: "{{ platform_templates[render_context.platform] }}"
    dest: "{{ playbook_dir }}/output/{{ device_id }}.cfg"
  vars:
    platform_templates:
      cat8k: cat8k_ospf.j2
      nexus9k: nexus_vlan.j2
    hostname: "{{ render_context.hostname }}"
    vlans: "{{ render_context.vlans }}"
  register: republish_result

- name: assert this device's config was not rewritten
  ansible.builtin.assert:
    that:
      - not republish_result.changed
    fail_msg: "{{ device_id }}'s config was rewritten even though nothing about it changed - publishing is not idempotent."
    success_msg: "{{ device_id }}'s config was already correct on disk - nothing was rewritten."''',
    8: '''- name: push rendered configuration via RESTCONF, retrying transient failures
  when: auto_deploy
  ansible.builtin.uri:
    url: "http://{{ ansible_host }}:{{ restconf_port }}{{ restconf_path }}"
    method: PATCH
    body_format: json
    body:
      config: "{{ lookup('file', playbook_dir + '/output/' + device_id + '.cfg') }}"
    url_username: "{{ lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME') }}"
    url_password: "{{ lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_PASSWORD') }}"
    force_basic_auth: true
    status_code: [200, 204, 401, 403, 422, 500, 502, 503, 504]
  register: push_result
  failed_when: false
  until: push_result.status | default(0) in [200, 204, 401, 403, 422]
  retries: 3
  delay: 2''',
    9: '''- name: verify device state via RESTCONF
  when: auto_deploy and (push_result.status | default(0)) in [200, 204]
  ansible.builtin.uri:
    url: "http://{{ ansible_host }}:{{ restconf_port }}{{ restconf_path }}"
    method: GET
    url_username: "{{ lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME') }}"
    url_password: "{{ lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_PASSWORD') }}"
    force_basic_auth: true
    return_content: true
  register: verify_result

- name: assert the device's live state matches what was pushed
  when: auto_deploy and (push_result.status | default(0)) in [200, 204]
  ansible.builtin.assert:
    that:
      - verify_result.json.config == lookup('file', playbook_dir + '/output/' + device_id + '.cfg')
    fail_msg: "{{ device_id }}'s live device state does not match what was pushed - the push reported success, but the device never actually applied it."
    success_msg: "{{ device_id }}'s live device state matches what was pushed."''',
}

EXPECTED = {
    1: "intent/retail_branch_service.yml should exist with tenant: \"Meridian Retail\", service: \"branch-network-standard\", and exactly the 5 VLAN definitions specified in TASK.md.",
    2: "Running the playbook should succeed for all 9 devices, and the debug task's output should show the correct service, tenant, environment, device identity, and resolved_vlans for every one of them.",
    3: "A validation failure injected into group_vars/staging.yml (an unknown disabled role) should fail the 2 staging devices and leave the 7 prod devices unaffected. After restoring the file, all 9 devices should pass.",
    4: "render_context.hostname and render_context.vlans should exactly match this device's own hostname and resolved_vlans for all 9 devices.",
    5: "output/<device_id>.cfg should exist and match golden/<site_id>/<device_id>.cfg exactly for all 9 devices - the right template for each device's platform, with the right hostname and vlans substituted in.",
    6: "Every device should report both checks passing on a clean run. Corrupting one device's golden reference should fail only that device. Injecting a disabled VLAN marker into a staging device's golden file AND its own rendered output (identical bytes) should still fail that device, proving the second check works independently of the first.",
    7: "Running the playbook from a clean output/ should report exactly one changed task per device (the first render). Running it again immediately after, with nothing else changed, should report exactly zero changed tasks per device - proof the whole pipeline, TODO 07's re-render included, is a genuine no-op.",
    8: "A GET to each device's own RESTCONF endpoint should show the 2 staging devices holding the exact content of their own output/<device_id>.cfg, and the 7 production devices holding nothing at all. Under fault injection: a device hit with a transient 503 should end up pushed after exactly 3 attempts (2 failures + 1 success); a device hit with a permanent 422 should never be pushed and should show exactly 1 attempt.",
    9: "A staging device made to silently ignore every push (while still returning HTTP 204) should have its own verification task fail, naming the mismatch. The other staging device, told the truth, should still report success. With no lie injected, both staging devices should push and verify correctly.",
}

PROBLEMS = {
    1: "The declarative service intent file is missing, malformed, or does not match the required business requirements.",
    2: "service_intent is not being loaded (or not loaded correctly) from intent/retail_branch_service.yml.",
    3: "Pre-flight validation did not catch an intentionally broken cross-file reference, or broke devices it shouldn't have.",
    4: "render_context is missing, or one of its fields doesn't match this device's own already-known values.",
    5: "No config was rendered for one or more devices, the wrong template was used for a device's platform, or the rendered content doesn't match golden.",
    6: "Post-render verification is missing, doesn't run for every device, or the disabled-VLAN check trusts golden/output content instead of independently re-deriving from disabled_vlan_markers.",
    7: "The idempotent re-render task is missing, points at the wrong file, or the assert doesn't actually check republish_result.changed - so a second run of the pipeline still shows changes.",
    8: "A staging device wasn't pushed correctly, a production device got pushed when it should have been held for approval, or a transient/permanent failure wasn't retried the right number of times.",
    9: "The verification task is missing, doesn't actually run a fresh GET, or the assert trusts push_result instead of independently comparing verify_result.json.config against the rendered file.",
}

STAGING_DEVICES = {"sea03-cat8k-01", "sea03-n9k-01"}
PROD_DEVICES = {
    "aus02-cat8k-01", "aus02-n9k-01", "aus02-n9k-02",
    "rdu01-cat8k-01", "rdu01-cat8k-02", "rdu01-n9k-01", "rdu01-n9k-02",
}


# -----------------------------------------------------------------------------
# Presentation helpers (Rich)
# -----------------------------------------------------------------------------

def c(text, style):
    return Text(str(text), style=style.strip())


def todo_label(number):
    """Zero-padded to match this course's folder naming (TODO-01,
    TODO-02, ...) instead of the unpadded "TODO 1" the Python course's
    grader used."""
    return f"TODO {number:02d}"


def banner(title, color=CYAN):
    console.print()
    console.print(
        Panel(
            Align.center(Text(str(title), style=f"bold {color}")),
            border_style=color,
            padding=(0, 2),
        )
    )
    console.print()


def divider():
    console.print()
    console.print(Rule(style="grey50"))
    console.print()


def pause(message):
    if INTERACTIVE_MODE:
        try:
            input(f"\n{message}")
        except EOFError:
            pass


def section(title, value, color):
    body = Text()
    lines = str(value).splitlines()
    for i, line in enumerate(lines):
        body.append(line)
        if i < len(lines) - 1:
            body.append("\n")
    console.print(Panel(body, title=title, title_align="left", border_style=color, padding=(0, 1)))
    console.print()


def render_bar(completed, total):
    total = max(total, 1)
    return Bar(size=total, begin=0, end=completed, color="green3", bgcolor="grey27", width=40)


# -----------------------------------------------------------------------------
# TODO checks
# -----------------------------------------------------------------------------

def check_todo_1():
    if not INTENT_FILE.exists():
        return False
    try:
        data = yaml.safe_load(INTENT_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("tenant") != "Meridian Retail":
        return False
    if data.get("service") != "branch-network-standard":
        return False
    vlans = data.get("vlans")
    if not isinstance(vlans, list):
        return False
    expected = {
        "users": ("RTL-USERS", True),
        "voice": ("RTL-VOICE", True),
        "wifi": ("RTL-WIFI", True),
        "guest": ("RTL-GUEST", True),
        "unused": ("UNUSED", False),
    }
    actual = {}
    for vlan in vlans:
        if not isinstance(vlan, dict):
            return False
        actual[vlan.get("role")] = (vlan.get("name"), vlan.get("enabled"))
    for role, expected_values in expected.items():
        if actual.get(role) != expected_values:
            return False
    return True


def load_expected_devices():
    result = subprocess.run(
        [sys.executable, str(INVENTORY_FILE), "--list"],
        cwd=ROOT, text=True, capture_output=True,
    )
    inventory = json.loads(result.stdout)
    devices = {}
    for host, hostvars in inventory["_meta"]["hostvars"].items():
        devices[host] = {
            "environment_name": hostvars["environment_name"],
            "platform": hostvars["platform"],
            "site_id": hostvars["site_id"],
            "hostname": hostvars["hostname"],
            "vlan_ids": [vlan["id"] for vlan in hostvars["resolved_vlans"]],
            "disabled_vlan_markers": hostvars.get("disabled_vlan_markers", []),
            "ansible_host": hostvars["ansible_host"],
            "restconf_port": hostvars["restconf_port"],
            "restconf_path": hostvars["restconf_path"],
        }
    return devices


def run_playbook(extra_args=None):
    """extra_args, if given, is a list of additional ansible-playbook CLI
    arguments (e.g. ["--limit", host, "--start-at-task", task_name]) -
    used by check_todo_6 to re-run only one device, and to resume partway
    through the play without re-rendering over an intentionally corrupted
    file."""
    command = ["ansible-playbook", "-i", str(INVENTORY_FILE), str(SITE_FILE)]
    if extra_args:
        command += list(extra_args)
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def kill_stray_mock_servers():
    """A mock_device_server.py left running from a manual test (e.g. via
    run_playbook.sh) would otherwise still be the one actually bound to
    every device's port, using whatever credentials *it* loaded from
    .env - while this grader's own playbook run authenticates with
    GRADING_CREDENTIALS instead. The result is a confusing 401 that looks
    exactly like a wrong solution, even though the real problem is two
    mock fleets fighting over the same addresses. Always clear the field
    first, every run."""
    subprocess.run(
        ["pkill", "-f", "mock_device_server.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)


def start_mock_fleet():
    """Start mock_device_server.py as its own subprocess, the same way you
    would yourself. Deletes any leftover mock_device_state.json first, so
    TODO 08 is always graded against a clean device fleet with no drift
    carried over from a previous manual run.

    Returns (process, None) on a normal start, or (None, crash_output) if
    the server process already exited during the startup wait. The most
    common cause by far is macOS: every device IP other than 127.0.0.1
    needs a one-time loopback alias before mock_device_server.py can even
    bind to it (see setup_local_loopback.sh) - without that, every device
    server fails with "Can't assign requested address" and the whole
    process exits immediately, which would otherwise show up here only as
    a wall of confusing HTTP connection timeouts with no obvious cause."""
    kill_stray_mock_servers()
    if MOCK_STATE_FILE.exists():
        MOCK_STATE_FILE.unlink()
    process = subprocess.Popen(
        [sys.executable, str(MOCK_SERVER_FILE)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(1.5)  # every device server binds synchronously at startup
    if process.poll() is not None:
        return None, process.stdout.read()
    return process, None


def stop_mock_fleet(process):
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def print_mock_fleet_error(crash_output):
    banner("mock device fleet failed to start", YELLOW)
    console.print(c(
        "mock_device_server.py exited immediately instead of starting up - "
        "TODO 08 (and anything after it) needs it running to do anything at "
        "all.",
        YELLOW,
    ))
    console.print()
    if "Can't assign requested address" in (crash_output or ""):
        console.print(c(
            "This is the known macOS setup step: every device IP other than "
            "127.0.0.1 needs a one-time loopback alias before this can bind. "
            "Run this once (needs sudo, and again after every reboot), then "
            "run python grading.py again:",
            YELLOW,
        ))
        console.print()
        console.print(c("  sudo ./setup_local_loopback.sh", f"{BOLD}{CYAN}"))
        console.print()
    else:
        # An unrecognized failure - show the raw traceback since there's no
        # specific fix to point at instead.
        section("mock_device_server.py's own output", (crash_output or "").strip(), RED)


def get_device_config(device_id, expected):
    """GETs one device's own RESTCONF endpoint and returns (config, None)
    on success, or (None, error_message) if anything went wrong."""
    env_prefix = f"RESTCONF_{expected['environment_name'].upper()}"
    username = os.environ.get(f"{env_prefix}_USERNAME", "")
    password = os.environ.get(f"{env_prefix}_PASSWORD", "")
    url = f"http://{expected['ansible_host']}:{expected['restconf_port']}{expected['restconf_path']}"

    try:
        response = requests.get(url, auth=(username, password), timeout=5)
    except requests.RequestException as exc:
        return None, f"GET {url} failed ({type(exc).__name__}) - is the mock device fleet running?"
    if response.status_code != 200:
        snippet = response.text[:200].replace("\n", " ")
        return None, f"GET {url} returned HTTP {response.status_code} (expected 200): {snippet!r}"
    try:
        body = response.json()
    except ValueError:
        return None, f"GET {url} returned a non-JSON body: {response.text[:200]!r}"
    return body.get("config"), None


def check_push_clean_state():
    """Never trusts the playbook's own exit code or stdout for this one -
    sends an independent GET straight to each device's own RESTCONF
    endpoint, with the same credentials, and checks two different things
    depending on the device:

    - Staging devices (auto_deploy: true) SHOULD have been pushed - their
      stored config must match the exact file TODO 05 rendered.
    - Production devices (auto_deploy: false) must NOT have been pushed
      yet at all - a production device holding any config here means the
      approval gate (when: auto_deploy) is missing or wrong, which is
      exactly as much a failure as a staging device never getting pushed.

    Returns (ok, diagnostics) instead of a plain bool - a live network call
    has too many distinct ways to fail (connection refused, timeout, wrong
    credentials, wrong path, wrong body, or - the one unique to this TODO -
    a production device that got pushed to when it never should have)
    for a bare True/False to be debuggable. Shared by check_todo_8 for
    both its initial clean-run check and its final re-verification after
    fault injection."""
    expected_devices = load_expected_devices()
    diagnostics = {}

    for device_id, expected in expected_devices.items():
        config, error = get_device_config(device_id, expected)
        if error:
            diagnostics[device_id] = error
            continue

        if device_id in STAGING_DEVICES:
            output_file = OUTPUT_DIR / f"{device_id}.cfg"
            if not output_file.exists():
                diagnostics[device_id] = f"output/{device_id}.cfg does not exist - nothing was rendered for this device this run."
                continue
            expected_config = output_file.read_text(encoding="utf-8")
            # lookup('file', ...) - the documented, intended way to read
            # the rendered artifact into this task's body - strips
            # exactly one trailing newline (a well-known Ansible lookup
            # behavior). A correct push therefore legitimately arrives
            # one newline shorter than the raw file on disk; comparing
            # both sides with trailing newlines stripped is what makes
            # this check pass a correct solution rather than the file's
            # exact byte count.
            if (config or "").rstrip("\n") != expected_config.rstrip("\n"):
                if not config:
                    diagnostics[device_id] = "should have been pushed, but holds no config at all - nothing was ever pushed."
                else:
                    diagnostics[device_id] = f"was pushed, but its stored config does not match output/{device_id}.cfg."
        else:
            if config not in (None, ""):
                diagnostics[device_id] = "must not be pushed without approval, but already holds a config - when: auto_deploy is missing or wrong."

    return (len(diagnostics) == 0), diagnostics


def check_todo_8():
    """Two-part proof this TODO is genuinely both a push AND a retry
    mechanism, not just one or the other:

    1. Clean run, no faults injected: every device must be in the right
       final state - see check_push_clean_state (an independent GET,
       never anything printed to the terminal).

    2. Fault injection: writes mock_fault_injection.json before running
       the playbook again, making one staging device (the transient
       device) fail its first 2 PATCH attempts with a transient 503, and
       the other (the permanent device) always fail with a permanent 422
       - see mock_device_server.py's own record_patch_attempt() for
       exactly how it decides this per attempt. Checks two independent
       things per device, neither of which trusts the playbook's own exit
       code: did it end up in the right final state, and how many times
       was it actually hit (mock_attempt_counts.json, the fleet's own
       counter - not something either side can fake by getting lucky on
       the final GET alone). Exactly 3 for the transient device (2
       failures + 1 success); exactly 1 for the permanent one.

    Both fault files are always removed afterward (see the finally
    block), whether or not the checks above passed, and a final clean run
    with no faults injected re-verifies both staging devices push
    correctly - so a student re-running this TODO by hand afterward
    starts from a known-good, fault-free fleet.

    mock_attempt_counts.json is cumulative for the mock fleet's whole
    lifetime, not reset per phase - the clean run above already pushed
    both staging devices once each before any fault exists. Comparing
    raw counts after the fault-injection run would silently count that
    earlier, fault-free push as if it were part of the retry sequence
    (undercounting a broken retry, and overcounting a permanent failure
    that should only ever be hit once). Only the DELTA since the
    baseline captured right after the clean run isolates what actually
    happened during the fault-injection run itself."""
    clear_rendered_output()
    run_playbook()
    clean_ok, clean_diagnostics = check_push_clean_state()
    if not clean_ok:
        return False, clean_diagnostics

    baseline_attempts = {}
    if ATTEMPT_FILE.exists():
        baseline_attempts = json.loads(ATTEMPT_FILE.read_text(encoding="utf-8"))

    expected_devices = load_expected_devices()
    transient_device = "sea03-cat8k-01"
    permanent_device = "sea03-n9k-01"
    diagnostics = {}

    fault_config = {
        transient_device: {"fail_count": 2, "fail_status": 503},
        permanent_device: {"fail_count": 999, "fail_status": 422},
    }

    try:
        FAULT_FILE.write_text(json.dumps(fault_config), encoding="utf-8")
        clear_rendered_output()
        run_playbook()

        attempt_counts = {}
        if ATTEMPT_FILE.exists():
            attempt_counts = json.loads(ATTEMPT_FILE.read_text(encoding="utf-8"))

        transient_attempts = attempt_counts.get(transient_device, 0) - baseline_attempts.get(transient_device, 0)
        permanent_attempts = attempt_counts.get(permanent_device, 0) - baseline_attempts.get(permanent_device, 0)

        config, error = get_device_config(transient_device, expected_devices[transient_device])
        if error:
            diagnostics[transient_device] = error
        else:
            expected_config = (OUTPUT_DIR / f"{transient_device}.cfg").read_text(encoding="utf-8")
            if (config or "").rstrip("\n") != expected_config.rstrip("\n"):
                diagnostics[transient_device] = f"should have succeeded after retrying a transient 503, but its stored config does not match output/{transient_device}.cfg."
            elif transient_attempts != 3:
                diagnostics[transient_device] = f"was hit {transient_attempts} time(s) during the retry test - expected exactly 3 (2 retried failures + 1 success)."

        config, error = get_device_config(permanent_device, expected_devices[permanent_device])
        if error:
            diagnostics[permanent_device] = error
        else:
            if config not in (None, ""):
                diagnostics[permanent_device] = "should never have been pushed (a permanent 422 error), but already holds a config."
            elif permanent_attempts != 1:
                diagnostics[permanent_device] = f"was hit {permanent_attempts} time(s) during the retry test - expected exactly 1 (a permanent error should never be retried)."
    finally:
        if FAULT_FILE.exists():
            FAULT_FILE.unlink()
        if ATTEMPT_FILE.exists():
            ATTEMPT_FILE.unlink()

    if diagnostics:
        return False, diagnostics

    # No faults injected this time - both staging devices, and every
    # production device, must still behave exactly like a normal clean run.
    clear_rendered_output()
    run_playbook()
    return check_push_clean_state()


VERIFY_TASK_NAME = "assert the device's live state matches what was pushed"


def check_todo_9():
    """Injects a "lying" fault into one staging device (see
    mock_device_server.py's do_PATCH) - it accepts every PATCH with a
    completely normal 204, but never actually stores the new config.

    Unlike every other RESTCONF-related check in this course, this one
    never sends its own GET at all - it reads the real playbook's own
    stdout/stderr directly to confirm the *pipeline itself* caught the
    lie. That's the actual point of TODO 09: verification has to be a
    task inside the playbook, not something only this grader checks
    from outside afterward.

    Content-based, same reasoning as the TODO 06/07 fixes - never
    trust the student's own fail_msg/success_msg text (TASK.md leaves
    that wording entirely up to them). Instead this uses task_block/
    task_passed_for_host/task_failed_for_host, scoped to the fixed
    task name VERIFY_TASK_NAME, to determine per-host pass/fail
    independent of any wording: the lying device's own assert task
    must fail; the truthful staging device's must pass.

    Always removes the fault file afterward, then runs one final clean
    pass with nothing faked and reuses check_todo_8's own external
    GET-based verification to confirm both staging devices still push
    and verify correctly."""
    truthful_device = "sea03-cat8k-01"
    lying_device = "sea03-n9k-01"
    diagnostics = {}

    fault_config = {lying_device: {"lie": True}}

    try:
        FAULT_FILE.write_text(json.dumps(fault_config), encoding="utf-8")
        clear_rendered_output()
        result = run_playbook()
        text = result.stdout + "\n" + result.stderr

        if not task_passed_for_host(text, VERIFY_TASK_NAME, truthful_device):
            diagnostics[truthful_device] = "device state could not be verified."

        if not task_failed_for_host(text, VERIFY_TASK_NAME, lying_device):
            diagnostics[lying_device] = "device state could not be verified."
    finally:
        if FAULT_FILE.exists():
            FAULT_FILE.unlink()

    if diagnostics:
        return False, diagnostics

    # No lie injected this time - both staging devices, and every
    # production device, must still behave exactly like TODO 08.
    clear_rendered_output()
    run_playbook()
    return check_todo_8()


def check_todo_2(result):
    """Content-based on purpose: never rely on the overall PLAY RECAP
    failed/unreachable counts here. Once a later TODO (4, 5, ...) exists
    in the same site.yml and is still blank, its own task fails and the
    whole run's recap shows failed=1 for every host - even though TODO
    2's own task, earlier in the play, already succeeded and already
    printed its lines. The presence of those lines is the real signal;
    anything that happens in a later, not-yet-graded task is irrelevant
    to whether TODO 2 itself is done."""
    if result is None:
        return False

    text = result.stdout + "\n" + result.stderr
    expected_devices = load_expected_devices()

    for device_id, expected in expected_devices.items():
        required_lines = [
            '"Loaded service: branch-network-standard"',
            '"Loaded tenant: Meridian Retail"',
            f'"Loaded environment: {expected["environment_name"]}"',
            f'"Loaded device: {device_id} ({expected["platform"]}, {expected["site_id"]})"',
            f'"Loaded resolved_vlans: {expected["vlan_ids"]}"',
        ]
        for line in required_lines:
            if line not in text:
                return False

    return True


def check_todo_3():
    """Only called once TODO 01 and TODO 02 are already confirmed correct -
    see compute_statuses(). Temporarily breaks group_vars/staging.yml,
    always restores it in a finally block even if something raises.

    Content-based, same reasoning as check_todo_2: a later TODO being
    blank makes the whole run's PLAY RECAP show failures for every host,
    so pass/fail here can't rely on recap counts. It also can't rely on
    the assert's own fail_msg/success_msg text, since the new solution
    loops per disabled role and a production device with an empty
    disabled_roles list never prints any per-item message at all.
    Instead this checks for the shared "report what was loaded for this
    device" debug task's own "Loaded device: <host> (...)" line - that
    task is sequenced right after the pre-flight validation assert, so
    it only ever prints for a host whose validation actually passed,
    regardless of how many roles that host happens to be disabling."""
    if not STAGING_FILE.exists():
        return False

    original = STAGING_FILE.read_text(encoding="utf-8")
    try:
        broken = original.replace("- guest", "- guest\n  - gust", 1)
        if broken == original:
            return False
        STAGING_FILE.write_text(broken, encoding="utf-8")

        broken_result = run_playbook()
        broken_text = broken_result.stdout + broken_result.stderr

        staging_correctly_failed = all(
            f'"Loaded device: {host} (' not in broken_text for host in STAGING_DEVICES
        )
        prod_unaffected = all(
            f'"Loaded device: {host} (' in broken_text for host in PROD_DEVICES
        )
    finally:
        STAGING_FILE.write_text(original, encoding="utf-8")

    if not (staging_correctly_failed and prod_unaffected):
        return False

    clean_result = run_playbook()
    clean_text = clean_result.stdout + clean_result.stderr

    return all(
        f'"Loaded device: {host} (' in clean_text
        for host in (STAGING_DEVICES | PROD_DEVICES)
    )


def check_todo_4(result):
    """Content-based, same reasoning as check_todo_2/3 - stays correct
    even after a future TODO 5 is appended below this one and is still
    blank in a later folder."""
    if result is None:
        return False

    text = result.stdout + "\n" + result.stderr
    expected_devices = load_expected_devices()

    for device_id, expected in expected_devices.items():
        required_lines = [
            f'"Render context hostname: {expected["hostname"]}"',
            f'"Render context vlans: {expected["vlan_ids"]}"',
        ]
        for line in required_lines:
            if line not in text:
                return False

    return True


def clear_rendered_output():
    """Delete any output/*.cfg left over from a previous run before
    re-checking TODO 5. Without this, a stale file from an earlier
    successful run could make a since-blanked STUDENT WORK AREA look
    complete, since a blank task simply renders nothing rather than
    producing a wrong file."""
    for cfg_file in OUTPUT_DIR.glob("*.cfg"):
        cfg_file.unlink()


def check_todo_5():
    """File-based, not text-based: compares the actual rendered artifact
    in output/<device_id>.cfg against golden/<site_id>/<device_id>.cfg
    byte for byte, for every device. Never reads playbook stdout at all,
    so it stays correct even once a future TODO 6 appends more tasks
    (and more debug output) below this one."""
    expected_devices = load_expected_devices()

    for device_id, expected in expected_devices.items():
        output_file = OUTPUT_DIR / f"{device_id}.cfg"
        golden_file = GOLDEN_DIR / expected["site_id"] / f"{device_id}.cfg"
        if not output_file.exists() or not golden_file.exists():
            return False
        if output_file.read_text(encoding="utf-8") != golden_file.read_text(encoding="utf-8"):
            return False

    return True


def task_block(text, task_name):
    """Every output line belonging to one named task's own run, up to
    (but not including) the next TASK banner - so a completely
    different, possibly still-blank, later task's failure can never be
    mistaken for this task's own result."""
    lines = text.splitlines()
    banner = f"TASK [{task_name}]"
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(banner):
            start = i + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].strip().startswith("TASK ["):
            end = i
            break
    return "\n".join(lines[start:end])


def task_failed_for_host(text, task_name, host):
    """True if this exact task's own output shows host actually failing
    it (a fatal:/failed: line for that host) - independent of whatever
    fail_msg text the task itself happens to be written with."""
    block = task_block(text, task_name)
    return any(
        line.strip().startswith(f"fatal: [{host}]") or line.strip().startswith(f"failed: [{host}]")
        for line in block.splitlines()
    )


def task_passed_for_host(text, task_name, host):
    """True if this exact task's own output shows host completing it
    without failing: ok:/changed: (ran and passed), or skipping: (a
    looped task with nothing to check for this host - not a failure)."""
    block = task_block(text, task_name)
    return any(
        line.strip().startswith(f"ok: [{host}]")
        or line.strip().startswith(f"changed: [{host}]")
        or line.strip().startswith(f"skipping: [{host}]")
        for line in block.splitlines()
    )


def task_changed_for_host(text, task_name, host):
    """True only if this exact task's own output shows host as changed: -
    scoped to one task by name, unlike parse_recap_changed's whole-play
    PLAY RECAP count. check_todo_7 needs this specifically: once a later
    TODO adds its own task that's unconditionally changed every run (for
    example TODO 10's ansible.builtin.shell append, which has no
    changed_when: false and legitimately writes a new line every time),
    the overall per-host changed count in the PLAY RECAP stops being 0
    on an idempotent second run even though TODO 05/07's own template
    tasks are genuinely no-ops - a false failure unrelated to TODO 07 at
    all. Scoping to one task name by inspecting the lines directly under
    its own TASK [...] banner sidesteps that entirely."""
    block = task_block(text, task_name)
    return any(
        line.strip().startswith(f"changed: [{host}]")
        for line in block.splitlines()
    )


GOLDEN_TASK_NAME = "verify rendered artifact against golden reference"
POLICY_TASK_NAME = "independently verify no disabled vlan leaked into the rendered output"


def check_todo_6():
    """Three-part proof, mirroring TODO 06's own two independent assert
    tasks:

    1. Clean run: both checks must report success, for every device.

    2. Golden-file regression: temporarily corrupt one device's golden
       reference (same temp-corrupt-restore pattern check_todo_3 already
       uses on group_vars/staging.yml). Only that device's own task may
       fail; every other device must be unaffected. Always restores the
       file, even if something raises.

    3. Independent policy re-check: inject the same disabled-VLAN marker
       into a staging device's golden file AND its own already-rendered
       output file - identical bytes, so the golden-compare check alone
       would trivially pass. Re-run starting at the verification tasks
       only (--start-at-task), so the render task doesn't overwrite the
       injected corruption, and confirm the run still fails - proving the
       second check catches this independently of the first, exactly as
       TASK.md describes. Always restores both files.

    Returns a plain bool - unlike TODO 06/07 in a later lab, a single
    corrupted-file scenario is specific and easy to describe in
    PROBLEMS[6] directly, so there's no need for a diagnostics dict here."""
    expected_devices = load_expected_devices()

    # --- Part 1: clean run, every device passes both checks -----------------
    clear_rendered_output()
    clean_result = run_playbook()
    clean_text = clean_result.stdout + "\n" + clean_result.stderr

    for host, expected in expected_devices.items():
        required_lines = [
            f'"output/{host}.cfg matches golden/{expected["site_id"]}/{host}.cfg"',
            '"No disabled VLAN markers leaked into the rendered output."',
            '"Post-render correctness verification passed."',
        ]
        if any(line not in clean_text for line in required_lines):
            return False

    # --- Part 2: a corrupted golden reference must fail only that device ----
    sample_host = "rdu01-cat8k-01"
    golden_file = GOLDEN_DIR / expected_devices[sample_host]["site_id"] / f"{sample_host}.cfg"
    original_golden = golden_file.read_text(encoding="utf-8")
    try:
        golden_file.write_text(original_golden + "\n corrupted-by-grader\n", encoding="utf-8")
        broken_result = run_playbook()
        broken_text = broken_result.stdout + "\n" + broken_result.stderr
    finally:
        golden_file.write_text(original_golden, encoding="utf-8")

    golden_check_caught_it = task_failed_for_host(broken_text, GOLDEN_TASK_NAME, sample_host)
    others_unaffected = all(
        task_passed_for_host(broken_text, GOLDEN_TASK_NAME, host)
        for host in expected_devices
        if host != sample_host
    )

    if not (golden_check_caught_it and others_unaffected):
        return False

    # --- Part 3: independent policy re-check, isolated from part 1 ----------
    staging_host = next(
        host for host, d in expected_devices.items() if d["disabled_vlan_markers"]
    )
    marker = expected_devices[staging_host]["disabled_vlan_markers"][0]
    site_id = expected_devices[staging_host]["site_id"]
    policy_golden_file = GOLDEN_DIR / site_id / f"{staging_host}.cfg"
    policy_output_file = OUTPUT_DIR / f"{staging_host}.cfg"

    original_policy_golden = policy_golden_file.read_text(encoding="utf-8")
    original_policy_output = policy_output_file.read_text(encoding="utf-8")
    try:
        corrupted = original_policy_golden + f"\n{marker}\n"
        policy_golden_file.write_text(corrupted, encoding="utf-8")
        policy_output_file.write_text(corrupted, encoding="utf-8")

        policy_result = run_playbook(extra_args=[
            "--limit", staging_host,
            "--start-at-task", "verify rendered artifact against golden reference",
        ])
        policy_text = policy_result.stdout + "\n" + policy_result.stderr
    finally:
        policy_golden_file.write_text(original_policy_golden, encoding="utf-8")
        policy_output_file.write_text(original_policy_output, encoding="utf-8")

    policy_check_caught_it = task_failed_for_host(policy_text, POLICY_TASK_NAME, staging_host)
    if not policy_check_caught_it:
        return False

    # --- Final clean run, so later TODOs start from a known-good state ------
    clear_rendered_output()
    final_result = run_playbook()
    final_text = final_result.stdout + "\n" + final_result.stderr
    return final_text.count('"Post-render correctness verification passed."') == len(expected_devices)


def parse_recap_changed(text):
    """Parse ansible-playbook's own PLAY RECAP block into {host: changed
    task count}. Used by check_todo_7 as the real proof of idempotency -
    not text matching, but Ansible's own per-host changed counter, which
    only increments when a module actually decided it needed to modify
    something."""
    changed = {}
    for line in text.splitlines():
        match = re.match(r"^(\S+)\s*:\s*ok=\d+\s+changed=(\d+)", line.strip())
        if match:
            changed[match.group(1)] = int(match.group(2))
    return changed


def extract_student_task_block(site_text, todo_number):
    """Extract just the task YAML written for one TODO's STUDENT WORK
    AREA, whether it's still blank (this folder's own TODO) or already
    pre-solved (a later folder, where the same markers carry an
    "(already solved)" suffix and a shorter END TODO N marker instead) -
    used by check_todo_7's fault-injection phase to test the real,
    currently in-place code rather than a hardcoded copy of it."""
    start_pattern = re.compile(
        rf"# STUDENT WORK AREA - TODO {todo_number:02d}.*?\n"
        rf"\s*# =+\n",
    )
    end_pattern = re.compile(
        rf"\n\s*# =+\n\s*# END (?:STUDENT WORK AREA - )?TODO {todo_number:02d}\b"
    )
    start_match = start_pattern.search(site_text)
    end_match = end_pattern.search(site_text, start_match.end())
    return site_text[start_match.end():end_match.start()]


RENDER_TASK_NAME = "render the platform-specific configuration"
REPUBLISH_TASK_NAME = "re-render the platform-specific configuration to confirm publishing is idempotent"


def check_todo_7():
    """Runs the whole playbook twice in a row, with nothing else changed
    in between - the actual test of idempotency, not just a content
    check.

    Scoped to TODO 05's render task and TODO 07's re-render task by name
    (task_changed_for_host), not the PLAY RECAP's overall per-host
    changed count. An overall count would be a false signal once a later
    TODO adds a task that's legitimately changed on every run regardless
    of idempotency - TODO 10's audit-log append, in particular, has no
    changed_when: false and is supposed to write a new line every single
    run. Scoping to these two task names by inspecting their own TASK
    [...] output directly keeps this check honest about what TODO 07
    itself is actually responsible for.

    Run 1 (starting from a cleared output/): TODO 05's render must be
    changed for every device (a genuine first-ever write); TODO 07's
    re-render must already be a no-op right behind it, since content
    matches what TODO 05 just wrote moments earlier in the same run.

    Run 2 (immediately after, output/ left untouched): both tasks must
    be no-ops for every device - proof the entire render/re-render pair
    is a genuine no-op the second time. A student who left TODO 07
    blank, pointed it at the wrong file, or forgot the assert would
    still show TODO 07's task as changed (or missing) here - this can't
    be gamed by hardcoding a success message, since changed: comes from
    Ansible itself, not from anything this grader reads out of debug
    output.

    Also confirms TODO 07's own assert task passed on run 2, so a
    solution that happens to satisfy the changed check some other way
    (e.g. a no-op task) still has to have actually run the right
    assert."""
    expected_devices = load_expected_devices()

    clear_rendered_output()
    first_result = run_playbook()
    first_text = first_result.stdout + "\n" + first_result.stderr

    if not all(task_changed_for_host(first_text, RENDER_TASK_NAME, host) for host in expected_devices):
        return False
    if any(task_changed_for_host(first_text, REPUBLISH_TASK_NAME, host) for host in expected_devices):
        return False

    second_result = run_playbook()
    second_text = second_result.stdout + "\n" + second_result.stderr

    if any(task_changed_for_host(second_text, RENDER_TASK_NAME, host) for host in expected_devices):
        return False
    if any(task_changed_for_host(second_text, REPUBLISH_TASK_NAME, host) for host in expected_devices):
        return False

    if not all(
        task_passed_for_host(second_text, "assert this device's config was not rewritten", host)
        for host in expected_devices
    ):
        return False

    # --- Phase 3: force a real change, confirm the assert genuinely catches it ---
    # Everything above can be satisfied by a no-op `that: true` condition -
    # Ansible's own PLAY RECAP changed counts only reflect the template
    # task, never the assert task itself, so a fake assert that always
    # "passes" would sail through both runs above undetected. This closes
    # that gap the same way TODO 03/06 do: inject a real fault (corrupt
    # one device's already-correct output file), then re-test using a
    # small scratch playbook containing only what TODO 07's own two
    # tasks actually need (service_intent, render_context) plus the
    # student's own TODO 07 block extracted verbatim from site.yml.
    # This can't just be `--start-at-task` on the real site.yml: that
    # would skip render_context's own build task too (undefined
    # variable), and even fixed, TODO 06's own golden-file check sits
    # between TODO 05 and TODO 07 in every later folder and would catch
    # the corruption as its own, unrelated failure before TODO 07 ever
    # got a chance to react to it. Running a minimal scratch playbook
    # sidesteps both problems while still testing the real, currently
    # in-place TODO 07 code, not a hardcoded copy of it.
    sample_host = "rdu01-cat8k-01"
    output_file = OUTPUT_DIR / f"{sample_host}.cfg"
    original_output = output_file.read_text(encoding="utf-8")

    site_text = SITE_FILE.read_text(encoding="utf-8")
    student_block = extract_student_task_block(site_text, 7)

    scratch_file = ROOT / "_todo7_fault_injection_scratch.yml"
    scratch_file.write_text(
        "---\n"
        "- name: fault injection scratch test for TODO 07\n"
        "  hosts: all\n"
        "  gather_facts: false\n"
        "  tasks:\n"
        "    - name: load the declarative service intent\n"
        "      ansible.builtin.include_vars:\n"
        "        file: \"{{ playbook_dir }}/intent/retail_branch_service.yml\"\n"
        "        name: service_intent\n"
        "\n"
        "    - name: build render context\n"
        "      ansible.builtin.set_fact:\n"
        "        render_context:\n"
        "          site_id: \"{{ site_id }}\"\n"
        "          environment_name: \"{{ environment_name }}\"\n"
        "          tenant: \"{{ service_intent.tenant }}\"\n"
        "          service: \"{{ service_intent.service }}\"\n"
        "          hostname: \"{{ hostname }}\"\n"
        "          platform: \"{{ platform }}\"\n"
        "          vlans: \"{{ resolved_vlans }}\"\n"
        + student_block,
        encoding="utf-8",
    )

    try:
        output_file.write_text(original_output + "\ncorrupted-by-grader\n", encoding="utf-8")
        third_result = subprocess.run(
            ["ansible-playbook", "-i", str(INVENTORY_FILE), str(scratch_file), "--limit", sample_host],
            cwd=ROOT, text=True, capture_output=True,
        )
        third_text = third_result.stdout + "\n" + third_result.stderr
    finally:
        output_file.write_text(original_output, encoding="utf-8")
        if scratch_file.exists():
            scratch_file.unlink()

    third_changed = parse_recap_changed(third_text)
    sample_actually_changed = third_changed.get(sample_host) == 1
    assert_caught_it = task_failed_for_host(
        third_text, "assert this device's config was not rewritten", sample_host
    )

    if not (sample_actually_changed and assert_caught_it):
        return False

    # --- Final clean run, so later TODOs start from a known-good state ---
    final_result = run_playbook()
    final_text = final_result.stdout + "\n" + final_result.stderr
    return not any(
        task_changed_for_host(final_text, RENDER_TASK_NAME, host)
        or task_changed_for_host(final_text, REPUBLISH_TASK_NAME, host)
        for host in expected_devices
    )


def line_containing(text, needle):
    for line in text.splitlines():
        if needle in line:
            return line
    return None


def clean_msg_line(line):
    """Ansible's debug module renders a msg: list as JSON-ish lines like
    '        "Loaded service: branch-network-standard",' - strip the
    indentation, the surrounding quotes, and the trailing comma so it
    reads the same as a plain print() line would."""
    if line is None:
        return None
    line = line.strip()
    if line.endswith(","):
        line = line[:-1]
    if line.startswith('"') and line.endswith('"'):
        line = line[1:-1]
    return line


def playbook_failed_to_parse(result):
    """Ansible's own dedicated exit code (4) for "the playbook itself
    could not even be parsed" - a YAML or task-structure error (bad
    indentation, conflicting action statements, and similar), completely
    different from a normal task failure on a host. When this happens,
    no host ever started running any task at all, so there is no way to
    tell which TODO the broken task belongs to from the (empty) run
    output alone - every later check would wrongly blame whichever TODO
    happens to be checked first. Report Ansible's own error directly
    instead of guessing a TODO number."""
    return result is not None and result.returncode == 4


def print_parse_error(result):
    banner("site.yml could not be parsed", YELLOW)
    console.print(c(
        "Ansible could not even start running the playbook - this is a YAML "
        "or task-structure error somewhere in site.yml, not a specific TODO "
        "being incomplete. Fix this error, then run python grading.py again.",
        YELLOW,
    ))
    console.print()
    section("Ansible's error", result.stderr.strip(), RED)


def compute_statuses():
    statuses = {1: check_todo_1()}

    playbook_result = None
    if statuses[1]:
        playbook_result = run_playbook()
        if playbook_failed_to_parse(playbook_result):
            return statuses, {"parse_error": playbook_result}

    statuses[2] = check_todo_2(playbook_result)
    statuses[3] = check_todo_3() if (statuses[1] and statuses[2]) else False

    # TODO 4 needs its own clean run, since TODO 3's check ran the playbook
    # against a temporarily-broken group_vars/staging.yml last.
    todo_4_result = None
    if statuses[1] and statuses[2] and statuses[3]:
        todo_4_result = run_playbook()
    statuses[4] = check_todo_4(todo_4_result)

    # TODO 5 is file-based (see check_todo_5), but it still needs a run to
    # actually produce output/*.cfg - clear any stale files first so a
    # blank STUDENT WORK AREA can't pass on leftover output from an
    # earlier successful run.
    todo_5_result = None
    if statuses[1] and statuses[2] and statuses[3] and statuses[4]:
        clear_rendered_output()
        todo_5_result = run_playbook()
    statuses[5] = check_todo_5() if todo_5_result is not None else False

    # TODO 6 runs the playbook several more times itself (clean run, a
    # corrupted-golden run, an isolated policy-check run) - see
    # check_todo_6's own docstring for why each one is needed.
    statuses[6] = check_todo_6() if statuses[5] else False

    # TODO 7 runs the whole playbook twice more itself (see check_todo_7's
    # own docstring) - only worth doing once TODO 06 is confirmed correct.
    statuses[7] = check_todo_7() if statuses[6] else False

    # TODO 8 needs the mock device fleet actually running - start it fresh,
    # then check_todo_8 handles its own playbook runs (a clean run, a
    # fault-injection run, and a final clean re-verification) before the
    # fleet is torn down.
    # TODO 9 shares that same fleet session - it builds directly on
    # TODO 8's own push task, so there's no reason to tear the fleet down
    # and start a second one.
    todo_8_status = False
    todo_8_diagnostics = {}
    todo_9_status = False
    todo_9_diagnostics = {}
    mock_fleet_error = None
    if statuses[7]:
        mock_process, mock_fleet_error = start_mock_fleet()
        if mock_process is not None:
            try:
                todo_8_status, todo_8_diagnostics = check_todo_8()

                if todo_8_status:
                    todo_9_status, todo_9_diagnostics = check_todo_9()
            finally:
                stop_mock_fleet(mock_process)
    statuses[8] = todo_8_status
    statuses[9] = todo_9_status

    context = {
        "playbook_result": todo_5_result or todo_4_result or playbook_result,
        "todo_8_diagnostics": todo_8_diagnostics,
        "todo_9_diagnostics": todo_9_diagnostics,
        "expected_devices": load_expected_devices(),
        "mock_fleet_error": mock_fleet_error,
    }
    return statuses, context


def first_failed_todo(statuses):
    for number in range(1, TOTAL_TODOS + 1):
        if not statuses[number]:
            return number
    return None


# -----------------------------------------------------------------------------
# TODO progress / feedback / summary
# -----------------------------------------------------------------------------

def print_todo_details(number, statuses, context):
    if number == 1:
        console.print("[1] Authoring the declarative service intent...")
        if statuses[number]:
            console.print("intent/retail_branch_service.yml matches the required business requirements.")

    elif number == 2:
        console.print("[2] Loading the declarative service intent...")
        if statuses[number]:
            result = context["playbook_result"]
            expected_devices = context["expected_devices"]
            text = (result.stdout + "\n" + result.stderr) if result else ""

            service_line = clean_msg_line(line_containing(text, "Loaded service:"))
            tenant_line = clean_msg_line(line_containing(text, "Loaded tenant:"))
            if service_line:
                console.print(service_line)
            if tenant_line:
                console.print(tenant_line)

            environments = sorted({d["environment_name"] for d in expected_devices.values()})
            sites = sorted({d["site_id"] for d in expected_devices.values()})
            console.print(f"Loaded environments: {environments}")
            console.print(f"Loaded sites: {sites}")
            console.print(f"Loaded devices ({len(expected_devices)}): {sorted(expected_devices.keys())}")

    elif number == 3:
        console.print("[3] Running pre-flight validation...")
        if statuses[number]:
            expected_devices = context["expected_devices"]
            console.print("Injected an unknown disabled role into group_vars/staging.yml:")
            console.print(f"  sea03-cat8k-01, sea03-n9k-01 (staging) -> failed as expected")
            console.print(f"  {len(expected_devices) - 2} prod device(s) -> unaffected, as expected")
            console.print("Restored group_vars/staging.yml - all 9 devices pass again.")

    elif number == 4:
        console.print("[4] Building environment- and site-aware render facts...")
        if statuses[number]:
            expected_devices = context["expected_devices"]
            for host in sorted(expected_devices.keys()):
                d = expected_devices[host]
                console.print(f"  {host} -> render_context.hostname: {d['hostname']}, vlans: {d['vlan_ids']}")

    elif number == 5:
        console.print("[5] Rendering multi-platform artifacts...")
        if statuses[number]:
            expected_devices = context["expected_devices"]
            for host in sorted(expected_devices.keys()):
                site_id = expected_devices[host]["site_id"]
                output_file = OUTPUT_DIR / f"{host}.cfg"
                first_line = output_file.read_text(encoding="utf-8").splitlines()[0]
                console.print(f"  {host} -> output/{host}.cfg matches golden/{site_id}/{host}.cfg ({first_line!r})")

    elif number == 6:
        console.print("[6] Running post-render correctness verification...")
        if statuses[number]:
            console.print("Golden-output regression check: passes on correct output, fails on a corrupted reference.")
            console.print("Independent policy re-check: passes on correct output, still catches a leaked disabled VLAN even when golden and output agree with each other.")
            expected_devices = context["expected_devices"]
            for host in sorted(expected_devices.keys()):
                console.print(f"  {host} -> both checks passed")

    elif number == 7:
        console.print("[7] Publishing idempotently...")
        if statuses[number]:
            expected_devices = context["expected_devices"]
            console.print("Run 1 (clean output/): every device showed exactly 1 changed task (the first render).")
            console.print("Run 2 (immediately after): every device showed exactly 0 changed tasks.")
            for host in sorted(expected_devices.keys()):
                console.print(f"  {host} -> already correct on disk, nothing rewritten")

    elif number == 8:
        console.print("[8] Pushing rendered configuration via RESTCONF, with retry (staging only)...")
        if statuses[number]:
            expected_devices = context["expected_devices"]
            for host in sorted(expected_devices.keys()):
                if host in STAGING_DEVICES:
                    console.print(f"  {host} (staging) -> pushed, GET confirmed the device now holds it")
                else:
                    console.print(f"  {host} (prod) -> held for approval, GET confirmed nothing was pushed")
            console.print("Fault injection: a transient 503 was retried until it succeeded (3 attempts); a permanent 422 failed immediately and was never retried (1 attempt).")
        else:
            diagnostics = context.get("todo_8_diagnostics") or {}
            by_reason = {}
            for host, reason in sorted(diagnostics.items()):
                by_reason.setdefault(reason, []).append(host)
            for reason, hosts in by_reason.items():
                console.print(f"  {', '.join(hosts)} -> {reason}")

    elif number == 9:
        console.print("[9] Verifying device state via RESTCONF...")
        if statuses[number]:
            console.print("sea03-n9k-01 (mock made to lie) -> caught: live state did not match, task failed as expected")
            console.print("sea03-cat8k-01 (truthful) -> verified: live state matches what was pushed")
            console.print("With no lie injected, both staging devices push and verify correctly.")
        else:
            diagnostics = context.get("todo_9_diagnostics") or {}
            by_reason = {}
            for host, reason in sorted(diagnostics.items()):
                by_reason.setdefault(reason, []).append(host)
            for reason, hosts in by_reason.items():
                console.print(f"  {', '.join(hosts)} -> {reason}")


def print_todo_progress(statuses, context):
    banner("TODO PROGRESS")

    for number in range(1, TOTAL_TODOS + 1):
        console.print(c(f"{todo_label(number)} - {TODO_NAMES[number]}", f"{BOLD}{CYAN}"))
        console.print(Rule(style=CYAN))
        console.print()

        print_todo_details(number, statuses, context)
        console.print()

        if statuses[number]:
            console.print(c(f"✓ {todo_label(number)} Complete", f"{BOLD}{GREEN}"))
            console.print(c(SUCCESS_MESSAGES[number], GREEN))
            if number < TOTAL_TODOS:
                console.print()
                console.print(c(f"Moving to {todo_label(number + 1)}...", DIM))
            divider()
            continue

        console.print(c(f"✗ {todo_label(number)} Not Complete", f"{BOLD}{YELLOW}"))
        console.print()
        console.print(c(FAIL_MESSAGES[number], YELLOW))
        console.print()
        console.print(c("Proceeding to detailed feedback...", DIM))
        divider()
        break


def feedback(failed, context=None):
    banner("FEEDBACK")

    if failed is None:
        for number in range(1, TOTAL_TODOS + 1):
            console.print(Text.assemble(("[PASS] ", "bold green"), (f"{todo_label(number)} - {TODO_NAMES[number]}", "bold")))
        return

    for number in range(1, failed):
        console.print(Text.assemble(("[PASS] ", "bold green"), (f"{todo_label(number)} - {TODO_NAMES[number]}", "bold")))

    console.print()
    console.print(Text.assemble(("[FAIL] ", "bold red"), (f"{todo_label(failed)} - {TODO_NAMES[failed]}", "bold")))
    console.print()

    problem_text = PROBLEMS[failed]
    if failed in (8, 9, 10):
        diagnostics = (context or {}).get(f"todo_{failed}_diagnostics") or {}
        if diagnostics:
            by_reason = {}
            for host, reason in sorted(diagnostics.items()):
                by_reason.setdefault(reason, []).append(host)
            detail_lines = "\n".join(f"  {', '.join(hosts)}: {reason}" for reason, hosts in by_reason.items())
            problem_text = f"{problem_text}\n\nPer device:\n{detail_lines}"

    section("Problem", problem_text, YELLOW)
    section("Expected", EXPECTED[failed], CYAN)
    section("Hint", HINTS[failed], GREEN)

    console.print("Type S and press Enter to reveal the solution, or press Enter to skip: ", end="")
    try:
        answer = input().strip().lower()
    except EOFError:
        answer = ""

    if answer == "s":
        console.print()
        syntax = Syntax(SOLUTIONS[failed], "yaml", theme="ansi_dark", line_numbers=False, word_wrap=True)
        console.print(Panel(syntax, title="Solution", title_align="left", border_style=GREEN, padding=(0, 1)))
        console.print()


def lab_summary(statuses):
    completed = sum(1 for number in range(1, TOTAL_TODOS + 1) if statuses[number])
    failed = first_failed_todo(statuses)
    percent = int((completed / TOTAL_TODOS) * 100)

    if failed is None:
        banner(f"{todo_label(TOTAL_TODOS)} COMPLETE - LAB {TOTAL_TODOS} OF 10 DONE", GREEN)
        console.print(c("Progress", f"{BOLD}{CYAN}"))
        console.print(Rule(style=CYAN))
        console.print(render_bar(completed, TOTAL_TODOS))
        console.print(f"  {percent}% Complete ({completed} of {TOTAL_TODOS} TODOs in this lab)")
        console.print()
        console.print(f"  {todo_label(TOTAL_TODOS)} - {TODO_NAMES[TOTAL_TODOS]} - is complete.")
        console.print("  Move on to the next lab; everything done here will")
        console.print("  already be done for you there.")
        console.print()
        return

    banner("LAB NOT COMPLETE", YELLOW)
    console.print(c("Progress", f"{BOLD}{CYAN}"))
    console.print(Rule(style=CYAN))
    console.print(render_bar(completed, TOTAL_TODOS))
    console.print(f"  {percent}% Complete ({completed} of {TOTAL_TODOS} TODOs)")
    console.print()

    console.print(c("Completed", f"{BOLD}{GREEN}"))
    console.print(Rule(style=GREEN))
    if completed == 0:
        console.print("  No TODOs completed yet.")
    else:
        for number in range(1, failed):
            console.print(f"  ✓ {todo_label(number)} - {TODO_NAMES[number]}")
    console.print()

    console.print(c("Remaining", f"{BOLD}{YELLOW}"))
    console.print(Rule(style=YELLOW))
    for number in range(failed, TOTAL_TODOS + 1):
        console.print(f"  ✗ {todo_label(number)} - {TODO_NAMES[number]}")
    console.print()

    console.print(c("Next Step", f"{BOLD}{CYAN}"))
    console.print(Rule(style=CYAN))
    console.print(f"  Complete {todo_label(failed)} and run:")
    console.print()
    console.print("  python grading.py")
    console.print()


def main():
    banner("Production-Grade IaC with Ansible")

    statuses, context = compute_statuses()

    if context.get("parse_error"):
        print_parse_error(context["parse_error"])
        sys.exit(1)

    if context.get("mock_fleet_error"):
        print_mock_fleet_error(context["mock_fleet_error"])
        sys.exit(1)

    print_todo_progress(statuses, context)
    pause("Press ENTER to view detailed feedback...")

    failed = first_failed_todo(statuses)
    feedback(failed, context)
    pause("Press ENTER to view lab progress...")

    divider()
    lab_summary(statuses)
    pause("Press ENTER to exit...")

    sys.exit(0 if failed is None else 1)


if __name__ == "__main__":
    main()
