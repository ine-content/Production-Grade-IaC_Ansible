---
# TODO 06 — Run Post-Render Correctness Verification
---

## Topics Covered

```
✓ Golden-Output Regression Testing
✓ Independent Policy Re-Checking
✓ The Jinja `in` Test as Substring Containment
```

## Recap

TODO 01 through TODO 05 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 06`.

## Scenario

Meridian Retail standardized its branch network configs using a one-off script with no verification step. During a routine rollout, a template change silently altered VLANs at a live site. Nobody caught it until the outage ticket came in.

Leadership's mandate: "The last outage happened because a config rendered without any errors, but it was still wrong, and nobody double-checked the actual output before it went out. We're mandating that nothing gets published or pushed to a device again without independent proof it's correct, verified two different ways."

Rendering without an error (TODO 05) is not the same as rendering correctly — that gap is exactly what this TODO closes, before anything gets published (TODO 07) or pushed to a device (TODO 08).

## The Two Checks

**Check 1 — golden-output regression testing.** Compare this device's rendered artifact against `golden/<site_id>/<device_id>.cfg`, byte for byte. If today's render doesn't match yesterday's known-good render, something changed, and the pipeline should stop and say so rather than publish it. This is the same pattern real infrastructure and compiler toolchains use to catch unintended change.

**Check 2 — independent policy re-check.** Golden-output testing only catches unintended *change*. It doesn't, by itself, prove the environmental policy is correct if the golden file were ever wrong or stale. This second check re-derives what should **not** be in this device's own output directly from its own environment's policy, and confirms none of it actually made it into the rendered text. It never looks at `resolved_vlans` or `render_context` for this — both already had disabled VLANs filtered out before this device ever got here (see `inventory/devices.py`), so trusting either one could never reveal a leak that happened anyway.

`disabled_vlan_markers` is already computed for you, per device, in `inventory/devices.py` — the exact substring that would reveal a disabled VLAN in *this* device's own rendered text (a VLAN database entry for a Nexus 9K switch, an OSPF network statement for a CAT8K router — see `vlan_marker()` in that file if you want the detail, though you don't need to read it to complete this TODO). It's built from `group_vars/<environment>.yml`'s `disabled_roles` — the same source TODO 03's pre-flight validation already trusts.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 06. Write your
   solution only inside that block - the guard task right after it (an
   assert checking policy_check_result is defined) and the debug task
   after that already exist and aren't yours to write.

2. Add two ansible.builtin.assert tasks:

     - name: verify rendered artifact against golden reference
       ansible.builtin.assert:
         that:
           - <...>
         fail_msg: <...>

     - name: independently verify no disabled vlan leaked into the rendered output
       ansible.builtin.assert:
         that:
           - <...>
         fail_msg: <...>
         success_msg: <...>
       loop: <...>
       register: policy_check_result

   Keep both task names exactly as shown - "verify rendered artifact
   against golden reference" and "independently verify no disabled
   vlan leaked into the rendered output". The grader restarts the
   playbook at the first task's exact name for one part of its check,
   and identifies each task's own pass/fail result by its name for
   both checks - fail_msg/success_msg wording is entirely up to you.
   Only the second task needs register: policy_check_result - if it
   runs at all, the first task already passed (Ansible stops a host at
   its first failed task), so one registered variable is proof enough
   that both ran. Without it, a blank TODO 06 would fall straight
   through to the "report post-render correctness verification" task
   and print both checks as passing even though nothing was checked.

3. Fill in each <...>:

     Task 1 that:  lookup('file', playbook_dir + '/output/' + device_id + '.cfg')
                   == lookup('file', playbook_dir + '/golden/' + site_id + '/' + device_id + '.cfg')

     Task 2 loop:  "{{ disabled_vlan_markers }}"   <- runs this check once per
                   marker this device's own environment disables

     Task 2 that:  item not in lookup('file', playbook_dir + '/output/' + device_id + '.cfg')

   Both tasks read the same rendered file back with lookup('file', ...).
   fail_msg can say whatever's useful to you; the grader checks live
   device behavior and specific text, not your exact wording.
   item not in rendered_text works as a substring check because
   Jinja's in test doubles as two different things depending on what's
   on its right-hand side - list membership when the right side is a
   list, but substring containment when the right side is a plain
   string, exactly like Python's own in operator. Looping over
   disabled_vlan_markers and checking item not in rendered_text, once
   per marker, means each iteration asks "did this one marker leak in?"
   directly - no filtering a whole list down and counting what's left,
   just a plain yes/no per marker. A device with no disabled VLANs at
   all (disabled_vlan_markers is empty) simply runs this task zero
   times - nothing to check, so nothing can fail.
   This check can't just reuse resolved_vlans: resolved_vlans (and
   render_context.vlans) already has every disabled VLAN filtered out,
   before this device's render task ever ran. If a bug upstream caused
   a disabled VLAN to leak into the rendered text anyway, resolved_vlans
   would have no way of knowing - it never saw the leak happen.
   disabled_vlan_markers is built the other way around, straight from
   disabled_roles and this site's own VLAN IDs, so it can catch exactly
   the kind of leak resolved_vlans is structurally blind to.

4. Save, then run: python grading.py
   (Running ./run_playbook.sh directly first, before writing anything,
   fails the same way - the guard assert stops every device with
   "TODO 06 not complete: ...", failed=1 in the PLAY RECAP.)
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 06 - Run Post-Render Correctness Verification
────────────────────────────────────────────────────────────────────────────────

[6] Running post-render correctness verification...

✗ TODO 06 Not Complete

The pipeline cannot continue because post-render verification is not actually
being executed, or does not independently catch a leaked disabled VLAN.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 06 - Run Post-Render Correctness Verification
────────────────────────────────────────────────────────────────────────────────

[6] Running post-render correctness verification...
Golden-output regression check: passes on correct output, fails on a corrupted reference.
Independent policy re-check: passes on correct output, still catches a leaked disabled VLAN even when golden and output agree with each other.
  aus02-cat8k-01 -> both checks passed
  ...

✓ TODO 06 Complete
Post-render verification is running and independently catches both a corrupted golden reference and a leaked disabled VLAN.
```

The grader tests this three ways: a clean run (both checks must pass for every device), a temporarily corrupted golden reference (only that one device's task may fail — everyone else must be unaffected), and a disabled-VLAN marker injected into **both** a staging device's golden file and its own rendered output at once, so they're byte-identical and check 1 alone would wrongly pass. If check 2 is written correctly (re-deriving from `disabled_vlan_markers`, not trusting golden or output content), it catches this third case on its own — proving the two checks are genuinely independent, not one silently doing the other's job.

---
