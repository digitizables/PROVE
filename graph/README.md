# Place graph

One JSON file is the shared model of one place. The schema is `protocols/place.schema.json` (`prove.place/1`). The sample is `places/example.place.json`.

A live file for a real game is `places/<id>.local.json`. Those files are gitignored. They may contain a file path on this machine. Commit a place file only after the person asks to share the model, and keep `studio_id` out of it. Studio window ids change when Studio restarts. Evidence runs may store them, and runs stay local.

## Document

`identity` is how a worker selects the Studio window: `display_name` (passed to `name_contains`), `place_id`, or `file_name`. `updated_at` changes when a patch is applied.

`nodes` and `edges` are the graph. At most one node of type `intent` has status `active`. That intent is the lock. Another session waits, or adds a `question` that does not call Studio.

An evidence node stores `props.path` and `props.summary`. The path points at a `prove.worker-result/1` file. The body of the evidence stays in that file.

A script node stores `props.source_sha256` after a read or a write. It does not store the source text. The local worker-result file for that read or write stores the text in `observations` (`script_path`, `source_sha256`, `source`). Run files stay uncommitted. A successful write removes `inputs.source` from the intent on the place graph. The run file still has the text.

## Status

The status word has to match the node type.

| Type | Status | Meaning |
| --- | --- | --- |
| `place` | `active` | This file describes this place |
| `service`, `instance`, `script` | `unverified` | Named, and not read since |
| `service`, `instance`, `script` | `observed` | Read from Studio and recorded |
| `service`, `instance`, `script` | `stale` | The place changed since the observation |
| `system` | `sketched` | Named, and scripts or instances are not all linked |
| `system` | `mapped` | The implementing scripts and instances are linked |
| `goal` | `open` | The person wants this decided |
| `goal` | `done` | The acceptance claim is `supported` |
| `goal` | `dropped` | The person dropped the goal |
| `intent` | `proposed` | Ready, and not started |
| `intent` | `active` | The session lock |
| `intent` | `done` | A worker result was applied |
| `intent` | `blocked` | The person has to answer or act |
| `intent` | `rejected` | The person rejected the intent |
| `claim` | `unverified` | No verdict has settled it |
| `claim` | `supported` | A `pass` evidence node checks it |
| `claim` | `contradicted` | A `fail` evidence node checks it |
| `evidence` | `pass`, `fail`, `inconclusive`, `blocked` | The verdict rules in the integration doc |
| `question` | `open` | Waiting on the person |
| `question` | `answered` | The answer is in `props.answer` |

## Edges

| Type | From | To |
| --- | --- | --- |
| `contains` | place, service, or instance | service, instance, or script |
| `implements` | script or instance | system |
| `depends_on` | system or script | system or script |
| `spawned_from` | intent | goal |
| `checks` | intent or evidence | claim |
| `about` | claim or question | system, script, instance, or place |
| `supports` | evidence | claim |
| `contradicts` | evidence | claim |

`checks` on an intent is the claim that intent is allowed to settle. `supports` and `contradicts` are written when the evidence verdict is `pass` or `fail`.

## Claim check

`claim.props.goal_id` names the goal that claim decides. `claim.props.check` is the playtest input the planner copies onto a `verify_output` intent: `expect_contains`, `expect_absent`, `seconds`, `screenshot`, `forbid_errors`, and `probes`. At least one of the two string lists is required. `claim.props.path` is the script that implements the claim. An `about` edge from the claim to that script, or to a system the script `implements`, is the same link.

`python -m prove goal` writes those fields. `python -m prove plan` then appends the read and the verify. It does not invent a script body.

## Patch

A worker result carries `graph_patch`:

- `upsert_nodes` replaces a node with the same `id`, or inserts it.
- `upsert_edges` does the same for edges.
- `set_status` changes `status` and leaves other fields in place.

The session that applies the patch sets `updated_at`. A Studio worker's patch may add the evidence node for its own intent, edges from that evidence, and status updates for that intent and the claims it checks. Wider map edits belong to a `graph` worker. See `workers/README.md`.
