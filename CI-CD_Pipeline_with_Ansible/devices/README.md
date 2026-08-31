# devices/

One `<site_id>.json` file per site. Each file is a JSON array of every
device at that site. JSON has no comment syntax, so this file documents
the schema instead — plain JSON is what `inventory/devices.py` and
`mock_device_server.py` both parse directly.

```json
{ "device_id": "rdu01-cat8k-01", "site_id": "rdu01", "platform": "cat8k",
  "hostname": "MER-RDU01-CAT8K-01", "ip_address": "127.50.11.10",
  "restconf_port": 8543 }
```

Field meanings:

```
device_id       - unique across the whole course, "<site_id>-<platform-short>-NN"
site_id         - must match a "site_id" in sites/<site_id>.json
platform        - "cat8k" or "nexus9k" only (the only two platforms
                  inventory/devices.py and mock_device_server.py know
                  RESTCONF paths for)
hostname        - the device's own configured hostname, used by templates/
ip_address      - must be a loopback address a mock server can actually
                  bind (see mock_device_server.py, setup_local_loopback.sh)
restconf_port   - the port mock_device_server.py listens on for this device
```

This directory is the single source of truth for "what devices exist."
Add a device here (or an entirely new `<site_id>.json`, alongside a
matching `sites/<site_id>.json`) and it is picked up automatically —
by the dynamic inventory, and by the mock device fleet — with no other
file needing a change. See `inventory/devices.py`'s module docstring for
the full explanation of why this is a script and not a static file.
