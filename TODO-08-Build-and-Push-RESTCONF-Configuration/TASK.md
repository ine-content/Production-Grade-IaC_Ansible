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

Every artifact is verified (TODO 06), published idempotently (TODO 07), and sitting in `output/<device_id>.cfg` - but a file on disk isn't a config running on a device. This TODO pushes it over RESTCONF, to staging only, with retries.

`group_vars/staging.yml` sets `auto_deploy: true`; `group_vars/prod.yml` sets it `false`. Production stays held back indefinitely within this progression - a real approval gate (a later, separate lab) is what would release it. This TODO pushes to the 2 staging devices only.

Use `ansible.builtin.uri`, not `ansible.netcommon.restconf_config` - that module needs an `httpapi` connection plugin, and this course uses `ansible_connection: local` throughout (see `inventory/devices.py`). `uri` ships with `ansible-core`, and RESTCONF is just HTTP underneath.

Each staging device's mock RESTCONF endpoint expects:

```
PATCH http://<ansible_host>:<restconf_port><restconf_path>
Authorization: Basic <credentials for this device's own environment>
Content-Type: application/json

{"config": "<the exact text in output/<device_id>.cfg>"}
```

A clean push returns HTTP 204. Credentials come from `.env.example`'s `RESTCONF_PROD_USERNAME`/`_PASSWORD` and `RESTCONF_STAGING_USERNAME`/`_PASSWORD` - never hardcoded; this device's own `environment_name` picks the pair.

A push can also fail - a momentary blip should retry; bad credentials should stop immediately, not waste retries on something that will never succeed. `until:`/`retries:`/`delay:` on the task is Ansible's built-in retry loop for exactly this - no hand-rolled backoff needed. Since `until:` re-runs the same task, retry has to live on the one push task itself, not a second task after it - which is why there's only one `STUDENT WORK AREA` here.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 08. Write your
   solution only inside that block - everything after it already
   exists and isn't yours to write: a guard task (an assert, gated
   the same when: auto_deploy, checking push_result is defined), a
   fail task that fires immediately on a permanent RESTCONF error, a
   fail task that fires if every retry on a transient error was used
   up without success, and two debug tasks - one reporting
   push_result.status and the attempt count for staging devices that
   got pushed, the other reporting that a production device is being
   held for approval.

2. Add one ansible.builtin.uri task:

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

3. Fill in each <...>:

     when            - auto_deploy
                       (already true on staging devices, false on prod
                       - see group_vars/staging.yml and group_vars/prod.yml)

     url             - "http://{{ ansible_host }}:{{ restconf_port }}{{ restconf_path }}"
                       (ansible_host, restconf_port, restconf_path are
                       already hostvars - see inventory/devices.py)

     body.config     - this device's own rendered artifact, read back
                       as text: lookup('file', playbook_dir + '/output/' + device_id + '.cfg')

     url_username    - lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME')
     url_password    - lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_PASSWORD')

     status_code     - [200, 204, 401, 403, 422, 500, 502, 503, 504]
                       (every status you want to inspect instead of crash on)

     failed_when     - false
                       (a task-level keyword - a sibling of register:,
                       until:, retries:, delay: - NOT a parameter
                       nested inside the uri: block itself)

     until           - push_result.status | default(0) in [200, 204, 401, 403, 422]

     retries         - 3
     delay           - 2

Note: why each of these matters -

   when: think of it as a gate. A skipped task is like a delivery
   truck that never left the warehouse - nothing was sent, nothing to
   undo. That's what you want for production: not "we tried and it
   failed safely," but "we didn't try at all until a human said yes."
   Without this gate, the task would push to all 9 devices, prod
   included, the moment you save the file.

   force_basic_auth and status_code - two separate problems: (1)
   normally uri waits to be challenged with a 401 before sending
   credentials, but this mock doesn't bother with that handshake - it
   just rejects you if they weren't there on the first try, so
   force_basic_auth: true sends them upfront. (2) by default uri
   treats anything that isn't 2xx as an instant crash, before your
   retry logic ever gets a turn - listing every status you expect in
   status_code: (plus failed_when: false) says "don't crash on these,
   just hand me the result and let me decide."

   until: worded backwards from how you'd guess - it means "keep
   retrying until this becomes true." List every status that means
   "we're done": the successes (200, 204) and the errors retrying can
   never fix (401, 403, 422 - bad password, bad data). Get one of
   those on attempt 1 and you're already done, so it stops
   immediately. Anything else (500, 503, a timeout) isn't on that
   list, so it keeps trying - up to retries times, delay seconds
   apart.

   default(0): if the connection fails outright (server down,
   timeout, wrong address), there's no HTTP response at all, so
   push_result.status doesn't even exist yet. Asking for .status when
   it's missing would crash the playbook instead of letting your
   retry logic handle it. default(0) just says "if there's no status,
   pretend it's 0" - a number that isn't in your success/permanent-
   error list, so it's treated like any other "try again" case.

   register and the credential lookup: register: push_result doesn't
   affect pass/fail at all - it just saves the result so the tasks
   after this one can read push_result.status and report what
   happened. 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME' is
   just string-gluing - for a staging device it builds the literal
   text RESTCONF_STAGING_USERNAME, the exact env var name holding
   that device's password.

4. Save, then run: python grading.py
   (Running ./run_playbook.sh directly first, before writing anything,
   the 2 staging devices fail on the guard task with "TODO 08 not
   complete: ..." - an unambiguous message, distinct from what the
   "exhausted retries" task would otherwise say ("last status was no
   response - connection failed."), which reads exactly like what a
   CORRECT solution says if the mock server were genuinely
   unreachable. The 7 production devices correctly show skipped, not
   failed - when: auto_deploy is false for them, and that's expected.)
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 08 - Build, Push, and Retry RESTCONF Configuration
────────────────────────────────────────────────────────────────────────────────

[8] Pushing rendered configuration via RESTCONF, with retry (staging only)...
  sea03-cat8k-01, sea03-n9k-01: should have been pushed, but holds no config at all - nothing was ever pushed.

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
  sea03-cat8k-01 (staging) -> pushed, GET confirmed the device now holds it
  sea03-n9k-01 (staging) -> pushed, GET confirmed the device now holds it
Fault injection: a transient 503 was retried until it succeeded (3 attempts); a permanent 422 failed immediately and was never retried (1 attempt).

✓ TODO 08 Complete
Staging was pushed correctly and production was correctly held back for approval,
and transient RESTCONF failures are retried until they succeed while permanent
failures stop immediately without wasting a single retry.
```

The grader starts the mock device fleet itself, using its own fixed test credentials - you don't need a `.env` file for grading to work, though you'll still want one (it's pre-created for you — see `run_playbook.sh`) if you want to run `python mock_device_server.py` and the playbook yourself, by hand, outside the grader. The check never trusts the playbook's own success message. First it verifies a clean run (no faults injected) purely by independently sending a GET to every device: staging devices must hold the exact content of their own `output/<device_id>.cfg`, and production devices must hold nothing at all - a production device holding any config is graded as a failure exactly as serious as a staging device that never got pushed. Then it makes one staging device fail its first 2 PATCH attempts with a transient 503, and the other always fail with a permanent 422, and checks two more independent things per device: did it end up in the right final state (pushed correctly for the transient device, never pushed for the permanent one), and — straight from the mock fleet's own attempt counter, not anything printed to the terminal — exactly how many times was it actually hit. The transient device must show exactly 3 attempts (2 failures + 1 success); the permanent device must show exactly 1. Getting the right final result with the wrong number of attempts (too few means no real retry happened; too many means a permanent error got retried) still fails this TODO.

---
