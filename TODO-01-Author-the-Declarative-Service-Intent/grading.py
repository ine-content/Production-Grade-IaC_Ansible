#!/usr/bin/env python3

"""
Production-Grade IaC with Ansible - Coaching-Style Grader (Rich terminal UI)

This grader validates the course one TODO at a time, always starting from
TODO 01, and stops at the first incomplete one - even in a later lab
folder where earlier TODOs are already solved for you, it re-checks them
every run, so you always see real, current proof that nothing earlier
broke, not a cached checkmark.

Student experience:
- TODO progress (every TODO from 1 up to this lab's total, re-checked live)
- Detailed feedback on the first incomplete one
- Lab progress summary
- Solution hidden unless you type S
"""

import os
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

console = Console(markup=False, highlight=False)

BOLD = "bold "
DIM = "dim"
RED = "red"
GREEN = "green"
YELLOW = "yellow"
CYAN = "cyan"

# Set to False, or run with CAPSTONE_INTERACTIVE=0, to disable ENTER pauses.
INTERACTIVE_MODE = os.environ.get("CAPSTONE_INTERACTIVE", "1") != "0"

TOTAL_TODOS = 1

TODO_NAMES = {
    1: "Author the Declarative Service Intent",
}

SUCCESS_MESSAGES = {
    1: "intent/retail_branch_service.yml captures the business requirements correctly.",
}

FAIL_MESSAGES = {
    1: "The pipeline cannot continue because the declarative service intent has not been authored correctly yet.",
}

HINTS = {
    1: "Create intent/retail_branch_service.yml by hand. Match the shape in TASK.md (tenant, service, vlans: [{role, name, enabled}]) using the business requirements table exactly - YAML, not JSON.",
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
}

EXPECTED = {
    1: "intent/retail_branch_service.yml should exist with tenant: \"Meridian Retail\", service: \"branch-network-standard\", and exactly the 5 VLAN definitions specified in TASK.md.",
}

PROBLEMS = {
    1: "The declarative service intent file is missing, malformed, or does not match the required business requirements.",
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
# TODO 01 check
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


def compute_statuses():
    return {1: check_todo_1()}


def first_failed_todo(statuses):
    for number in range(1, TOTAL_TODOS + 1):
        if not statuses[number]:
            return number
    return None


# -----------------------------------------------------------------------------
# TODO progress / feedback / summary
# -----------------------------------------------------------------------------

def print_todo_details(number, statuses):
    if number == 1:
        console.print("[1] Authoring the declarative service intent...")
        if statuses[number]:
            console.print("intent/retail_branch_service.yml matches the required business requirements.")


def print_todo_progress(statuses):
    banner("TODO PROGRESS")

    for number in range(1, TOTAL_TODOS + 1):
        console.print(c(f"{todo_label(number)} - {TODO_NAMES[number]}", f"{BOLD}{CYAN}"))
        console.print(Rule(style=CYAN))
        console.print()

        print_todo_details(number, statuses)
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
        lexer = "yaml" if failed == 1 else "yaml"
        syntax = Syntax(SOLUTIONS[failed], lexer, theme="ansi_dark", line_numbers=False, word_wrap=True)
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

    statuses = compute_statuses()
    print_todo_progress(statuses)
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
