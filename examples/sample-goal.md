# Sample goal

Place file: `graph/places/example.place.json`.

The open goal is `goal:hello`: on a solo playtest the server prints `hello from the agent`. The claim `claim:hello-prints` is `unverified`. `question:which-studio` is `open` because `identity.display_name` is the placeholder `Example`.

## What the session does

1. Ask the person which Studio window, and record the answer on the question (`status` `answered`, `props.answer`) and on `identity.display_name` if the name was wrong. That is a graph edit with no Studio call.
2. Activate `intent:read-hello`. It is `proposed`, `order` 1, `after` null. The script worker calls `scripts.read` on `game.ServerScriptService.HelloAgent`. The patch sets `script:hello` to `observed` and adds `props.source_sha256`. The body stays in Studio.
3. Activate `intent:verify-hello` only after the read is `done`. The playtest worker calls `playtest.run` with the `inputs` on that intent and wraps the adapter record as in `evidence/examples/verify-hello.worker-result.json`.
4. Apply that file's `graph_patch`: an evidence node, a `supports` edge, the claim `supported`, the intent `done`.
5. The acceptance on the goal is met by that claim, so the planner sets `goal:hello` to `done`.

If `studio.console.reset` is true, step 4 writes verdict `inconclusive` and the claim stays `unverified`. The failure playbook cuts the next playtest. If Output contains `hello failed`, verdict is `fail`, the claim is `contradicted`, and the next intent is one fix.

The sample evidence file is an illustration of the verify result. It is not a recording from a live Studio session.

## With the runtime

Copy the sample, then ask the runtime for one intent at a time. `python -m prove next` on the copy names the action. `status` and `next` on the checked-in sample are safe. `run` refuses `example.place.json`.

```powershell
Copy-Item graph/places/example.place.json graph/places/example.local.json
$env:PYTHONPATH = "src;..\roblox-studio-adapter\src"
python -m prove status graph/places/example.local.json
python -m prove run graph/places/example.local.json --name "The open place"
```

The first run reads HelloAgent and stores `source_sha256`. The second playtests. A pass supports `claim:hello-prints` and sets `goal:hello` to `done`. A fail leaves the goal open. `python -m prove plan` then appends a write and a recheck. `--name` selects the Studio window and overrides `identity.display_name`. The runtime does not save the Roblox place.
