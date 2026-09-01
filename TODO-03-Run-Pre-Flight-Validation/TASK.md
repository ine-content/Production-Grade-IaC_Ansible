---
# TODO 03 — Run Pre-Flight Validation
---

## Topics Covered

```
✓ Correctness Before Rendering
✓ Referential Integrity
```

## Recap

TODO 01 and TODO 02 are already solved in this folder — the intent file is correct, and `site.yml` already loads it into `service_intent`. Open `site.yml` and find `STUDENT WORK AREA - TODO 03`.

## Scenario

Now that everything is loaded (TODO 02), nothing has actually confirmed it's correct yet. A file can be perfectly well-formed YAML and still be wrong.

Network Engineering has said: "We've had an environment file disable a VLAN role that didn't even exist — a typo, 'gust' instead of 'guest'. It didn't do anything, silently, and nobody noticed until a site that should have had guest wifi didn't. We want every cross-file reference checked before the pipeline renders or pushes anything."

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 03. Write your
   solution only inside that block - the guard task right after it (an
   assert checking preflight_result is defined) and the debug task
   after that already exist and aren't yours to write.

2. Add one ansible.builtin.assert task with:
     that:        one condition - true when every role in disabled_roles
                  also appears among service_intent.vlans' roles
     fail_msg:    names the failing device ({{ inventory_hostname }})
     success_msg: names the passing device
     register:    preflight_result   <- required. The guard task right
                  after this block checks for it - without it, a blank
                  TODO 03 would fall straight through to the "report
                  what was loaded" task and print "Pre-flight
                  validation passed." even though nothing was checked.

3. Build the condition with Jinja's difference filter:
     disabled_roles | difference(<all valid roles>) | length == 0
   difference() returns items in the first list NOT found in the
   second - 0 leftover items means every disabled role was valid. This
   is the referential-integrity check - exactly what catches an
   environment disabling a VLAN role that was never actually defined
   in the intent, the "gust" vs. "guest" typo from the scenario above.

4. Save, then run: python grading.py
```

### Running this directly, without `python grading.py`

If you run `./run_playbook.sh` yourself before writing anything, every device genuinely fails on that guard task: `failed=1` in the PLAY RECAP, a non-zero exit code, and a `fatal: [host]: FAILED! => {...}` result carrying the "TODO 03 not complete: ..." message. If your own assert task runs and fails one of its conditions, the guard is never even reached - your own `fail_msg` is what stops the host, exactly as it should.

## Important

The grader intentionally breaks `group_vars/staging.yml` (adds a disabled role that doesn't exist in the intent) before checking this TODO, to make sure your validation is actually being executed and not just present as a no-op. It restores the file afterward either way.

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 03 - Run Pre-Flight Validation
────────────────────────────────────────────────────────────────────────────────

[3] Running pre-flight validation...

✗ TODO 03 Not Complete

The pipeline cannot continue because pre-flight validation is not actually being
executed.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 03 - Run Pre-Flight Validation
────────────────────────────────────────────────────────────────────────────────

[3] Running pre-flight validation...

✓ TODO 03 Complete
Pre-flight validation is running and correctly catches a bad cross-file
reference.
```

---
