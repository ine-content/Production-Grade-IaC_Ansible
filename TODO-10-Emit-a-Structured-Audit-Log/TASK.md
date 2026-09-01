---
# TODO 10 — Emit a Structured Audit Log
---

## Topics Covered

```
✓ Structured, permanent logging from an ephemeral run
✓ Building and serializing a dict in one Jinja pass
✓ Safe concurrent file appends without cross-host coordination
```

## Recap

TODO 01 through TODO 09 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 10`. This is the last TODO in the course.

## Scenario

This run has authored, loaded, validated, rendered, verified, published, pushed, and verified again (TODO 02 through TODO 09) — but every bit of that so far only exists as scrollback in a terminal that disappears the moment the window closes. Compliance and IT leadership have said: "When someone asks us three weeks from now which devices were actually touched during a given rollout, we can't just say we don't know because the terminal window closed. Every run needs to leave a permanent, structured record of what happened — what was pushed, what was held back, and what was independently verified — that we can search and audit later."

### Why this looks different from Python's version of this same lesson

Python's version of this course runs as one process for the whole fleet, so it builds one dict describing every device's outcome and writes it out once, right at the end. This course's playbook instead runs each device as its own independent host loop iteration — by the time this task runs, this device already knows its own final outcome (`push_result`, `verify_result`, `auto_deploy`), but has no way to see any other device's outcome, and doesn't need to: each device just appends its own one-line JSON record to one shared file, `logs/audit.jsonl`, with no coordination between hosts required.

### Why this task reaches for `ansible.builtin.shell`

That "no coordination required" claim only holds if the append itself is actually safe to run from several hosts at once — and this playbook does run several devices in parallel, not one at a time. A module like `ansible.builtin.lineinfile` reads the whole file, decides what to add, and rewrites the whole file. Two hosts doing that at the same instant can each read the same starting content, and whichever one writes second silently overwrites the first host's line — a lost update, not an error either host would ever see.

Appending with a shell redirect (`>>`) is different: POSIX guarantees that a single `write()` to a file opened for append is atomic as long as it's smaller than the system's `PIPE_BUF` (4KB on Linux). One line of JSON is always well under that, so every device's line lands intact, in whatever order the writes happen to land in, with nothing lost and nothing interleaved. That's the one and only reason this task uses `ansible.builtin.shell` instead of a normal declarative file module — it's not "shell scripting for its own sake," it's the one primitive here that's actually safe under real concurrency.

### The subtlety that will bite you if you don't know about it

Ansible templates a task's `vars:` one field at a time. If you build a YAML dict of separate fields first —

```yaml
vars:
  pushed: "{{ (auto_deploy and push_result.status in [200, 204]) | bool }}"
  push_status: "{{ push_result.status | default(none) }}"
```

— and only combine them into one dict and run it through `| to_json` in a later step, every field has already been flattened to plain text by the time `to_json` ever sees it: `true` becomes the four-character string `"True"`, not JSON's bare `true`, and a missing status becomes an empty string instead of JSON `null`. `to_json` can only emit real JSON types for values that are still real Python types at the moment it runs.

The fix: build the dict **and** call `| to_json` inside the very same `{{ ... }}` expression, in one pass. That keeps every value a real Python `bool`/`int`/`None` right up until the instant it's serialized, so `to_json` emits `true`, `204`, and `null` the way a real audit consumer expects — not the strings `"True"`, `"204"`, `"None"`.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 10. Write your
   solution only inside that block - the guard task right after it (an
   assert checking audit_result is defined) and the debug task after
   that already exist and aren't yours to write.

2. Add one ansible.builtin.shell task:

     - name: append this device's audit record to the shared audit log
       vars:
         audit_line: <...>
       ansible.builtin.shell: <...>
       register: audit_result

3. Fill in each <...>:

     audit_line - one {{ ... }} | to_json expression, built from a
                  single Jinja dict literal with exactly these 7 keys:

                    device_id     - device_id
                    platform      - platform
                    site_id       - site_id
                    environment   - environment_name
                    pushed        - auto_deploy and (push_result.status | default(0)) in [200, 204]
                    push_status   - push_result.status | default(none)
                    verified      - auto_deploy and (push_result.status | default(0)) in [200, 204]

                  pushed and verified are the same expression here on
                  purpose: by the time this task runs, TODO 09's own
                  assert has already stopped this host if a push had
                  succeeded but verification then failed - so if
                  execution reaches this task at all, a successful
                  push always means a verified one.

     ansible.builtin.shell -
                  printf '%s\n' {{ audit_line | quote }} >> {{ playbook_dir }}/logs/audit.jsonl

     register:  - audit_result   <- required. The guard task right
                  after this block checks for it - without it, a
                  blank TODO 10 would fall straight through to the
                  "report the audit record" task and print a success
                  message even though nothing was ever appended.

4. Why | quote: audit_line is a JSON string, completely full of double
   quotes and colons - exactly the characters that would otherwise
   confuse the shell parsing this command. The quote filter (a thin
   wrapper around Python's shlex.quote) wraps the whole string in
   single quotes and escapes anything inside it that needs escaping,
   so it survives the trip through the shell as one literal argument.

5. push_result is already register:-ed by TODO 08's task for every
   device, whether or not auto_deploy was true for it - a production
   device just has a push_result describing a SKIPPED task instead of
   a real HTTP response, which is why push_result.status | default(0)
   is the right way to read it everywhere in this playbook. A dict
   literal inside {{ ... }} uses normal Python/Jinja syntax:
   {'key': value, 'key2': value2} - single-quoted keys, no
   key: value YAML-style colons-without-quotes, since this is Jinja,
   not YAML, once you're inside the {{ }}.

6. Save, then run: python grading.py
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 10 - Emit a Structured Audit Log
────────────────────────────────────────────────────────────────────────────────

[10] Emitting a structured audit log...

✗ TODO 10 Not Complete

The pipeline cannot complete because a correct, permanent audit record was not
appended to logs/audit.jsonl for every device.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 10 - Emit a Structured Audit Log
────────────────────────────────────────────────────────────────────────────────

[10] Emitting a structured audit log...
  aus02-cat8k-01 (prod) -> pushed: false, push_status: null, verified: false
  aus02-n9k-01 (prod) -> pushed: false, push_status: null, verified: false
  aus02-n9k-02 (prod) -> pushed: false, push_status: null, verified: false
  rdu01-cat8k-01 (prod) -> pushed: false, push_status: null, verified: false
  rdu01-cat8k-02 (prod) -> pushed: false, push_status: null, verified: false
  rdu01-n9k-01 (prod) -> pushed: false, push_status: null, verified: false
  rdu01-n9k-02 (prod) -> pushed: false, push_status: null, verified: false
  sea03-cat8k-01 (staging) -> pushed: true, push_status: 204, verified: true
  sea03-n9k-01 (staging) -> pushed: true, push_status: 204, verified: true
logs/audit.jsonl has exactly one correct line per device.

✓ TODO 10 Complete
Every device appended a correct, permanent audit record to logs/audit.jsonl -
pushed, held, and verified outcomes are now on the record, not just in a
terminal that already closed.
```

The grader deletes any existing `logs/audit.jsonl` first, runs one final clean pass with nothing faked, then reads the file back directly with `json.loads()` on every line — never by matching text in the playbook's own stdout. A solution that writes `"true"`/`"204"`/`"None"` as plain strings round-trips through `json.loads()` as those exact strings, which fails the comparison against the real values `True`/`204`/`None` just as loudly as a missing line would.

---

# Course Complete

If `python grading.py` shows all 10 TODOs passing, this course is done. This playbook now authors, loads, validates, renders, verifies, publishes, pushes, retries, verifies again, and audits itself — for every device, every run, with nothing hand-waved and nothing trusted that wasn't independently checked.

One thing this course's 10 labs deliberately never build: a way to actually let a production device go live. `auto_deploy: false` in `group_vars/prod.yml` holds every one of the 7 production devices back, indefinitely, on every run in this course — on purpose. That's not a missing feature to fix here. A real production release for Meridian Retail's branch network goes through an actual change-control gate — a GitLab pipeline's manual approval job, sitting in front of the exact same push task this course already built — not a local flag any one engineer can flip alone. That's the next lab.
