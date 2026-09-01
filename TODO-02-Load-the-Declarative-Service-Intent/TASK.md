---
# TODO 02 — Load the Declarative Service Intent
---

## Topics Covered

```
✓ Dynamic Inventory
✓ Ansible Variable Precedence (group_vars vs. explicit loading)
```

## Recap

TODO 01 is already done for you in this folder — `intent/retail_branch_service.yml` is the correct, finished answer, so you can focus on this TODO. `site.yml` is the one playbook this whole course builds, one TODO at a time; open it and find `STUDENT WORK AREA - TODO 02`.

## What's Already Loaded, With Zero Code From You

Run this yourself before writing anything:

```
ansible-inventory -i inventory/devices.py --list
```

Every device already has `device_id`, `site_id`, `platform`, `hostname`, `restconf_port`, `restconf_path`, `region`, `environment_name`, and `resolved_vlans` — built by `inventory/devices.py` from `devices/*.json` + `sites/*.json`. Every device is also already carrying the right policy from `group_vars/prod.yml` or `group_vars/staging.yml`, because Ansible loads `group_vars/<name>.yml` automatically for every host in a group named `<name>`, and the dynamic inventory already put each device into a `prod` or `staging` group.

None of that is what this TODO is about. It's already done — that's the point of dynamic inventory.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 02. Write your
   solution only inside that block - the two tasks right after it
   already exist and aren't yours to write: a guard assert that fails
   with "TODO 02 not complete: ..." if service_intent was never
   loaded, and a debug task that reports service_intent,
   environment_name, and resolved_vlans once it is.

2. intent/retail_branch_service.yml is the one input NOT loaded
   automatically - it isn't a group_vars/host_vars file, so nothing
   points Ansible at it on its own. Use the include_vars module to
   load it into a variable named service_intent, so that
   service_intent.tenant, service_intent.service, and
   service_intent.vlans are all available afterward.

3. There is no separate "parse" step to write. include_vars does both
   in one move - Ansible variables are just nested dicts and lists, so
   the moment it reads the YAML, that structure already IS the parsed
   result (service_intent.vlans is already a real list with real
   .role/.name/.enabled fields on each entry). This is the real
   contrast with the Python course, not just a renamed step: there,
   load_json() returned a raw dict, and a separate
   parse_service_intent() function hand-built a typed ServiceIntent
   dataclass field-by-field. Ansible has no equivalent "convert a raw
   dict into a typed object" step, because it has no static types to
   convert into.

4. Save, then run: python grading.py
   (Running ./run_playbook.sh directly first, before writing anything,
   fails the same way - the guard assert stops every device with
   "TODO 02 not complete: ...", failed=1 in the PLAY RECAP, non-zero
   exit code. Depending on your Ansible version you may also see an
   "[ERROR]: Task failed: Action failed" callout above that - that's
   newer ansible-core's own extra diagnostic context for any failed
   task, not a second problem.)
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 02 - Load the Declarative Service Intent
────────────────────────────────────────────────────────────────────────────────

[2] Loading the declarative service intent...

✗ TODO 02 Not Complete

The pipeline cannot continue because structured inputs have not been loaded and
parsed yet.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 02 - Load the Declarative Service Intent
────────────────────────────────────────────────────────────────────────────────

[2] Loading the declarative service intent...

✓ TODO 02 Complete
service_intent was loaded correctly and is visible, correctly resolved, on every
one of the 9 devices.
```

---
