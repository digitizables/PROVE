# Protocols

These JSON Schemas are the field lists. Prose next to them explains when to write each field. When you add a field, change the schema and the one doc that owns the meaning.

| Schema | Id | Meaning lives in |
| --- | --- | --- |
| `place.schema.json` | `prove.place/1` | `graph/README.md` |
| `intent.schema.json` | `prove.intent/1` | `planner/README.md` |
| `evidence.schema.json` | `prove.evidence/1` | `evidence/README.md` and the verdict table in `docs/integration/roblox-studio-adapter.md` |
| `worker-result.schema.json` | `prove.worker-result/1` | `workers/README.md` |

`evidence.studio` is an adapter record. Its field list is `roblox-studio-adapter` `docs/evidence.schema.json` (`roblox-studio-adapter.evidence/1`). It is not restated here.

The worker enum is `intent.schema.json`. The methods for each worker are `workers/catalog.md`.
