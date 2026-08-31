# sites/

One `<site_id>.json` file per site — its own physical/network identity,
separate from the devices that live there (see `devices/README.md`). JSON
has no comment syntax, so this file documents the schema instead.

```json
{ "site_id": "rdu01", "region": "us-east", "environment": "prod",
  "vlan_ids": { "users": 110, "voice": 120, "wifi": 130, "guest": 140,
                "unused": 199 } }
```

Field meanings:

```
site_id      - matches devices/<site_id>.json's filename and every
               device's own "site_id" field
region       - free-form label, exposed as the "region" hostvar
environment  - "prod" or "staging" - which group_vars/<environment>.yml
               policy this site's devices inherit
vlan_ids     - this site's actual VLAN numbers, keyed by role. Combined
               with intent/retail_branch_service.yml's enabled roles (see
               resolve_vlans() in inventory/devices.py) to produce each
               device's resolved_vlans
```

Note this key is named "environment", not "environment_name" - unlike
group_vars/*.yml, this file is plain JSON consumed only by Python
(inventory/devices.py, mock_device_server.py), never loaded by Ansible
itself as a variable, so the "environment" reserved-keyword collision
(see group_vars/prod.yml's comment) doesn't apply here. devices.py reads
this "environment" key and republishes it to Ansible under the safe name
environment_name - that translation happens once, in one place.
