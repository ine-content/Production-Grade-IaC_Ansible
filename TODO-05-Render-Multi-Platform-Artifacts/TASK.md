---
# TODO 05 — Render Multi-Platform Artifacts
---

## Topics Covered

```
✓ Template Rendering (ansible.builtin.template)
✓ Task-Level vars: Overrides
✓ Platform-Conditional Logic
```

## Recap

TODO 01 through TODO 04 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 05`.

## Scenario

`render_context` (TODO 04) has everything this device's config needs. But `ansible.builtin.template` doesn't work like Python's Jinja2 — there is no `template.render(**render_context)` that hands a whole object to the template in one call. Ansible renders a template using whatever variables are already in scope, under the exact names the `.j2` file references.

Look at `templates/cat8k_ospf.j2` and `templates/nexus_vlan.j2` — both expect plain `hostname` and `vlans`:

```
hostname {{ hostname }}
...
{% for vlan in vlans %}
```

Neither template says `render_context.hostname` or `render_context.vlans`. If you just run the template module against `render_context` sitting in scope, `hostname` and `vlans` are undefined and rendering fails.

This TODO is the render step: pick the right template file for this device's platform, expose `render_context`'s fields under the names those templates actually expect, and write the result to `output/<device_id>.cfg`.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 05. Write your
   solution only inside that block - the two guard tasks right after
   it (stat + assert, checking output/<device_id>.cfg actually
   exists) and the debug task after that already exist and aren't
   yours to write.

2. Add one ansible.builtin.template task:

     - name: render the platform-specific configuration
       ansible.builtin.template:
         src: <...>
         dest: <...>
       vars:
         platform_templates:
           cat8k: <...>
           nexus9k: <...>
         hostname: <...>
         vlans: <...>

3. Fill in each <...>:

     src              - the right template for this device's platform,
                        chosen by looking render_context.platform up
                        in the platform_templates dict below
     dest             - "{{ playbook_dir }}/output/{{ device_id }}.cfg"
     platform_templates.cat8k    - cat8k_ospf.j2
     platform_templates.nexus9k  - nexus_vlan.j2
     hostname         - render_context.hostname
     vlans            - render_context.vlans

   Both template files already exist under templates/ - Ansible finds
   them there automatically, so src: only needs the filename, not a
   full path. platform_templates[render_context.platform] looks up
   this device's own platform and returns the matching filename, so
   src: becomes one Jinja expression instead of an if/else chain.

4. The vars: block matters because a task's own vars: only exists for
   the duration of that task - it's the standard Ansible way to rename
   a variable for something that expects a different name. Here,
   that "something" is the template file itself, which was written
   expecting hostname and vlans, not render_context.hostname and
   render_context.vlans.

5. Save, then run: python grading.py
   (Running ./run_playbook.sh directly first, before writing anything,
   fails the same way - the guard assert stops every device with
   "TODO 05 not complete: ...", failed=1 in the PLAY RECAP.)
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 05 - Render Multi-Platform Artifacts
────────────────────────────────────────────────────────────────────────────────

[5] Rendering multi-platform artifacts...

✗ TODO 05 Not Complete

The pipeline cannot continue because no device configuration has been rendered yet.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 05 - Render Multi-Platform Artifacts
────────────────────────────────────────────────────────────────────────────────

[5] Rendering multi-platform artifacts...
  aus02-cat8k-01 -> output/aus02-cat8k-01.cfg matches golden/aus02/aus02-cat8k-01.cfg ('hostname MER-AUS02-CAT8K-01')
  ...

✓ TODO 05 Complete
Every device's rendered artifact matches its golden reference config exactly.
```

The grader checks this by clearing `output/*.cfg`, running the playbook, and comparing each device's rendered file against its reference in `golden/<site_id>/<device_id>.cfg` byte for byte — not just that a file exists, but that it's exactly right.

---
