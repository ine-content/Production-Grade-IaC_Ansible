# CI/CD Pipeline with Ansible

## This lab is different

There is no Ansible to write. `site.yml` is the exact same playbook built progressively across TODO 01 through TODO 10 of Production-Grade-IaC_Ansible, already complete and correct, plus one small addition: `push_authorized`, a fact that lets a production device be pushed to when this run has been explicitly approved. You only ever run one script yourself: `run_playbook.sh`. It starts the mock device fleet (`mock_device_server.py`) for you in the background, runs `ansible-playbook site.yml` with whatever flags you give it, and shuts the mock fleet back down when it's done. Your task is operational, not coding: push this project to a real GitLab instance and trigger a real, human-approved production deploy. There is no grading script - the lab is complete when it actually happens on GitLab, not when a local check says so.

## Your Task

```
1. Copy .env.example to .env and pick your own username/password for
   each of the four values - there is no built-in default. Without this,
   every RESTCONF request gets a real 401.

2. Add the same four variable names as Protected + Masked GitLab CI/CD
   variables (Settings > CI/CD > Variables), with the values you chose.

3. Push this lab's own repo to GitLab - or open it, if already there.

4. Confirm the automatic "build_and_stage" job goes green - it runs
   `./run_playbook.sh --limit staging`, which starts the mock device
   fleet and pushes and verifies SEA03's 2 staging devices. RDU01/AUS02's
   7 production devices are excluded from this job entirely (--limit),
   and reported as "held for approval, not pushed yet" if you ever run
   the full playbook without --limit.

5. Click Play/Approve on the "deploy_production" job.

6. Wait for it to finish and go green - it runs
   `./run_playbook.sh --limit prod`, this time with
   PRODUCTION_APPROVED=true set by GitLab, which pushes and verifies all
   7 production devices.
```

Full details are in TASK.md.

## Run

```bash
./run_playbook.sh --limit staging
```

This is the only script anyone ever runs directly - it wraps `ansible-playbook site.yml`, forwarding any flags you give it, and manages the mock device fleet's whole lifecycle around that one run. Locally, running it is optional - do it once with `--limit staging` (or no `--limit` at all) for the automatic-stage behavior, then run it again with `PRODUCTION_APPROVED=true ./run_playbook.sh --limit prod` (see TASK.md → "Completion") to simulate the approved production deploy. But the run that actually completes this lab isn't one you type yourself - it's GitLab's own runner executing this same script, inside `build_and_stage` on every pipeline and inside `deploy_production` after you click Approve. Either way, it starts and stops the mock device fleet for you every time - you never touch `mock_device_server.py` directly.

There is no grading script to run afterward. Completion is defined by what happened on your real GitLab instance - see TASK.md → "Completion". If you want to verify it yourself, `logs/audit.jsonl` records every device's real outcome for that run - a production device only shows `"pushed": true` / `"verified": true` once `deploy_production` has actually run with GitLab's own `PRODUCTION_APPROVED=true`.

## The approval gate

`site.yml`'s TODO 08 section computes `push_authorized` for each device: `auto_deploy` (true for staging, false for prod - see `group_vars/`) `or` the `PRODUCTION_APPROVED` environment variable being exactly `"true"`. Nothing in this repo ever sets `PRODUCTION_APPROVED` - it exists only as a variable GitLab itself injects into the `deploy_production` job (`.gitlab-ci.yml`), and that job doesn't run until a human clicks Run on it in the GitLab UI. Approval is enforced twice, independently: once by GitLab's own manual gate (the job doesn't execute at all otherwise), and once inside the playbook itself (a production device's push task is skipped unless `push_authorized` is true, regardless of who or what triggered the run). Either gate alone would be enough; both together mean a bug in one doesn't silently defeat the other.

## Mock device fleet

`mock_device_server.py` reads every `devices/<site_id>.json` file and starts one HTTP listener per device, at that device's own `ip_address:restconf_port`. It's fully dynamic - add a device to an existing site, or an entirely new site (`devices/<new_site>.json` + `sites/<new_site>.json`), and it's served automatically the next time `run_playbook.sh` starts it. Placeholder IPs live in `127.0.0.0/8` (loopback), which is loopback-routable with zero setup on Linux - including every GitLab CI runner.

You never start or stop this script yourself - `run_playbook.sh` does that for you, every run.

**On macOS**, only `127.0.0.1` is loopback by default - binding to any other `127.x.x.x` address fails with `Can't assign requested address`. Run this once first (after each reboot):

```bash
sudo ./setup_local_loopback.sh
```

It reads the exact IPs out of `devices/*.json` and adds each as a loopback alias; it's a no-op on Linux, so it's safe to run either way.

## Inventory

```
Site   Environment  Devices
RDU01  prod         2x CAT8K, 2x Nexus 9K  (4)
AUS02  prod         1x CAT8K, 2x Nexus 9K  (3)
SEA03  staging      1x CAT8K, 1x Nexus 9K  (2)
```

9 devices total across 3 sites - 7 production, 2 staging. `inventory/devices.py` (this course's dynamic inventory plugin) discovers all of this from `devices/*.json` + `sites/*.json`; nothing is hardcoded to this exact mix.

## Offline CI environment

This course's lab VMs have no internet access, so `build_and_stage`/`deploy_production` don't pull a base image or `pip install` anything at runtime - both would need Docker Hub / PyPI, neither reachable from here. They run on `cicd-lab-ansible:latest` instead, a custom image (built from the `Dockerfile` in this folder) with `ansible-core` already baked in.

That image has to already exist in the GitLab Runner host's own local Docker image cache before either job can start; otherwise both jobs fail immediately trying to pull it. This is admin setup, done once by whoever administers the runner - not something a student does, and not something you repeat per run.

```
1. On a machine WITH internet access:
     docker build -t cicd-lab-ansible:latest -f Dockerfile .
     docker save -o cicd-lab-ansible-latest.tar cicd-lab-ansible:latest

2. Move cicd-lab-ansible-latest.tar to the offline GitLab Runner host
   (USB drive, scp over the local network, shared folder - anything that
   doesn't require the offline host itself to reach the internet).

3. On the offline host, load it into the same Docker daemon the runner
   uses, and confirm it's there:
     docker load -i cicd-lab-ansible-latest.tar
     docker images | grep cicd-lab-ansible

4. In that runner's config.toml, under [runners.docker], set:
     pull_policy = "if-not-present"
   This stops the runner from ever trying to re-pull cicd-lab-ansible:latest
   from a registry it can't reach - it uses the image already sitting in
   its local cache instead. Restart the runner after changing config.toml.
```

If a pipeline ever fails with something like "pull access denied" or a DNS/timeout error trying to reach a registry, this is almost always the cause - the image was never loaded onto this particular runner host, or `pull_policy` still defaults to always pulling.

## Credentials

There's no built-in RESTCONF username or password - you pick your own. They're never stored in `group_vars/*.yml` or anywhere else in this repo; set `RESTCONF_PROD_USERNAME`, `RESTCONF_PROD_PASSWORD`, `RESTCONF_STAGING_USERNAME`, and `RESTCONF_STAGING_PASSWORD` as Protected + Masked GitLab CI/CD variables for a real pipeline run, or in a local, git-ignored `.env` file (copy `.env.example`) for a by-hand run.

This isn't just a formality: `mock_device_server.py` reads the exact same four variables and genuinely checks every request's Basic Auth against them. Missing or mismatched credentials get a real `401`, which `site.yml`'s TODO 08 push task treats as a permanent failure - no retry, immediate error. Because `run_playbook.sh` starts the mock fleet itself as a subprocess and sources the same `.env`, both sides always read the same credentials for a given local run - and in CI, both the playbook and the mock fleet process share GitLab's own job environment the same way.

## The files

```
run_playbook.sh          <- the one script anyone runs directly - you, locally
                             (optional testing), or GitLab's runner (real completion).
site.yml                 <- the playbook itself, TODO 02 through TODO 10, plus
                             push_authorized (TODO 08).
mock_device_server.py    <- the mock fleet. Started and stopped by run_playbook.sh only.
inventory/devices.py     <- dynamic inventory, built from devices/ + sites/.
```

## Do not modify

```text
site.yml
mock_device_server.py
run_playbook.sh
setup_local_loopback.sh
inventory/devices.py
intent/
group_vars/
sites/
devices/
templates/
golden/
.gitlab-ci.yml
Dockerfile
```
