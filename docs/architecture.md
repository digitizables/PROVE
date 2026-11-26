# Architecture

PROVE is a shared model plus a short loop. The model survives from one agent session to the next. The loop is small enough that a later session can check the previous session's work.

## Pieces

| Piece | Role | Persistent? |
| --- | --- | --- |
| Place graph | Instances, scripts, systems, goals, intents, claims, evidence pointers | Yes. One JSON file per place |
| Planner | Reads the graph and adds proposed intents | The intents it adds are stored on the graph |
| Worker | Carries out one intent through the adapter, or updates the graph from evidence already collected | Yes. One worker-result file, then the graph patch |
| Evidence | What Studio (or a graph read) actually returned | The run file is local and holds script source. The graph keeps the pointer, the verdict, the summary, and the hash |
| Adapter | The Studio tool layer (`roblox-studio-adapter`) | Its process memory is the session `Context`. PROVE does not treat that memory as the place model |

`python -m prove` loads a place file, runs one ready intent through the adapter, and writes the graph back. `docs/runtime.md` lists the actions it implements. An action outside that list is a session the agent runs by hand from these files.

## What the graph is for

The DataModel in Studio is the place. The graph is the working agreement about that place: which systems exist, which scripts implement them, which claims have evidence, and which goal is open. A full tree dump is a poor agreement. `search_game_tree` truncates, and most of a dump is services that do not bear on the goal.

The shared graph stores a script's path, class, one-line responsibility, and, after a read or write, a hash of the source. The local worker-result file stores the source text. Run files stay uncommitted. An agent fills the next write from that text and does not call Studio to read it again.

## What an intent is

An intent is one worker and one action with a `done_when` that a later evidence record can decide. "Make combat feel better" is a goal. "Playtest for 3 seconds and require Output to contain `round started`" is an intent.

The planner emits intents. A worker may propose follow-up intents inside its result. Those stay `proposed` until the current result is on the graph.

## Collaboration

Several agents can read one place file. One intent in status `active` is the lock. A second agent that finds an active intent waits, or works on a question that does not touch Studio.

The person owns goals, the choice of Studio window, saves, and publishing. An agent that needs one of those writes a `blocked` intent and stops.

## Where a fact lives

| Fact | File |
| --- | --- |
| Why these pieces exist | this file |
| Session checklist | `skills/prove/SKILL.md` |
| Status words | `graph/README.md` |
| JSON fields | `protocols/` |
| How to cut an intent | `planner/README.md` |
| Which adapter methods a worker calls | `workers/catalog.md` |
| Studio boundary, safety, verdicts | `docs/integration/roblox-studio-adapter.md` |
| Step sequences | `docs/playbooks/` |
