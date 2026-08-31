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
"""

import json
import os
import subprocess
import sys
from pathlib import Path

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

console = Console(markup=False, highlight=False)

BOLD = "bold "
DIM = "dim"
RED = "red"
GREEN = "green"
YELLOW = "yellow"
CYAN = "cyan"

# Set to False, or run with CAPSTONE_INTERACTIVE=0, to disable ENTER pauses.
INTERACTIVE_MODE = os.environ.get("CAPSTONE_INTERACTIVE", "1") != "0"

TOTAL_TODOS = 6

TODO_NAMES = {
    1: "Author the Declarative Service Intent",
    2: "Load the Declarative Service Intent",
    3: "Run Pre-Flight Validation",
    4: "Build Environment- and Site-Aware Render Facts",
    5: "Render Multi-Platform Artifacts",
    6: "Run Post-Render Correctness Verification",
}

SUCCESS_MESSAGES = {
    1: "intent/retail_branch_service.yml captures the business requirements correctly.",
    2: "service_intent was loaded correctly and is visible, correctly resolved, on every one of the 9 devices.",
    3: "Pre-flight validation is running and correctly catches a bad cross-file reference.",
    4: "render_context was assembled correctly for every one of the 9 devices.",
    5: "Every device's rendered artifact matches its golden reference config exactly.",
    6: "Post-render verification is running and independently catches both a corrupted golden reference and a leaked disabled VLAN.",
}

FAIL_MESSAGES = {
    1: "The pipeline cannot continue because the declarative service intent has not been authored correctly yet.",
    2: "The pipeline cannot continue because the declarative service intent has not been loaded yet.",
    3: "The pipeline cannot continue because pre-flight validation is not actually being executed.",
    4: "The pipeline cannot continue because render_context has not been built yet.",
    5: "The pipeline cannot continue because no device configuration has been rendered yet.",
    6: "The pipeline cannot continue because post-render verification is not actually being executed, or does not independently catch a leaked disabled VLAN.",
}

HINTS = {
    1: "Create intent/retail_branch_service.yml by hand. Match the shape in TASK.md (tenant, service, vlans: [{role, name, enabled}]) using the business requirements table exactly - YAML, not JSON.",
    2: "Use the include_vars module. Point its file: option at intent/retail_branch_service.yml (playbook_dir is the directory site.yml lives in), and set name: service_intent so the whole file lands under one variable instead of three separate loose variables.",
    3: "Write one assert task whose that: condition checks that every role in disabled_roles is also a real role somewhere in service_intent.vlans - Jinja's `difference` filter returns items in the first list that are NOT in the second, so `disabled_roles | difference(<all valid roles>) | length == 0` means every disabled role was found among the valid ones. Add register: preflight_result too - the guard task right after STUDENT WORK AREA - TODO 03 checks for it to confirm this task actually ran at all.",
    4: "Use set_fact to build a dict named render_context with exactly these keys: site_id, environment_name, tenant (from service_intent.tenant), service (from service_intent.service), hostname, platform, and vlans (= resolved_vlans). Every value on the right already exists as a variable - this task only combines them.",
    5: "Use the template module with src: chosen by render_context.platform (cat8k -> cat8k_ospf.j2, nexus9k -> nexus_vlan.j2) and dest: output/<device_id>.cfg. The templates expect plain hostname and vlans variables, not render_context.hostname/render_context.vlans - use this task's own vars: to expose them under those exact names.",
    6: "Write two assert tasks. First: lookup('file', ...output.../<device_id>.cfg) equals lookup('file', ...golden.../<device_id>.cfg). Second: disabled_vlan_markers (already computed for you in inventory/devices.py) | select('in', <that same rendered text>) | list | length == 0 - the Jinja 'in' test does substring containment when the right side is a string, so this finds any disabled VLAN marker that leaked into the rendered text, independently of golden - register: policy_check_result on this second task only (if it runs at all, the first one already passed). The guard task right after STUDENT WORK AREA - TODO 06 checks for policy_check_result to confirm both tasks actually ran.",
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
    3: '''- name: pre-flight validation
  ansible.builtin.assert:
    that:
      - disabled_roles | difference(service_intent.vlans | map(attribute='role') | list) | length == 0
    fail_msg: "Pre-flight validation failed for {{ inventory_hostname }}."
    success_msg: "Pre-flight validation passed for {{ inventory_hostname }}."
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
      - disabled_vlan_markers
        | select('in', lookup('file', playbook_dir + '/output/' + device_id + '.cfg'))
        | list | length == 0
    fail_msg: "A disabled VLAN marker leaked into output/{{ device_id }}.cfg."
  register: policy_check_result''',
}

EXPECTED = {
    1: "intent/retail_branch_service.yml should exist with tenant: \"Meridian Retail\", service: \"branch-network-standard\", and exactly the 5 VLAN definitions specified in TASK.md.",
    2: "Running the playbook should succeed for all 9 devices, and the debug task's output should show the correct service, tenant, environment, device identity, and resolved_vlans for every one of them.",
    3: "A validation failure injected into group_vars/staging.yml (an unknown disabled role) should fail the 2 staging devices and leave the 7 prod devices unaffected. After restoring the file, all 9 devices should pass.",
    4: "render_context.hostname and render_context.vlans should exactly match this device's own hostname and resolved_vlans for all 9 devices.",
    5: "output/<device_id>.cfg should exist and match golden/<site_id>/<device_id>.cfg exactly for all 9 devices - the right template for each device's platform, with the right hostname and vlans substituted in.",
    6: "Every device should report both checks passing on a clean run. Corrupting one device's golden reference should fail only that device. Injecting a disabled VLAN marker into a staging device's golden file AND its own rendered output (identical bytes) should still fail that device, proving the second check works independently of the first.",
}

PROBLEMS = {
    1: "The declarative service intent file is missing, malformed, or does not match the required business requirements.",
    2: "service_intent is not being loaded (or not loaded correctly) from intent/retail_branch_service.yml.",
    3: "Pre-flight validation did not catch an intentionally broken cross-file reference, or broke devices it shouldn't have.",
    4: "render_context is missing, or one of its fields doesn't match this device's own already-known values.",
    5: "No config was rendered for one or more devices, the wrong template was used for a device's platform, or the rendered content doesn't match golden.",
    6: "Post-render verification is missing, doesn't run for every device, or the disabled-VLAN check trusts golden/output content instead of independently re-deriving from disabled_vlan_markers.",
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
    so pass/fail here is decided purely by whether each host's own
    pre-flight validation task printed the fail_msg / success_msg it was
    supposed to - never by recap counts."""
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
            f'"Pre-flight validation failed for {host}."' in broken_text
            and f'"Pre-flight validation passed for {host}."' not in broken_text
            for host in STAGING_DEVICES
        )
        prod_unaffected = all(
            f'"Pre-flight validation passed for {host}."' in broken_text
            for host in PROD_DEVICES
        )
    finally:
        STAGING_FILE.write_text(original, encoding="utf-8")

    if not (staging_correctly_failed and prod_unaffected):
        return False

    clean_result = run_playbook()
    clean_text = clean_result.stdout + clean_result.stderr

    return all(
        f'"Pre-flight validation passed for {host}."' in clean_text
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

    golden_check_caught_it = (
        f"Rendered artifact for {sample_host} does not match" in broken_text
    )
    success_count = broken_text.count('"Post-render correctness verification passed."')
    others_unaffected = success_count == len(expected_devices) - 1

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

    policy_check_caught_it = (
        f"A disabled VLAN marker leaked into output/{staging_host}.cfg." in policy_text
    )
    if not policy_check_caught_it:
        return False

    # --- Final clean run, so later TODOs start from a known-good state ------
    clear_rendered_output()
    final_result = run_playbook()
    final_text = final_result.stdout + "\n" + final_result.stderr
    return final_text.count('"Post-render correctness verification passed."') == len(expected_devices)


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

    context = {
        "playbook_result": todo_5_result or todo_4_result or playbook_result,
        "expected_devices": load_expected_devices(),
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


def feedback(failed):
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

    section("Problem", PROBLEMS[failed], YELLOW)
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

    print_todo_progress(statuses, context)
    pause("Press ENTER to view detailed feedback...")

    failed = first_failed_todo(statuses)
    feedback(failed)
    pause("Press ENTER to view lab progress...")

    divider()
    lab_summary(statuses)
    pause("Press ENTER to exit...")

    sys.exit(0 if failed is None else 1)


if __name__ == "__main__":
    main()
