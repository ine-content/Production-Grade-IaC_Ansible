---
# TODO 08 — Build, Push, and Retry RESTCONF Configuration
---

## Topics Covered

```
✓ ansible.builtin.uri (HTTP requests from a task)
✓ Basic Auth via url_username / url_password
✓ Reading credentials from the environment with lookup('env', ...)
✓ Gating a task with when:
✓ until: / retries: / delay: (Ansible's built-in retry loop)
✓ failed_when: to defer a module's own pass/fail decision
✓ Distinguishing transient failures from permanent ones
✓ default() as a guard against a missing HTTP response entirely
```

## Recap

TODO 01 through TODO 07 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 08`.

## Scenario

Every artifact has been verified twice (TODO 06) and published idempotently (TODO 07), and is sitting in `output/<device_id>.cfg` — but a config file on disk isn't the same as a config actually running on a device. This TODO delivers it over RESTCONF — but not to every device, and not with a single blind attempt.

`group_vars/staging.yml` already sets `auto_deploy: true`. `group_vars/prod.yml` already sets it `false`. That flag exists for exactly this moment: a real pipeline must never push to production automatically just because the mechanism to do so works. Production changes wait for an explicit human approval step. Within the scope of this progression, that approval step doesn't exist yet — production simply stays held, indefinitely. A real GitLab pipeline's manual approval gate (a later, separate lab) is what actually releases it, gating this exact same push task. This TODO pushes to the 2 staging devices only, and holds the 7 production devices back untouched.

You might expect `ansible.netcommon.restconf_config` here - it's the module built specifically for RESTCONF. It needs an `httpapi` connection plugin, though, and this whole course uses `ansible_connection: local` (see `inventory/devices.py`) - every device here is reached over plain HTTP, with connection details (`ansible_host`, `restconf_port`, `restconf_path`) just sitting in scope as ordinary hostvars, not through a real Ansible connection plugin. `ansible.builtin.uri` is the right tool instead: it ships with `ansible-core` (nothing to install), and RESTCONF, underneath everything else, is just HTTP.

Each staging device's mock RESTCONF endpoint expects:

```
PATCH http://<ansible_host>:<restconf_port><restconf_path>
Authorization: Basic <credentials for this device's own environment>
Content-Type: application/json

{"config": "<the exact text in output/<device_id>.cfg>"}
```

A clean push returns HTTP 204 with an empty body. Credentials are never hardcoded - `.env.example` names them `RESTCONF_PROD_USERNAME` / `RESTCONF_PROD_PASSWORD` and `RESTCONF_STAGING_USERNAME` / `RESTCONF_STAGING_PASSWORD`; this device's own `environment_name` decides which pair applies.

But a real device doesn't only ever return 204. IT leadership's complaint: "Sometimes a push to a device just fails — a momentary network blip, a device that's briefly overloaded — and right now nothing retries it. We lose a valid deployment over something that would have worked one second later. But a network blip is not the same thing as a bad password: if a push fails because of bad credentials, we want the pipeline to stop immediately and tell us, not waste time retrying something that will never succeed." Ansible already has a built-in retry mechanism for exactly this — `until:`/`retries:`/`delay:` on a task. There's no `while` loop or manual backoff math to write by hand here, unlike a hand-rolled Python pipeline. A task with `until:` keeps re-running until that condition is true, or it runs out of retries, whichever comes first. The real job in this TODO isn't just making the push - it's also deciding what "done" means, and retrying only the failures worth retrying.

`until:`/`retries:`/`delay:` have to live directly on the one task making the attempt - a task's own `until:` already re-runs that exact task, so there's no way to "add retry" as a second task layered after a first, plain push; that would mean pushing twice per device instead of retrying once. This is why there's only one `STUDENT WORK AREA` here: one task does the push and the retry together.

## Your Task

Inside `STUDENT WORK AREA - TODO 08` in `site.yml`, write one `ansible.builtin.uri` task shaped like this:

```yaml
- name: push rendered configuration via RESTCONF, retrying transient failures
  when: <...>
  ansible.builtin.uri:
    url: <...>
    method: PATCH
    body_format: json
    body:
      config: <...>
    url_username: <...>
    url_password: <...>
    force_basic_auth: true
    status_code: <...>
  register: push_result
  failed_when: <...>
  until: <...>
  retries: <...>
  delay: <...>
```

Fill in each `<...>`:

```
when            - auto_deploy
                  (already true on staging devices, false on prod - see
                  group_vars/staging.yml and group_vars/prod.yml)

url             - "http://{{ ansible_host }}:{{ restconf_port }}{{ restconf_path }}"
                  (ansible_host, restconf_port, restconf_path are already
                  hostvars - see inventory/devices.py)

body.config     - this device's own rendered artifact, read back as text:
                  lookup('file', playbook_dir + '/output/' + device_id + '.cfg')

url_username    - lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME')
url_password    - lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_PASSWORD')

status_code     - [200, 204, 401, 403, 422, 500, 502, 503, 504]
                  (every status you want to inspect instead of crash on)

failed_when     - false
                  (a task-level keyword - a sibling of register:, until:,
                  retries:, delay: - NOT a parameter nested inside the
                  uri: block itself)

until           - push_result.status | default(0) in [200, 204, 401, 403, 422]

retries         - 3
delay           - 2
```

### Why when: auto_deploy matters here specifically

A task that's skipped (`when:` is false) is Ansible's way of saying "this genuinely never ran" - nothing was sent, nothing was attempted, nothing to roll back. That's exactly the property you want for production: not "the push failed safely," but "the push never happened at all until someone approves it." Leaving `when:` off this task would push to all 9 devices, prod included, the moment this TODO runs - silently defeating the whole point of `auto_deploy` existing.

### Why force_basic_auth and status_code matter

Without `force_basic_auth: true`, `uri` only sends credentials after a server first replies with a 401 challenge - an extra round trip this mock doesn't bother with, so the very first request would come back unauthenticated. `uri`'s default behavior is to treat any status outside 200-299 as an immediate, fatal task failure - fine for a single no-retry attempt, but that default would defeat `until:` before it ever gets a chance to retry. Listing every status you care about in `status_code:`, combined with `failed_when: false` below, turns a non-2xx response into ordinary data (`push_result.status`) for you to make a retry decision about, instead of a crash.

### Why until: stops retrying on 401/403/422

`until:` keeps a task going only while its condition is *false*. Listing `401, 403, 422` alongside the success codes `200, 204` means a permanent error already satisfies the condition on the very first attempt — so it's never retried at all, exactly like a 200/204 wouldn't be. Anything else (a 500, 503, or similar) leaves the condition false, so Ansible tries again, up to `retries` more times, waiting `delay` seconds in between.

### Why default(0) matters

A connection that fails outright — refused, timed out, DNS failure — never gets a real HTTP response at all, so `push_result` has no `.status` key that attempt. Referencing `push_result.status` directly would then be a hard templating error instead of a retry. `default(0)` gives Jinja a safe fallback (an int that isn't in either list) so a totally failed connection attempt is correctly treated as "keep retrying," the same as any other transient failure.

### Hints

`register: push_result` doesn't affect whether this task succeeds - it exists so the guard and report tasks right after it (already written for you) can read `push_result.status`, the actual HTTP status code this device ended up with, only for the staging devices that actually ran the task. `'RESTCONF_' ~ environment_name | upper ~ '_USERNAME'` is Jinja string concatenation (`~`) building the exact env var name `mock_device_server.py` checks against - for a staging device that's `RESTCONF_STAGING_USERNAME`.

## Where to Write Your Code

Open `site.yml`. Locate `STUDENT WORK AREA - TODO 08`. Write your solution only inside that block — everything after it already exists and isn't yours to write: a guard task (an `assert`, gated the same `when: auto_deploy`, checking `push_result is defined`), a `fail` task that fires immediately on a permanent RESTCONF error, a `fail` task that fires if every retry on a transient error was used up without success, and two `debug` tasks - one reporting `push_result.status` and the attempt count for staging devices that got pushed, the other reporting that a production device is being held for approval.

### Running this directly, without `python grading.py`

If you run `./run_playbook.sh` yourself before writing anything, the 2 staging devices genuinely fail on the guard task: `failed=1` in the PLAY RECAP, a non-zero exit code, and a `fatal: [host]: FAILED! => {...}` result carrying the "TODO 08 not complete: ..." message. Without that guard, the failure would instead come from the "exhausted retries" task, with a message that reads exactly like a genuine connection failure - `"last status was no response - connection failed."` - indistinguishable from what a *correct* solution would say if the mock server really were unreachable. The guard fails first instead, with an unambiguous message. The 7 production devices correctly skip everything (`when: auto_deploy` is false for them) and show `skipped`, not `failed` - that's expected, not a sign anything's wrong.

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 08 - Build, Push, and Retry RESTCONF Configuration
────────────────────────────────────────────────────────────────────────────────

[8] Pushing rendered configuration via RESTCONF, with retry (staging only)...

✗ TODO 08 Not Complete

The pipeline cannot continue because staging devices have not been pushed to
correctly, production devices are not being held for approval, or a transient
failure isn't being retried the right number of times.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 08 - Build, Push, and Retry RESTCONF Configuration
────────────────────────────────────────────────────────────────────────────────

[8] Pushing rendered configuration via RESTCONF, with retry (staging only)...
  aus02-cat8k-01 (prod) -> held for approval, GET confirmed nothing was pushed
  ...
  sea03-cat8k-01 (staging, transient 503 x2) -> retried, pushed on the 3rd attempt
  sea03-n9k-01 (staging, permanent 422) -> failed immediately, never retried

✓ TODO 08 Complete
Staging was pushed correctly and production was correctly held back for approval,
and transient RESTCONF failures are retried until they succeed while permanent
failures stop immediately without wasting a single retry.
```

The grader starts the mock device fleet itself, using its own fixed test credentials - you don't need a `.env` file for grading to work, though you'll still want one (it's pre-created for you — see `run_playbook.sh`) if you want to run `python mock_device_server.py` and the playbook yourself, by hand, outside the grader. The check never trusts the playbook's own success message. First it verifies a clean run (no faults injected) purely by independently sending a GET to every device: staging devices must hold the exact content of their own `output/<device_id>.cfg`, and production devices must hold nothing at all - a production device holding any config is graded as a failure exactly as serious as a staging device that never got pushed. Then it makes one staging device fail its first 2 PATCH attempts with a transient 503, and the other always fail with a permanent 422, and checks two more independent things per device: did it end up in the right final state (pushed correctly for the transient device, never pushed for the permanent one), and — straight from the mock fleet's own attempt counter, not anything printed to the terminal — exactly how many times was it actually hit. The transient device must show exactly 3 attempts (2 failures + 1 success); the permanent device must show exactly 1. Getting the right final result with the wrong number of attempts (too few means no real retry happened; too many means a permanent error got retried) still fails this TODO.

---
