# Runtime

`python -m prove` runs one ready intent. It locks that intent, calls the adapter, writes a worker result, and applies the graph patch.

The verdict rules stay in `docs/integration/roblox-studio-adapter.md`. This file is the command and the actions the package implements.

## Setup

From this repository, with the sibling adapter checkout:

```powershell
$env:PYTHONPATH = "src;..\roblox-studio-adapter\src"
python -m prove status graph/places/example.place.json
```

Python 3.11 or newer. The package does not depend on the adapter at install time. A Studio command needs `roblox_studio_adapter` on `PYTHONPATH`, or an installed adapter 0.1.2 or newer.

Copy a place file before a real run. `run` refuses `example.place.json`.

```powershell
Copy-Item graph/places/example.place.json graph/places/example.local.json
python -m prove run graph/places/example.local.json --name "The open place"
```

`--studio-id` selects the window id from `list_roblox_studios`. `--name` is a `name_contains` selector and overrides `identity.display_name`. With neither flag, the runtime uses `identity.display_name`.

The runtime does not call `agent.save()`. It does not publish.

## Exit codes

| Code | When |
| --- | --- |
| 0 | Verdict `pass` or `inconclusive` |
| 1 | Verdict `fail` |
| 2 | Verdict `blocked`, an action this runtime does not run, no ready intent, or a run aimed at `example.place.json` |

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

`read_source` needs `inputs.path`. `write_source` needs `inputs.path` and `inputs.source`. A missing input is verdict `blocked`.

## What a run persists

The intent is saved as `active` before the Studio call. One active intent is the lock.

The worker result is JSON. When the place file sits inside this repository, the path is `evidence/runs/<id>.worker-result.json`. Characters outside letters, digits, `.`, `_`, and `-` become `-`, so `intent:read-hello` is stored as `intent-read-hello.worker-result.json`. Run files stay local.

The place file then absorbs `graph_patch`, adds `follow_ups` as `proposed` intents, and may set a goal to `done`. A goal closes when every intent spawned from it is `done` or `rejected`, at least one of those intents checks a claim, and every such claim is `supported`.

An unexpected error leaves the intent `active`. The next `run` continues that intent.

`AmbiguousStudioError` and `NoStudioError` record verdict `blocked`. `AmbiguousOutcome` and `TimeoutError` record `inconclusive` and propose a read of the script that was being written, or an `overview` when the intent had no script path. `ToolFailed`, `ModeError`, and `UnyieldingLuau` record `fail`. A `fail` sets a claim that intent checks to `contradicted`.

`status` prints the place id, the active intent, the next intent, intents waiting on `after`, and open questions. It does not write the place file.
