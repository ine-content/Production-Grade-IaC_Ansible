---
# TODO 01 — Author the Declarative Service Intent
---

<details>
<summary><strong>Overview</strong></summary>

This course combines the major concepts of production-grade Infrastructure as Code, built entirely with Ansible:

```
✓ Declarative Authoring
✓ Dynamic Inventory
✓ Pre-Flight Validation
✓ Environment-Aware Policy Overrides
✓ Golden-Output Regression Testing
✓ Idempotent Publishing
✓ Structured Logging
```

The goal is not to write a large playbook. The goal is to engineer an automation pipeline that is safe to run in production, repeatedly, without supervision — starting from nothing but a business requirement.

There is no Terraform anywhere in this course. There is no hand-written Python pipeline either. Everything is pure Ansible.

</details>

---

<details>
<summary><strong>Business Scenario</strong></summary>

```
- Meridian Retail standardized its branch network configs using a one-off script with no verification step. During a routine rollout, a template change silently altered VLANs at a live site. Nobody caught it until the outage ticket came in.

- Leadership has mandated a production-grade replacement:

  • No ad hoc scripts
  • No hand-waved requirements — the intent must be written down
  • No unverified output
  • No silent rewrites of unchanged infrastructure
  • Every run must prove its own correctness, before AND after render
  • No automatic pushes to production devices without change control
  • No trusting an HTTP 200 as proof that a device actually changed

- The service must be rendered — and, for staging, actually pushed to a live device fleet over RESTCONF — across 3 branch sites:
  • RDU01  (Raleigh   - prod)
  • AUS02  (Austin    - prod)
  • SEA03  (Seattle   - staging, newly onboarding)

- Unlike a fixed one-router-one-switch-per-site model, each site has its own real fleet — RDU01 alone has 2 CAT8Ks and 2 Nexus 9Ks. Devices are never hardcoded: add a new device to devices/<site_id>.json and Ansible's dynamic inventory (inventory/devices.py) picks it up automatically, with no other change needed.

- The target platforms are:
  • Cisco CAT8K   - a router. It has no VLAN database of its own, so it renders an OSPF network statement per VLAN subnet instead.
  • Cisco Nexus 9K - a switch. It creates a VLAN database entry for each VLAN, as a switch normally would.

- Store Operations and Network Engineering have agreed on the VLANs the service needs. Nobody has written that agreement down as a real, loadable artifact yet. That is your first job.

- There is no real Cisco hardware available for this lab. A mock RESTCONF device fleet stands in for it — from a playbook's point of view, it is indistinguishable from a real device's RESTCONF API.

- You are provided:
  • Environment policy (group_vars/prod.yml, group_vars/staging.yml — disabled_roles and auto_deploy per environment)
  • Site files (sites/*.json — region, environment, per-site VLAN IDs)
  • Device files (devices/*.json — every device at every site)
  • A dynamic inventory script (inventory/devices.py) that turns the above into Ansible groups and host vars automatically
  • Two Jinja2 templates
  • A golden/ directory of known-good reference artifacts
  • A prebuilt mock RESTCONF device fleet (mock_device_server.py)
  • A milestone-based grader

- You are NOT provided the declarative service intent. You write it yourself, from the requirements below, before anything else can run.
```

</details>

---

<details>
<summary><strong>Final Pipeline</strong></summary>

```
Author Declarative Intent
        ↓
Load the Declarative Service Intent
        ↓
Pre-Flight Validation
        ↓
Environment- and Site-Aware Render Facts
        ↓
Render CAT8K and Nexus Artifacts, Per Device
        ↓
Post-Render Correctness Verification
        ↓
Idempotent Local Publish
        ↓
Build, Push, and Retry RESTCONF Configuration
        ↓
Verify Device State via RESTCONF
        ↓
Structured Audit Log
```

Each stage becomes one lesson (TODO 02 through TODO 10), always written as native Ansible — tasks, `assert`, `template`, `uri`, `retries`/`until` — never a hand-rolled Python equivalent of what Ansible already does for you.

</details>

---

<details>
<summary><strong>Lab Files</strong></summary>

Run all commands from this lab's own directory.

```
TODO-01-Author-the-Declarative-Service-Intent/
├── intent/
│   └── (empty — you create retail_branch_service.yml here, TODO 01)
├── group_vars/
│   ├── prod.yml           (disabled_roles, auto_deploy — no credentials)
│   └── staging.yml         (disabled_roles, auto_deploy — no credentials)
├── sites/{rdu01,aus02,sea03}.json
├── devices/{rdu01,aus02,sea03}.json
├── inventory/devices.py    (dynamic inventory — builds groups + hostvars from devices/ + sites/)
├── templates/{cat8k_ospf,nexus_vlan}.j2
├── golden/{rdu01,aus02,sea03}/*.cfg
├── output/ , logs/
├── mock_device_server.py
├── setup_local_loopback.sh (macOS only — see the script's own header)
├── .env.example, .gitignore
├── grading.py
├── TASK.md, README.md
```

You will create:

```
intent/retail_branch_service.yml
```

Do not modify:

```
group_vars/
sites/
devices/
inventory/devices.py
templates/
golden/
mock_device_server.py
grading.py
```

</details>

---

<details>
<summary><strong>How This Lab Works</strong></summary>

There is no playbook to run yet — this TODO has no code, only a file to author by hand. Later TODOs (2 through 10) introduce a playbook one stage at a time; the grader runs each stage for you.

</details>

---

<details>
<summary><strong>Run the grader</strong></summary>

```
python grading.py
```

Note: TODO 01 is checked directly by reading the YAML file you create — the grader does not need anything else running to check it, because there is nothing to run until the intent file exists.

</details>

---

# TODO 01 — Author the Declarative Service Intent

## Topics Covered

```
✓ Declarative Authoring
✓ Structured Data Modeling in YAML
```

## Business Requirements

```
- Store Operations and Network Engineering have agreed on the following requirements for the standard branch network service:
  - Tenant:              Meridian Retail

  - Service identifier:  branch-network-standard

  - A dedicated VLAN for corporate user devices.
        role: users   name: RTL-USERS   enabled: true

  - A dedicated VLAN for VoIP handsets.
        role: voice   name: RTL-VOICE   enabled: true

  - A dedicated VLAN for corporate wifi.
        role: wifi    name: RTL-WIFI    enabled: true

  - A dedicated VLAN for guest wifi. Approved at the intent level — individual environments may still restrict it locally.
        role: guest   name: RTL-GUEST   enabled: true

  - A placeholder VLAN reserved for future use. Not yet approved.
        role: unused  name: UNUSED      enabled: false
```

## Scenario

This is the very first step in the whole pipeline. Nothing has been inventoried, checked, rendered, or pushed yet, because nothing has even been written down yet.

Store Operations and Network Engineering have said: "We've agreed on the VLANs we need, but right now that agreement only exists in a meeting and a Slack thread — nothing a computer can actually read. Before any automation touches a single device, we want that agreement written down as a real file the system can load and trust."

## Steps

```
1. Create the file: intent/retail_branch_service.yml
   There is no code for this TODO - this is the only file you write.

2. Shape it exactly like this:
     tenant: "<string>"
     service: "<string>"
     vlans:
       - role: "<string>"
         name: "<string>"
         enabled: true

3. Add one vlans entry per VLAN in the Business Requirements above, in
   any order, using the exact role, name, and enabled values given
   there. vlans is a list.

4. Save, then run: python grading.py
```

## Grading Check

Run the grader. The grader reads this file directly — it does not need to run anything to check it.

Before you complete this TODO, running the grader shows:

```
TODO 01 - Author the Declarative Service Intent
────────────────────────────────────────────────────────────────────────────────

[1] Authoring the declarative service intent...

✗ TODO 01 Not Complete

The pipeline cannot continue because the declarative service intent has not been
authored correctly yet.

Proceeding to detailed feedback...
```

After you complete it correctly, the grader shows:

```
TODO 01 - Author the Declarative Service Intent
────────────────────────────────────────────────────────────────────────────────

[1] Authoring the declarative service intent...
intent/retail_branch_service.yml matches the required business requirements.

✓ TODO 01 Complete
intent/retail_branch_service.yml captures the business requirements correctly.
```

---
