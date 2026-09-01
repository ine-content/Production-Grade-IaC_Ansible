#!/usr/bin/env python3

"""
Production-Grade IaC with Ansible - Coaching-Style Grader (Rich terminal UI)

This grader validates the course one TODO at a time, always starting from
TODO 01, and stops at the first incomplete one - even though TODO 01 and
TODO 02 are already solved for you in this folder, it re-checks them live
every run, so you always see real, current proof that nothing earlier
broke, not a cached checkmark.

TODO 03 is checked by temporarily breaking a real cross-file reference
(group_vars/staging.yml disabling a VLAN role, "gust", that was never
defined in the service intent), running the playbook, and confirming the
2 staging devices fail while the 7 prod devices are unaffected - proof
your validation is actually being executed, not just present as an inert
assert that would pass no matter what. The file is always restored
afterward, and this check only runs at all once TODO 01 and TODO 02 are
already confirmed correct, so a failure here always means TODO 03
specifically, never noise from an earlier TODO.
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

console = Console(markup=False, highlight=False)

BOLD = "bold "
DIM = "dim"
RED = "red"
GREEN = "green"
YELLOW = "yellow"
CYAN = "cyan"

# Set to False, or run with CAPSTONE_INTERACTIVE=0, to disable ENTER pauses.
INTERACTIVE_MODE = os.environ.get("CAPSTONE_INTERACTIVE", "1") != "0"

TOTAL_TODOS = 3

TODO_NAMES = {
    1: "Author the Declarative Service Intent",
    2: "Load the Declarative Service Intent",
    3: "Run Pre-Flight Validation",
}

SUCCESS_MESSAGES = {
    1: "intent/retail_branch_service.yml captures the business requirements correctly.",
    2: "service_intent was loaded correctly and is visible, correctly resolved, on every one of the 9 devices.",
    3: "Pre-flight validation is running and correctly catches a bad cross-file reference.",
}

FAIL_MESSAGES = {
    1: "The pipeline cannot continue because the declarative service intent has not been authored correctly yet.",
    2: "The pipeline cannot continue because the declarative service intent has not been loaded yet.",
    3: "The pipeline cannot continue because pre-flight validation is not actually being executed.",
}

HINTS = {
    1: "Create intent/retail_branch_service.yml by hand. Match the shape in TASK.md (tenant, service, vlans: [{role, name, enabled}]) using the business requirements table exactly - YAML, not JSON.",
    2: "Use the include_vars module. Point its file: option at intent/retail_branch_service.yml (playbook_dir is the directory site.yml lives in), and set name: service_intent so the whole file lands under one variable instead of three separate loose variables.",
    3: "First build a plain list of every valid role with a set_fact (service_intent.vlans | map(attribute='role') | list). Then write one assert task, looped with loop: \"{{ disabled_roles }}\", whose that: condition is simply `item in valid_roles` - true when the current disabled role is one of the real ones. Add register: preflight_result on this assert task too - the guard task right after STUDENT WORK AREA - TODO 03 checks for it to confirm this task actually ran at all.",
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
}

EXPECTED = {
    1: "intent/retail_branch_service.yml should exist with tenant: \"Meridian Retail\", service: \"branch-network-standard\", and exactly the 5 VLAN definitions specified in TASK.md.",
    2: "Running the playbook should succeed for all 9 devices, and the debug task's output should show the correct service, tenant, environment, device identity, and resolved_vlans for every one of them.",
    3: "A validation failure injected into group_vars/staging.yml (an unknown disabled role) should fail the 2 staging devices and leave the 7 prod devices unaffected. After restoring the file, all 9 devices should pass.",
}

PROBLEMS = {
    1: "The declarative service intent file is missing, malformed, or does not match the required business requirements.",
    2: "service_intent is not being loaded (or not loaded correctly) from intent/retail_branch_service.yml.",
    3: "Pre-flight validation did not catch an intentionally broken cross-file reference, or broke devices it shouldn't have.",
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
            "vlan_ids": [vlan["id"] for vlan in hostvars["resolved_vlans"]],
        }
    return devices


def run_playbook():
    return subprocess.run(
        ["ansible-playbook", "-i", str(INVENTORY_FILE), str(SITE_FILE)],
        cwd=ROOT, text=True, capture_output=True,
    )


def check_todo_2(result):
    """Content-based on purpose: never rely on the overall PLAY RECAP
    failed/unreachable counts here. Once a later TODO (3) exists in the
    same site.yml and is still blank, its own guard task fails and the
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


def check_recap(text, host, expect_failed):
    for line in text.splitlines():
        if line.strip().startswith(host) and "ok=" in line:
            failed_zero = "failed=0" in line
            return (not failed_zero) if expect_failed else failed_zero
    return False


def check_todo_3():
    """Only called once TODO 01 and TODO 02 are already confirmed correct -
    see compute_statuses(). Temporarily breaks group_vars/staging.yml,
    always restores it in a finally block even if something raises."""
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
            check_recap(broken_text, host, expect_failed=True) for host in STAGING_DEVICES
        )
        prod_unaffected = all(
            check_recap(broken_text, host, expect_failed=False) for host in PROD_DEVICES
        )
    finally:
        STAGING_FILE.write_text(original, encoding="utf-8")

    if not (staging_correctly_failed and prod_unaffected):
        return False

    clean_result = run_playbook()
    clean_text = clean_result.stdout + clean_result.stderr

    if clean_result.returncode != 0:
        return False

    all_passed = all(
        check_recap(clean_text, host, expect_failed=False) for host in (STAGING_DEVICES | PROD_DEVICES)
    )
    if not all_passed:
        return False

    return "Pre-flight validation passed." in clean_text


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

    context = {"playbook_result": playbook_result, "expected_devices": load_expected_devices()}
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
            console.print("Restored group_vars/staging.yml - all 9 devices pass again:")
            for host in sorted(expected_devices.keys()):
                d = expected_devices[host]
                console.print(f"  {host} ({d['environment_name']}) -> Pre-flight validation passed.")


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
