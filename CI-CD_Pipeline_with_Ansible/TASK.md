---
# CI/CD Pipeline with Ansible — Production Approval Gate
---

<details>
<summary><strong>Overview</strong></summary>

The IaC solution for Meridian Retail's branch-network has already been built, one TODO at a time, across TODO 01 through TODO 10 of Production-Grade-IaC_Ansible - declarative intent, pre-flight validation, environment- and site-aware render contexts, multi-platform Jinja2 templates, golden-output verification, idempotent publishing, resilient RESTCONF delivery with retry, independent post-push verification, and a structured audit log. It already runs end to end against a mock RESTCONF device fleet:

```
✓ 9 devices across 3 sites (RDU01, AUS02 - prod; SEA03 - staging)
✓ CAT8K routers (OSPF network statements) and Nexus 9K switches (VLAN database)
✓ One playbook (site.yml): loads, validates, renders, verifies, publishes,
  pushes, and verifies again over RESTCONF - staging only, automatically
✓ A permanent, structured audit record of every device's outcome
```

The one thing that playbook never does on its own is touch production - on purpose. That's this lab's job: **test Meridian's production sites by approving a real deploy and pushing configuration to RDU01 and AUS02's 7 production devices, on your real GitLab instance.**

There is no Ansible to write. Every task in `site.yml` is already complete and correct - your task is operational, not coding.

</details>

---

<details>
<summary><strong>Final Pipeline</strong></summary>

```
Load the Declarative Service Intent
        ↓
Pre-Flight Validation
        ↓
Environment- and Site-Aware Render Context
        ↓
Render CAT8K and Nexus Artifacts, Per Device
        ↓
Post-Render Correctness Verification
        ↓
Idempotent Local Publish
        ↓
Push and Verify Staging Devices via RESTCONF, with Retry (automatic)
        ↓
Structured Audit Log
        ↓
Manual CI/CD Production-Approval Gate (PRODUCTION_APPROVED=true)
        ↓
Push and Verify Production Devices via RESTCONF (only after approval)
        ↓
Structured Audit Log (production devices)
```

Every stage is the same TODO 02 through TODO 10 task you already saw pass in Production-Grade-IaC_Ansible - see `site.yml`'s own `# TODO N -` banners if you want to read how it works. The only new logic in this lab is `push_authorized`, just above TODO 08's push task - see that comment for exactly how a production device becomes pushable.

</details>

---

<details>
<summary><strong>Lab Files</strong></summary>

This lab is its own standalone repo/folder. Run all commands from inside it.

```
CI-CD_Pipeline_with_Ansible/        (this lab - its own repo root)
├── .gitlab-ci.yml           (already complete - runs run_playbook.sh for you)
├── Dockerfile               (builds this lab's offline CI image - admin use)
├── site.yml                 (the one playbook - already complete and correct)
├── intent/retail_branch_service.yml
├── group_vars/{prod,staging}.yml       (no credentials - see .env.example)
├── sites/{rdu01,aus02,sea03}.json
├── devices/{rdu01,aus02,sea03}.json
├── templates/{cat8k_ospf,nexus_vlan}.j2
├── golden/{rdu01,aus02,sea03}/*.cfg
├── inventory/devices.py      (dynamic inventory - reads devices/, sites/)
├── output/ , logs/
├── mock_device_server.py
├── run_playbook.sh            (the one script anyone runs directly)
├── setup_local_loopback.sh    (macOS only)
├── .gitignore, .env.example
├── TASK.md, README.md
```

Do not modify: `site.yml`, `mock_device_server.py`, `run_playbook.sh`, `setup_local_loopback.sh`, `inventory/devices.py`, `intent/`, `group_vars/`, `sites/`, `devices/`, `templates/`, `golden/`, `.gitlab-ci.yml`, `Dockerfile`.

</details>

---

<details>
<summary><strong>Your Task</strong></summary>

```
1. VPN to the EVE-NG machine. Verify ping to 10.10.10.250 works.
   Navigate to this lab's folder. Copy .env.example to .env.

2. In .env, set the username to api and the password to api (all four
   RESTCONF credential values).

3. Point this repo at your GitLab project:

     cd CI-CD_Pipeline_with_Ansible
     git add .
     git commit -m "Initial Commit"
     git remote add origin http://10.10.10.250:8929/ine/ci-cd_pipeline_with_ansible.git

4. Open the GitLab repository in your local Chrome browser:
   http://10.10.10.250:8929/ine/ci-cd_pipeline_with_ansible

5. Add the same four variable names from .env as CI/CD variables -
   Settings > CI/CD > Variables, marked Protected but NOT Masked,
   values api / api (GitLab won't even let you mask a value this
   short anyway).

6. Create a Personal Access Token (write_repository scope) - avatar >
   Edit profile > Access Tokens.

7. Push:

     git push -u origin main

   When prompted, use username expert and the token as the password.

8. Verify the stages: confirm "build_and_stage" goes green, review its
   log (every staging device pushed and verified, every production
   device reported as "held for approval, not pushed yet"), then approve
   the prod sites - click Run (the Play icon) on "deploy_production" and
   confirm it goes green too. "deploy_production" sits blocked behind
   that manual Run button until you click it - that click is the
   approval, even though the button doesn't literally say "Approve."
```

That's it - once both jobs are green, and `deploy_production` only ran because you clicked Run, the lab is done. See "Completion" at the bottom.

</details>

---

# Completion

The lab is complete when, on your real GitLab instance:

```
1. The automatic "build_and_stage" job has run and is green.
2. You clicked Run on "deploy_production" yourself, and it is green too.
```

There is no grading script - a local check can always be satisfied by running something locally, which is exactly the loophole this lab is designed to close. If you want to verify it yourself, pull the job's `logs/` artifact and open `logs/audit.jsonl` - every production device's line should show `"pushed": true` and `"verified": true` only after `deploy_production` has actually run; a `build_and_stage`-only run's `audit.jsonl` shows every production device with `"pushed": false`, `"push_status": null`, `"verified": false` instead, because `push_authorized` (site.yml, TODO 08) was never true for them in that job.

---
