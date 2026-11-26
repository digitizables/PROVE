# Agents

PROVE work starts here.

1. Read [skills/prove/SKILL.md](skills/prove/SKILL.md) and follow it for the session.
2. Field lists live in [protocols/](protocols/README.md). Status meanings live in [graph/README.md](graph/README.md). Adapter calls live in [workers/catalog.md](workers/catalog.md). Studio rules and verdicts live in [docs/integration/roblox-studio-adapter.md](docs/integration/roblox-studio-adapter.md).
3. Keep one intent in status `active` for a place file. Finish it, or mark it `blocked` and stop, before activating another.
4. Call Studio only through `roblox-studio-adapter` 0.1.1 or newer. Open the place the person named.
5. Write the full evidence record under `evidence/runs/` (gitignored). Store an evidence node on the place graph whose `props.path` points at that file.
6. Commit the place graph when the person wants the model shared. Leave `evidence/runs/` and `graph/places/*.local.json` uncommitted. They hold machine paths and Studio window ids.

The design narrative is [docs/architecture.md](docs/architecture.md). The sample walkthrough is [examples/sample-goal.md](examples/sample-goal.md).
