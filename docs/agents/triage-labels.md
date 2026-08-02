# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## State of these labels in this repo

As of 2026-08-02, only `wontfix` exists - it comes from GitHub's default label set. The other four have never been created, because nothing has been triaged here yet. `/triage` will create them on first use; there is no pre-existing vocabulary to preserve, so the defaults above stand.

Separately, this repo also carries `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling` and `wayfinder:task`. Those belong to `/wayfinder`, not to triage, and the two vocabularies do not interact.
