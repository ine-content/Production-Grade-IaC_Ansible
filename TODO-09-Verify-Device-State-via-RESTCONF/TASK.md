---
# TODO 09 — Verify Device State via RESTCONF
---

## Topics Covered

```
✓ Never trusting a status code as proof of a real change
✓ A second, independent uri (GET) task
✓ Comparing live device state against the source of truth
```

## Recap

TODO 01 through TODO 08 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 09`.

## Scenario

TODO 08 already made sure a push either succeeds or fails loudly — but "succeeds" so far only means "the device replied with a 200 or 204." Leadership's harder requirement: "No trusting an HTTP 200 as proof that a device actually changed." A device could accept a PATCH, return a perfectly normal success status, and simply never apply it — a firmware bug, a device silently rejecting a change it didn't like, or (in this lab) a mock built specifically to test whether you'd notice. Nothing about `push_result.status` can ever reveal that on its own — only reading the device's live state back independently can.

This only makes sense for devices that were actually pushed to — the 7 production devices are still held for approval and have nothing yet to verify.

## Your Task

Inside `STUDENT WORK AREA - TODO 09` in `site.yml`, write one `ansible.builtin.uri` GET task, followed by one `ansible.builtin.assert`:

```yaml
- name: verify device state via RESTCONF
  when: <...>
  ansible.builtin.uri:
    url: <...>
    method: GET
    url_username: <...>
    url_password: <...>
    force_basic_auth: true
    return_content: true
  register: verify_result

- name: assert the device's live state matches what was pushed
  when: <...>
  ansible.builtin.assert:
    that:
      - <...>
    fail_msg: <...>
    success_msg: <...>
```

Fill in each `<...>`:

```
when (both tasks) - auto_deploy and (push_result.status | default(0)) in [200, 204]
                    (only devices that were actually pushed to have
                    anything to verify)

url             - "http://{{ ansible_host }}:{{ restconf_port }}{{ restconf_path }}"
                  (the exact same URL the push task just used)

url_username    - lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_USERNAME')
url_password    - lookup('env', 'RESTCONF_' ~ environment_name | upper ~ '_PASSWORD')
                  (same as the push task)

assert that:    - verify_result.json.config
                  == lookup('file', playbook_dir + '/output/' + device_id + '.cfg')
```

### Why this has to be a second, separate request

`push_result` only ever tells you what the device *said* in response to the PATCH. It cannot tell you what the device actually did with it afterward - those are two different claims, and only one of them (a fresh GET) is checking the device's actual current state rather than its immediate reply. A device that lies about a PATCH would still make `push_result.status` look completely normal.

### Why the same lookup('file', ...) as the push task

Whatever was actually sent in the PATCH body already went through `lookup('file', playbook_dir + '/output/' + device_id + '.cfg')` in TODO 08's task - and that lookup strips exactly one trailing newline, every time it's used. Reading the same file the same way here means both sides of this comparison went through that stripping exactly once, so a genuinely successful push compares equal without any extra `.rstrip()` gymnastics on your part.

### Hints

`return_content: true` is what makes the response body available to read afterward - without it, `verify_result.json` wouldn't exist. `verify_result.json.config` reaches into the same `{"config": "..."}` shape the mock device always returns from a GET (see `mock_device_server.py`'s `do_GET` if you want to see it directly).

## Where to Write Your Code

Open `site.yml`. Locate `STUDENT WORK AREA - TODO 09`. Write your solution only inside that block — the `debug` task right after it already exists and reports that this device's live state was verified.

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 09 - Verify Device State via RESTCONF
────────────────────────────────────────────────────────────────────────────────

[9] Verifying device state via RESTCONF...

✗ TODO 09 Not Complete

The pipeline cannot continue because a device's live state after a push is not
being independently re-verified via a real GET.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 09 - Verify Device State via RESTCONF
────────────────────────────────────────────────────────────────────────────────

[9] Verifying device state via RESTCONF...
sea03-n9k-01 (mock made to lie) -> caught: live state did not match, task failed as expected
sea03-cat8k-01 (truthful) -> verified: live state matches what was pushed
With no lie injected, both staging devices push and verify correctly.

✓ TODO 09 Complete
Live device state is independently verified after every push - a device that lies
about applying a change is caught, not trusted.
```

The grader configures one staging device's mock to accept every push with a completely normal HTTP 204, while silently never actually storing it — the exact scenario this TODO exists to catch. Unlike every earlier RESTCONF check, this one doesn't send its own GET from outside — it reads the real playbook's own output to confirm *your* verification task caught the lie. A solution that trusts `push_result.status` and skips the independent GET would still show a "successful" push here, and correctly fails this TODO.

---
