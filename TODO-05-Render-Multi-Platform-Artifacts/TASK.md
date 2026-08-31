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

## Your Task

Inside `STUDENT WORK AREA - TODO 05` in `site.yml`, write one `ansible.builtin.template` task shaped like this:

```yaml
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
```

Fill in each `<...>`:

```
src              - the right template for this device's platform, chosen by
                   looking render_context.platform up in the
                   platform_templates dict below
dest             - "{{ playbook_dir }}/output/{{ device_id }}.cfg"
platform_templates.cat8k    - cat8k_ospf.j2
platform_templates.nexus9k  - nexus_vlan.j2
hostname         - render_context.hostname
vlans            - render_context.vlans
```

Both template files already exist under `templates/` — Ansible finds them there automatically, so `src:` only needs the filename, not a full path.

### Why the vars: block matters

A task's own `vars:` only exists for the duration of that task, and it's the standard Ansible way to rename a variable for something that expects a different name — here, that "something" is the template file itself, which was written expecting `hostname` and `vlans`, not `render_context.hostname` and `render_context.vlans`.

### Hints

`platform_templates` is just a plain dict you're defining inline in `vars:` — nothing special about it beyond that. `platform_templates[render_context.platform]` looks up this device's own platform in that dict and returns the matching filename, so `src:` becomes one Jinja expression instead of an if/else chain — and adding a third platform later only means adding one more key to this dict.

## Where to Write Your Code

Open `site.yml`. Locate `STUDENT WORK AREA - TODO 05`. Write your solution only inside that block — the two guard tasks right after it (`stat` + `assert`, checking that `output/<device_id>.cfg` actually exists) and the `debug` task after that already exist and aren't yours to write. The `debug` task reads back the first line of `output/<device_id>.cfg` to prove something was actually rendered.

### Running this directly, without `python grading.py`

If you run `./run_playbook.sh` yourself before writing anything, every device genuinely fails on that guard task: `failed=1` in the PLAY RECAP, a non-zero exit code, and a `fatal: [host]: FAILED! => {...}` result carrying the "TODO 05 not complete: ..." message.

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
