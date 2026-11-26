# Playbook: explore a place

Use this when the graph has no service nodes, or the nodes are `stale`, and the goal needs a map before a change.

1. Ask which Studio window when `RobloxStudio.connect` reports more than one and the place identity does not select a single window.
2. Emit an `explore` intent whose action is `overview`. `inputs` names the services the goal cares about. `done_when` says those services exist as nodes with status `observed`.
3. The worker calls `agent.loop.explore()` or `agent.datamodel.overview()`. It pages with `tree(path, max_depth=2)` when the overview is truncated. It uses `scripts.find` for script names.
4. The worker result's `graph_patch` upserts `service` and `script` nodes. Script props get `path`, `class_name`, and `responsibility` when the name makes the responsibility clear. The body stays in Studio. A read intent records `source_sha256` later.
5. Verdict is `inconclusive`. An explore records what was visible. It does not prove a behavior.
6. The next proposed intent is a read or a verify against the open goal. The explore intent is `done`.

The call list is the `explore` row in `workers/catalog.md`.
