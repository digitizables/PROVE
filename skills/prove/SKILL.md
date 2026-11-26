---
name: prove
description: Operate the PROVE place graph, planner, and evidence loop for Roblox Studio. Use when working in the PROVE repo, turning a game goal into short intents, running a PROVE worker, or recording Studio evidence through roblox-studio-adapter.
---

# PROVE session

The place file is the shared state. `python -m prove next` names the one next action. Do not call Studio except through `run`. Do not invent a script body when `next` already returned one. Do not save or publish the Roblox place unless the person asks.

1. Use `graph/places/<id>.local.json` when it exists. Otherwise run `python -m prove init` on that path with the place id, title, and the Studio window's display name.
2. Add a goal with `python -m prove goal`. `--contains` or `--absent` is the check a playtest can decide. Pass `--script` when you know the script path.
3. Run `python -m prove next --json` on that file.
4. `action` is `plan`: run `python -m prove plan`, then `next` again. Plan does not call Studio. It seeds a read and a verify from `claim.props.check`, and after a failed check it appends a write whose `inputs.source` is still empty.
5. `action` is `run`: run `python -m prove run` on the local file. One intent. Then `next` again. `run` refuses `example.place.json`.
6. `action` is `fill`: the JSON `source` field is the current script body from the local evidence file. Write the new body to a file and run `python -m prove fill <place> <intent> --file <body>`. Then `next` again. When `source` is null, there is no recorded body, so write the whole script.
7. `action` is `answer`: ask the person. Record the reply with `python -m prove answer <place> <question> --text "..."`. Then `next` again. An open question blocks a write.
8. `action` is `blocked` or `done`: stop and read `reason`. A missing script path means set `claim.props.path` to a `game.` script path, then run `plan` again. Any other `blocked` needs the person. `done` means no goal is open.
9. Save the Roblox place only after the person asks. Use `agent.save()`. The runtime does not call it. Publishing stays a separate confirmation.

Field lists live in `protocols/`. Status words live in `graph/README.md`. Verdicts live in `docs/integration/roblox-studio-adapter.md`. Playbooks live in `docs/playbooks/`. An action absent from `docs/runtime.md` is not started by `run`.
