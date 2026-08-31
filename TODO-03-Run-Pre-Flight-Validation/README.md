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

The grader automatically starts a local mock RESTCONF device fleet in the background for the TODOs that need it, and shuts it down when it finishes. You do not need to start anything yourself.

This TODO's grader also temporarily edits `group_vars/staging.yml` to prove your validation actually runs, and restores it afterward — you don't need to do anything about that yourself either.

## Student Files

Edit:

```text
site.yml   (TODO 03 - and every later TODO in this course)
```

Do not modify `inventory/devices.py`, `mock_device_server.py`, `grading.py`, `intent/retail_branch_service.yml`, `.env` (pre-created for you — see `.env.example`), or anything under `group_vars/`, `sites/`, `devices/`, `templates/`, or `golden/`.
