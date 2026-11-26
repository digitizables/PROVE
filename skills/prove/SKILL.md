---
name: prove
description: Operate the PROVE place graph, planner, and evidence loop for Roblox Studio. Use when working in the PROVE repo, turning a game goal into short intents, running a PROVE worker, or recording Studio evidence through roblox-studio-adapter.
---

# PROVE session

Follow this order. Field lists, status words, adapter methods, and verdict rules have their own files. Use those files when a step names them.

1. Read the place file (`graph/places/<id>.local.json`, or `graph/places/example.place.json` for the sample).
2. If some intent has status `active`, continue that intent. Leave every other intent `proposed`.
3. If the goal can be decided more than one way, add a `question` node and ask the person. Wait for the answer before a write intent.
4. Activate the earliest `proposed` intent whose `props.after` is null or names an intent already `done`. How to cut an intent is in `planner/README.md`.
5. Run the worker named on the intent. Call only the adapter methods in that worker's row in `workers/catalog.md`.
6. Open Studio with the rules in `docs/integration/roblox-studio-adapter.md`. Use adapter 0.1.1 or newer.
7. Write one `prove.worker-result/1` file under `evidence/runs/`. Apply its `graph_patch` to the place file. Set the intent to `done` or `blocked` as the patch says.
8. Apply the verdict rules in the integration doc before marking a claim `supported`.
9. Leave `follow_ups` as new `proposed` intents. Run the next one only after this result is on the graph.
10. Save the place only after the person asks. Use `agent.save()`. Publishing stays a separate confirmation through the adapter's high-risk cloud gate.

Playbooks for the three common sessions: `docs/playbooks/explore-a-place.md`, `docs/playbooks/verify-a-change.md`, `docs/playbooks/iterate-on-failure.md`.
