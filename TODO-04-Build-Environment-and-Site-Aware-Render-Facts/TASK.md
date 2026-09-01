---
# TODO 04 — Build Environment- and Site-Aware Render Facts
---

## Topics Covered

```
✓ Fact Assembly (set_fact)
✓ Preparing Data for Templates
```

## Recap

TODO 01, 02, and 03 are already solved in this folder. Open `site.yml` and find `STUDENT WORK AREA - TODO 04`.

## Scenario

Everything this device needs to render its own config already exists - it's just scattered across separate variables, each coming from a different place:

```
- service_intent.tenant / service_intent.service
    -> loaded by the include_vars task you wrote in TODO 02

- hostname, platform, site_id, environment_name
    -> set automatically as host vars by inventory/devices.py (the
       dynamic inventory) before this playbook even starts - no task
       of yours creates these, they're just already there. Confirm it
       yourself: ansible-inventory -i inventory/devices.py --list

- resolved_vlans
    -> also set automatically by inventory/devices.py, already filtered
       for this exact device's environment and site, already sorted
```

TODO 05's render step needs ONE clean fact to hand to the Jinja template - not three different variables, from three different sources, that it has to know how to find and combine itself. That one fact is what this TODO builds.

This mirrors the Python course's `RenderContext` object, with one real difference: there, TODO 4 also did the VLAN filtering and sorting itself. Here, that work already happened once, centrally, in the dynamic inventory, for every device - see `inventory/devices.py` if you want the details. This TODO is only the assembly step: gather what already exists into the one shape the renderer expects.

## Steps

```
1. Open site.yml and find STUDENT WORK AREA - TODO 04. Write your
   solution only inside that block - the guard task right after it (an
   assert checking render_context is defined) and the debug task
   after that already exist and aren't yours to write.

2. Add one ansible.builtin.set_fact task building one dict:

     - name: build render context
       ansible.builtin.set_fact:
         render_context:
           site_id: <...>
           environment_name: <...>
           tenant: <...>
           service: <...>
           hostname: <...>
           platform: <...>
           vlans: <...>

3. Fill in each value using a variable that's already available on
   this device - nothing here is computed, this task only combines
   existing variables into one dict:

     site_id            - this device's own site_id
     environment_name   - this device's own environment_name
     tenant             - service_intent.tenant
     service            - service_intent.service
     hostname           - this device's own hostname
     platform           - this device's own platform
     vlans              - this device's own resolved_vlans

4. Save, then run: python grading.py
   (Running ./run_playbook.sh directly first, before writing anything,
   fails the same way - the guard assert stops every device with
   "TODO 04 not complete: ...", failed=1 in the PLAY RECAP.)
```

## Grading Check

```
python grading.py
```

Before you complete this TODO:

```
TODO 04 - Build Environment- and Site-Aware Render Facts
────────────────────────────────────────────────────────────────────────────────

[4] Building environment- and site-aware render facts...

✗ TODO 04 Not Complete

The pipeline cannot continue because render_context has not been built yet.

Proceeding to detailed feedback...
```

After you complete it correctly:

```
TODO 04 - Build Environment- and Site-Aware Render Facts
────────────────────────────────────────────────────────────────────────────────

[4] Building environment- and site-aware render facts...
  aus02-cat8k-01 -> render_context.hostname: MER-AUS02-CAT8K-01, vlans: [210, 220, 230, 240]
  ...

✓ TODO 04 Complete
render_context was assembled correctly for every one of the 9 devices.
```

---
