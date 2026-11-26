# Runtime

`python -m prove run` runs one ready intent. It locks that intent, calls the adapter, writes a worker result, and applies the graph patch. `python -m prove plan` appends the next intent from the latest evidence and does not call Studio.

The verdict rules stay in `docs/integration/roblox-studio-adapter.md`. This file is the command and the actions the package implements.

## Setup

From this repository, with the sibling adapter checkout:

```powershell
$env:PYTHONPATH = "src;..\roblox-studio-adapter\src"
python -m prove status graph/places/example.place.json
```

Python 3.11 or newer. The package does not depend on the adapter at install time. A Studio command needs `roblox_studio_adapter` on `PYTHONPATH`, or an installed adapter 0.1.2 or newer.

Copy a place file before a real run. `run` refuses `example.place.json`. `plan` leaves that file unchanged when the plan would edit it.

```powershell
Copy-Item graph/places/example.place.json graph/places/example.local.json
python -m prove run graph/places/example.local.json --name "The open place"
```

`--studio-id` selects the window id from `list_roblox_studios`. `--name` is a `name_contains` selector and overrides `identity.display_name`. With neither flag, the runtime uses `identity.display_name`.

The runtime does not call `agent.save()`. It does not publish.

## Exit codes

`run` uses these codes.

| Code | When |
| --- | --- |
| 0 | Verdict `pass` or `inconclusive` |
| 1 | Verdict `fail` |
| 2 | Verdict `blocked`, an action this runtime does not run, a missing `inputs.source` or `inputs.path`, no ready intent, or a run aimed at `example.place.json` |

`plan` exits 0 when it adds intents, when an intent is already ready, or when there is nothing to add. It exits 2 when an intent is blocked, the evidence file is missing, the same failure has been recorded three times, or the file is `example.place.json` and the plan would have changed it.

`--json` prints the worker result. The other form prints the intent id, the verdict, the summary, and the evidence path.

## Actions

| Worker | Action | Studio call | What the patch records |
| --- | --- | --- | --- |
| `script` | `read_source` | `scripts.read` | Script `observed`, `source_sha256` of the source UTF-8, verdict `inconclusive` |
| `script` | `write_source` | `scripts.write` | Same hash, taken from the text that was written |
| `playtest` | `verify_output` | `playtest.run` | Verdict from the studio record. `inputs.probes` are passed through |
| `playtest` | `change_and_verify` | `loop.change_and_verify` | The studio record on `result["evidence"]`, script hashes, instance nodes |
| `explore` | `overview` | `loop.explore` | Services and scripts `observed`. An existing `source_sha256` stays. A new script has no hash |

Any other worker or action raises before the intent is activated and before Studio is contacted.

`read_source` needs `inputs.path`. `write_source` needs `inputs.path` and `inputs.source`. A missing input stays `proposed`, and `run` exits 2 before it contacts Studio.

## Plan

`python -m prove plan <place>` reads the place file and the evidence files the graph points at.

A ready or active intent is left for `run`. A readback from `AmbiguousOutcome` stays the next intent. An existing `blocked` intent stops planning.

`console.reset` adds one `verify_output` with the same playtest inputs. The claim status stays as it is.

A failed check adds `write_source` for the script that implements the claim. `inputs.path` and `inputs.class_name` are filled. `inputs.source` is left empty for the person or the agent. When that script is `unverified` or `stale`, a `read_source` intent is ordered first. The recheck is `verify_output` with the same playtest inputs, and its `after` is the write. When the graph has no script path, the first intent is `overview`.

The same failed observation on one claim, three times, adds a blocked intent and an open question. The failed evidence nodes stay. Reject that blocked intent after the question is answered if a later `plan` should run.

## What a run persists

The intent is saved as `active` before the Studio call. One active intent is the lock.

The worker result is JSON. When the place file sits inside this repository, the path is `evidence/runs/<id>.worker-result.json`. Characters outside letters, digits, `.`, `_`, and `-` become `-`, so `intent:read-hello` is stored as `intent-read-hello.worker-result.json`. Run files stay local.

The place file then absorbs `graph_patch`, adds `follow_ups` as `proposed` intents, and may set a goal to `done`. A goal closes when every intent spawned from it is `done` or `rejected`, at least one of those intents checks a claim, and every such claim is `supported`.

An unexpected error leaves the intent `active`. The next `run` continues that intent.

`AmbiguousStudioError` and `NoStudioError` record verdict `blocked`. `AmbiguousOutcome` and `TimeoutError` record `inconclusive` and propose a read of the script that was being written, or an `overview` when the intent had no script path. `ToolFailed`, `ModeError`, and `UnyieldingLuau` record `fail`. A `fail` sets a claim that intent checks to `contradicted`.

`status` prints the place id, the active intent, the next intent, intents waiting on `after`, and open questions. It does not write the place file.
