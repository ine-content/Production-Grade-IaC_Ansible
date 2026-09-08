---
# TODO 07 — Publish Idempotently
---

## Topics Covered

```
✓ Idempotency
✓ ansible.builtin.template's Built-in Checksum Comparison
✓ register: and changed:
```

## Recap

TODO 01 through TODO 06 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 07`.

## Scenario

Now that every artifact has been independently verified twice (TODO 06), it's safe to actually publish it. But a pipeline that rewrites every device's config file on every single run — whether or not anything actually changed — makes it impossible to ever tell a real change from noise.

Network Engineering's complaint: "We run this pipeline on a schedule, and if it rewrites every config file every single time, even when nothing changed, we can't trust file timestamps, we can't tell a real change from noise, and every run looks like a full redeploy. We need it to only touch a file when something actually changed."

A hand-written pipeline (in plain Python, say) has to solve this itself: hash the new content, compare it against a hash saved from the last run, and only write to disk if they differ. Ansible modules already do this. `ansible.builtin.template` checksums the content it's about to write against whatever's already at `dest`, and only touches the file — and only reports `changed: true` — if they're actually different. TODO 05's render task has been idempotent this whole time, without you writing a single extra line for it.

This TODO doesn't add a new mechanism. It makes an existing guarantee visible and proven, rather than just assumed: re-run the exact same render immediately after it, and confirm Ansible itself reports no change the second time.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 07. Write your
   solution only inside that block - the guard task right after it (an
   assert checking republish_result is defined) and the debug task
   after that already exist and aren't yours to write.

2. Add one ansible.builtin.template task - identical to TODO 05's own
   task - followed by one ansible.builtin.assert:

     - name: re-render the platform-specific configuration to confirm publishing is idempotent
       ansible.builtin.template:
         src: <...>
         dest: <...>
       vars:
         platform_templates:
           cat8k: <...>
           nexus9k: <...>
         hostname: <...>
         vlans: <...>
       register: <...>

     - name: assert this device's config was not rewritten
       ansible.builtin.assert:
         that:
           - <...>
         fail_msg: <...>
         success_msg: <...>

   This task looking identical to TODO 05's is the point, not an
   oversight - idempotency means running the same declarative action
   again and getting nothing to happen. Name its result
   republish_result (not something generic) so it's clear at a glance
   which result is which. Keep the assert task's name exactly "assert
   this device's config was not rewritten" - the grader identifies its
   pass/fail result by that name, not by fail_msg/success_msg wording.

3. Fill in each <...> - the template task is a straight copy of
   TODO 05's:

     src              - platform_templates[render_context.platform]
     dest             - "{{ playbook_dir }}/output/{{ device_id }}.cfg"
     platform_templates.cat8k    - cat8k_ospf.j2
     platform_templates.nexus9k  - nexus_vlan.j2
     hostname         - render_context.hostname
     vlans            - render_context.vlans
     register         - republish_result

     assert that:     - not republish_result.changed

   republish_result.changed is false when Ansible compared the content
   it was about to write against what's already at dest and found them
   identical. If your assert fails, the likely cause isn't the assert -
   it's a small mismatch between this task's src/dest/vars and TODO
   05's, causing Ansible to render something slightly different from
   what's already on disk.

4. Save, then run: python grading.py
   (Running ./run_playbook.sh directly first, before writing anything,
   fails the same way - the guard assert stops every device with
   "TODO 07 not complete: ...", failed=1 in the PLAY RECAP.)
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 07 - Publish Idempotently
────────────────────────────────────────────────────────────────────────────────

[7] Publishing idempotently...

✗ TODO 07 Not Complete

The pipeline cannot continue because publishing has not been proven idempotent -
a second run should make zero changes, on every device.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 07 - Publish Idempotently
────────────────────────────────────────────────────────────────────────────────

[7] Publishing idempotently...
Run 1 (clean output/): every device showed exactly 1 changed task (the first render).
Run 2 (immediately after): every device showed exactly 0 changed tasks.
  aus02-cat8k-01 -> already correct on disk, nothing rewritten
  ...

✓ TODO 07 Complete
Publishing is proven idempotent - a second run of the whole pipeline makes zero changes on any device.
```

The grader tests this three ways. First, it runs the whole playbook twice in a row, with nothing else changed in between, and reads Ansible's own per-host `changed` counter straight out of the `PLAY RECAP` - not just text you printed. The first run (from a cleared `output/`) must show exactly one changed task per device (TODO 05's first-ever write). The second run must show exactly zero. Third, it deliberately corrupts one device's already-rendered output and re-checks just that device: your assert must genuinely fail here, `changed` must flip to `true` - proof your `that:` condition is really checking `republish_result.changed` and isn't a no-op that always reports success.

---
