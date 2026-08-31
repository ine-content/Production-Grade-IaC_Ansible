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

This TODO's grader temporarily edits `group_vars/staging.yml` while re-verifying TODO 03, and `golden/<site_id>/<device_id>.cfg` (and, briefly, `output/<device_id>.cfg`) while verifying TODO 06 itself — restoring each one afterward. You don't need to do anything about that yourself.

This lab doesn't need the mock RESTCONF device fleet yet (`mock_device_server.py` is here for a later TODO) — grading TODO 06 never starts it.

## Student Files

Edit:

```text
site.yml   (TODO 06 - and every later TODO in this course)
```

Do not modify `inventory/devices.py`, `mock_device_server.py`, `grading.py`, `intent/retail_branch_service.yml`, `.env` (pre-created for you — see `.env.example`), or anything under `group_vars/`, `sites/`, `devices/`, `templates/`, or `golden/`.
