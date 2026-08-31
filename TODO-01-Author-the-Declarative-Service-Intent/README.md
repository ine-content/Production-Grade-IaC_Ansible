# Production-Grade IaC with Ansible

## Setup

```bash
pip install ansible-core rich requests pyyaml
```

No collections need to be installed — every task in this course uses modules that ship with `ansible-core` itself (`ansible.builtin.uri`, `ansible.builtin.template`, `ansible.builtin.assert`, ...). There is nothing to fetch from Ansible Galaxy, which matters on an offline lab VM.

## Run

```bash
python grading.py
```

The grader automatically starts a local mock RESTCONF device fleet in the background for the TODOs that need it, and shuts it down when it finishes. You do not need to start anything yourself.

## Student Files

Edit or create:

```text
intent/retail_branch_service.yml   (you create this — TODO 01)
```

Do not modify `inventory/devices.py`, `mock_device_server.py`, `grading.py`, `.env` (pre-created for you — see `.env.example`), or anything under `group_vars/`, `sites/`, `devices/`, `templates/`, or `golden/`.
