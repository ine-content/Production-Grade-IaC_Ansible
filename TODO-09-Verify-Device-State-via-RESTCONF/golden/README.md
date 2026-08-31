# golden/

One `<site_id>/<device_id>.cfg` file per device — the exact config that
device should end up with once `templates/cat8k_ospf.j2` or
`templates/nexus_vlan.j2` renders its render_context correctly (TODO 04 +
TODO 05) and, in a later TODO, that config is pushed over RESTCONF.

These are reference output, not source you write. A later grading check
compares a real render (or a real GET back from the mock device) against
the matching file here byte-for-byte, so nothing in this directory should
ever be hand-edited to "look nicer" — any stray whitespace or comment
added here would make an otherwise-correct student render fail grading.

If you ever need to know what a device's config *should* look like, this
is the place to check — not a description, the literal expected output.
