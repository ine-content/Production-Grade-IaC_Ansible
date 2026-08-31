# Production-Grade IaC with Ansible

## Setup

```bash
pip install ansible-core rich requests pyyaml
```

No collections need to be installed — every task in this course uses modules that ship with `ansible-core` itself. There is nothing to fetch from Ansible Galaxy, which matters on an offline lab VM.

## Run

```bash
python grading.py
```

This TODO's grader temporarily edits `group_vars/staging.yml` while re-verifying TODO 03, and `golden/<site_id>/<device_id>.cfg` (and, briefly, `output/<device_id>.cfg`) while re-verifying TODO 06 — restoring each one afterward. You don't need to do anything about that yourself.

The grader automatically starts a local mock RESTCONF device fleet in the background for TODO 08 through TODO 10 (they share one fleet session), and shuts it down when it finishes. You do not need to start anything yourself. It supplies its own fixed RESTCONF test credentials to that fleet, so grading works the same way regardless of what's in `.env`.

Grading TODO 08 and TODO 09 both briefly write `mock_fault_injection.json` (TODO 08 makes one staging device fail its first two attempts and another always fail; TODO 09 makes one staging device silently ignore every push while still returning success) so each check can actually observe the behavior it's testing for, then delete it again before finishing — you don't need to do anything about that yourself, and it's always removed even if a check fails partway through.

Grading TODO 10 deletes any existing `logs/audit.jsonl` before its own clean run, so a line left over from an earlier check in the same grading session (or an earlier manual run of yours) can never be mistaken for this run's own record.

A `.env` is already pre-created for you in this folder (username and password both `api`, for every environment) — you don't need to copy `.env.example` yourself.

If you want to run this by hand (outside the grader), just:

```bash
./run_playbook.sh                     # any ansible-playbook flag works too, e.g. ./run_playbook.sh --check
```

One command, no separate terminal needed. `ansible-playbook` on its own does not start the mock device fleet (it only talks to whatever's already listening, the same as it would never power on a real switch for you) and does not read `.env` files itself (only `mock_device_server.py` does). `run_playbook.sh` handles both: it stops any mock fleet already running, starts its own fresh one (logging to `logs/mock_device_server.log`), exports `.env` into its own shell, runs the playbook, then stops the fleet again when it's done — even if the playbook fails. `mock_device_state.json` (the fleet's persisted device memory) is never touched by this, so drift you introduce in one run is still there in the next.

Want to watch the mock fleet's log live instead of just the file? Run `python mock_device_server.py` yourself in a separate terminal first, then call `ansible-playbook -i inventory/devices.py site.yml` directly instead of `run_playbook.sh`.

(You do NOT need any of this just to grade — `python grading.py` manages its own mock fleet and sets its own credentials directly, entirely separately from `.env` and `run_playbook.sh`.)

macOS also needs the loopback aliases set up once per reboot before `mock_device_server.py` will bind:

```bash
sudo ./setup_local_loopback.sh
```

(Not needed on Linux, or in a real GitLab CI runner.)

## Student Files

Edit:

```text
site.yml   (TODO 10 - the last TODO in this course)
```

Do not modify `inventory/devices.py`, `mock_device_server.py`, `grading.py`, `intent/retail_branch_service.yml`, `.env`, `run_playbook.sh`, or anything under `group_vars/`, `sites/`, `devices/`, `templates/`, or `golden/`.
