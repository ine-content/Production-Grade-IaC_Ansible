#!/usr/bin/env python3
"""
inventory/devices.py - dynamic Ansible inventory for the Meridian Retail
branch network.

This is the Ansible-native equivalent of what CI-CD_Pipeline_with_Git's
mock_device_server.py and iac_lib.py did together: devices/*.json is the
one source of truth for what devices exist, and this script turns that
into Ansible groups and host variables automatically, every time it runs.
Add a device to an existing devices/<site_id>.json file, or an entirely
new site (devices/<new_site>.json + sites/<new_site>.json), and it shows
up in `ansible-inventory --list` on the very next run - no code change,
no re-registration, nothing else to touch.

Ansible calls this file directly (it's a "script" inventory source - see
https://docs.ansible.com/ansible/latest/dev_guide/developing_inventory.html#inventory-script-conventions):

    ansible-inventory -i inventory/devices.py --list
    ansible-playbook -i inventory/devices.py playbooks/site.yml

Groups this produces:
  - One group per environment (prod, staging) - group_vars/<environment>.yml
    attaches automatically because Ansible loads group_vars by group name.
  - One group per platform (cat8k, nexus9k) - useful for platform-specific
    plays/roles.
  - One group per site (rdu01, aus02, sea03) - useful for site-scoped runs.

Host variables this sets, per device:
  ansible_host       - the device's own IP (mock_device_server.py binds a
                        listener at exactly this address)
  ansible_connection  - "local": nothing here is reached over SSH. Every
                        device in this course is a RESTCONF HTTP endpoint,
                        so all "connection" details are just plain
                        variables tasks pass to restconf_config/restconf_get
                        or the uri module - there is no real transport for
                        Ansible itself to open.
  device_id, site_id, platform, hostname, restconf_port, restconf_path
  region, environment_name, resolved_vlans - the exact VLANs this device
                        should carry: intent's enabled VLANs, minus the
                        environment's disabled_roles, mapped to this
                        site's actual VLAN IDs. The same resolution
                        iac_lib.py's resolve_vlans() did in the Python
                        course, done here once, in one shared place, so
                        no lesson has to re-derive it.

  Note the name environment_name, not environment: "environment" is a
  reserved Ansible play/task keyword (it sets environment variables for
  module execution), so a host var literally named "environment" is
  silently shadowed - {{ environment }} in a template or task returns the
  built-in empty value, never this host's real value, with no error or
  warning. environment_name sidesteps that trap entirely.
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
DEVICES_DIR = ROOT / "devices"
SITES_DIR = ROOT / "sites"
GROUP_VARS_DIR = ROOT / "group_vars"
INTENT_FILE = ROOT / "intent" / "retail_branch_service.yml"

RESTCONF_PATHS = {
    "cat8k": "/restconf/data/Cisco-IOS-XE-native:native/router/ospf",
    "nexus9k": "/restconf/data/nexus-vlan-database",
}


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_sites():
    """site_id -> site dict, read from every sites/*.json file."""
    sites = {}
    for site_file in sorted(SITES_DIR.glob("*.json")):
        site = load_json(site_file)
        sites[site["site_id"]] = site
    return sites


def load_environments():
    """environment name -> {disabled_roles, auto_deploy}, read from
    group_vars/*.yml - the same files Ansible itself loads for real runs,
    so this inventory script and a real playbook can never quietly
    disagree about what a given environment allows.

    Keyed by "environment_name", not "environment" - see the module
    docstring above for why "environment" specifically is unsafe to use
    as an Ansible variable name."""
    environments = {}
    for group_vars_file in sorted(GROUP_VARS_DIR.glob("*.yml")):
        data = load_yaml(group_vars_file)
        if data and "environment_name" in data:
            environments[data["environment_name"]] = data
    return environments


def resolve_vlans(intent, environment_policy, site):
    """Every VLAN this device should carry: intent's enabled VLANs, minus
    this environment's disabled_roles, mapped to this site's actual VLAN
    IDs. Mirrors iac_lib.py's resolve_vlans() from the Python course -
    same rule, same shape, just computed once here for every device
    instead of inside a hand-written pipeline."""
    disabled_roles = set(environment_policy.get("disabled_roles", []))
    resolved = []
    for vlan in intent["vlans"]:
        if not vlan["enabled"]:
            continue
        if vlan["role"] in disabled_roles:
            continue
        resolved.append({
            "id": site["vlan_ids"][vlan["role"]],
            "name": vlan["name"],
            "role": vlan["role"],
        })
    return sorted(resolved, key=lambda v: v["id"])


def build_inventory():
    sites = load_sites()
    environments = load_environments()
    intent = load_yaml(INTENT_FILE)

    inventory = {"_meta": {"hostvars": {}}}

    def add_to_group(group, host):
        inventory.setdefault(group, {"hosts": []})
        if host not in inventory[group]["hosts"]:
            inventory[group]["hosts"].append(host)

    for device_file in sorted(DEVICES_DIR.glob("*.json")):
        for device in load_json(device_file):
            site = sites[device["site_id"]]
            environment_name = site["environment"]
            environment_policy = environments.get(environment_name, {})

            host = device["device_id"]
            add_to_group(environment_name, host)
            add_to_group(device["platform"], host)
            add_to_group(device["site_id"], host)

            inventory["_meta"]["hostvars"][host] = {
                "ansible_host": device["ip_address"],
                "ansible_connection": "local",
                # Every "host" here is really this same machine (RESTCONF
                # over HTTP, not SSH) - telling Ansible to reuse the exact
                # interpreter already running ansible-playbook itself skips
                # its per-host interpreter auto-discovery, which otherwise
                # prints one "future installation of another Python..."
                # warning per device even though they're all identical.
                "ansible_python_interpreter": "{{ ansible_playbook_python }}",
                "device_id": device["device_id"],
                "site_id": device["site_id"],
                "platform": device["platform"],
                "hostname": device["hostname"],
                "restconf_port": device["restconf_port"],
                "restconf_path": RESTCONF_PATHS[device["platform"]],
                "region": site["region"],
                "environment_name": environment_name,
                "resolved_vlans": resolve_vlans(intent, environment_policy, site),
            }

    return inventory


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        print(json.dumps(build_inventory(), indent=2))
    elif len(sys.argv) == 3 and sys.argv[1] == "--host":
        # Every host's vars are already returned under _meta in --list,
        # which Ansible always prefers when present - this branch exists
        # only to satisfy the script-inventory contract for tools that
        # call --host directly instead.
        print(json.dumps({}))
    else:
        sys.stderr.write("Usage: devices.py --list | devices.py --host <hostname>\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
