# Evidence

A worker writes one `prove.worker-result/1` file per intent. The schema is `protocols/worker-result.schema.json`. The envelope inside it is `prove.evidence/1` (`protocols/evidence.schema.json`).

When the worker ran a playtest, `evidence.studio` is `roblox-studio-adapter.evidence/1`. That field list stays in the adapter (`docs/evidence.schema.json`). The sample file `examples/verify-hello.worker-result.json` shows both layers filled in for the sample place's verify intent.

## Where files go

| File | Committed? |
| --- | --- |
| `evidence/examples/` | Yes. Shapes and the sample walkthrough |
| `evidence/runs/<intent-id>.worker-result.json` | No. Gitignored. Screenshot paths and `studio_id` live here |
| Evidence node on the place graph | Yes, when the place file is shared. `props.path` may point at a local run. A shared place file should use a path the next person can read, or drop the run and keep `props.summary` |

`console` excerpts in the adapter record are already clipped. The place graph stores the summary, not the excerpt.

A script read or write adds three observations: `script_path`, `source_sha256`, and `source`. `source` is the script body. It stays in this local file so the next session can fill a write without opening Studio. Do not commit a run file. The place graph keeps the hash and, after a successful write, drops `inputs.source` from the intent.

## Verdict

The worker sets `evidence.verdict` with the table in `docs/integration/roblox-studio-adapter.md`. The evidence node's `status` is that same word. `graph_patch.set_status` is how the node and the intent change together.

## What a record must make checkable

- Which intent, which place, which worker.
- The verdict and a one-line summary a later planner can read without opening Studio.
- The check id that failed, when one failed (`observations` or `studio.failures`).
- The limits: solo play, reset console, missing screenshot, server copy not read. The sample puts these in `evidence.limits`.
- Artifact paths for screenshots and video, so a person can open the file. The bytes stay on disk.
