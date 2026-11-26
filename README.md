# PROVE

**P**ersistent **R**oblox **O**rchestration and **V**erification **E**ngine.

PROVE keeps a shared, checkable model of a Roblox place and turns a goal into short intents that a worker can finish. Workers call [roblox-studio-adapter](https://github.com/digitizables/roblox-studio-adapter) to run real Studio tools: inspect the DataModel, edit scripts, playtest, capture the viewport, and read Output. Each run writes an evidence record. The next intent starts from that record.

A person sets the goal, chooses the Studio window when several are open, and decides when to save. PROVE is a collaboration between people and agents. The repository holds the model and the protocol. It does not ship an autonomous agent that owns the game.

This tree is the foundation: contracts, playbooks, and a sample place. There is no orchestration runtime yet. A future Python package should import the adapter and follow the contracts in `protocols/`.

PROVE is not affiliated with Roblox Corporation. Roblox, Roblox Studio, and Luau are trademarks of their owners.

## Loop

```
place graph + open goal
        |
        v
     planner  --->  one short intent
        ^                 |
        |                 v
   evidence node      worker
        ^                 |
        |                 v
        +-------- roblox-studio-adapter ---> Studio
```

1. The place graph says what is believed, what is unverified, and which intent is active.
2. The planner adds one intent: one worker, one action, one `done_when`.
3. The worker calls the adapter methods listed for it in `workers/catalog.md`.
4. The worker writes a `prove.evidence/1` record and a graph patch.
5. The graph absorbs the patch. The planner reads it before emitting the next intent.

## How an agent should start

1. Read [AGENTS.md](AGENTS.md), then [skills/prove/SKILL.md](skills/prove/SKILL.md).
2. Read the place file. The sample is [graph/places/example.place.json](graph/places/example.place.json).
3. If an intent has status `active`, finish that intent or stop. Leave a second intent at `proposed`.
4. Follow [docs/integration/roblox-studio-adapter.md](docs/integration/roblox-studio-adapter.md) before any Studio call.
5. Write evidence under `evidence/runs/` on the machine. Commit the place graph when the person wants the model shared. Leave run files and `*.local.json` place files uncommitted.

## What a person does

- Names the goal in language a playtest or a read can decide.
- Tells the agent which Studio window to use when more than one is open.
- Asks for a save when the place should be written to disk or to Roblox. The adapter save never publishes.
- Accepts or drops a claim after reading the evidence summary.

## Layout

```
AGENTS.md                         entry for an agent session
skills/prove/SKILL.md             session checklist
docs/architecture.md              why the pieces exist
docs/integration/                 adapter boundary, verdicts, safety
docs/playbooks/                   explore, verify, iterate
protocols/                        JSON Schemas (the field lists)
graph/                            place files and status vocabulary
planner/                          how a goal becomes intents
workers/                          which adapter calls each worker may make
evidence/                         envelope, sample record, local runs
studio/                           pointer at the adapter boundary
examples/sample-goal.md           one goal walked through the sample place
src/                              reserved for a future runtime
```

## Adapter

Workers need `roblox-studio-adapter` **0.1.1** or newer. That version writes `roblox-studio-adapter.evidence/1` from a playtest, including named `expect_contains` and `expect_absent` checks. On this machine the checkout is the sibling folder `../roblox-studio-adapter`. Install and connection checks live in that repository.

## License

[MIT](LICENSE).
