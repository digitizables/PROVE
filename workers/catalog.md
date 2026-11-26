# Worker catalog

Each row is the adapter surface for that worker. Session setup (`RobloxStudio.connect`, `close`) is available to every Studio worker and is described in `docs/integration/roblox-studio-adapter.md`. The `graph` worker has no session.

Paths, play mode, and save rules are in that integration doc. This table is only the method list.

The runtime executes five actions: `explore` `overview`, `script` `read_source`, `script` `write_source`, `playtest` `verify_output`, and `playtest` `change_and_verify`. `verify_output` stops a play already running, then calls `playtest.run`, so the console delta belongs to that intent. `docs/runtime.md` is that command list. `read_source`, `write_source`, and `change_and_verify` set `source_sha256` on the script node and store the source text in the local worker-result file. `overview` marks a script `observed` and leaves an existing hash as it is.

| Worker | Adapter methods | Writes the place? |
| --- | --- | --- |
| `explore` | `studios`, `playtest.state`, `loop.explore`, `datamodel.overview`, `datamodel.tree`, `datamodel.walk`, `datamodel.inspect`, `scripts.find` | Service and script nodes from what those calls returned. An existing `source_sha256` stays. `overview` does not add one |
| `script` | `scripts.find`, `scripts.grep`, `scripts.read`, `scripts.write`, `scripts.replace` | `source_sha256` on read and on write. A write intent names the path in `inputs` |
| `datamodel` | `datamodel.inspect`, `datamodel.read_properties`, `datamodel.apply`, `datamodel.destroy` | Instance nodes for paths it created or deleted. `apply` does not set `Source` |
| `luau` | `luau.query`, `luau.run` | Observations in the evidence file. A query result can set a property on a node the intent names |
| `playtest` | `playtest.state`, `playtest.run`, `playtest.console`, `evidence_record` | The evidence node. `run` stops play when `stop` is true (the default) |
| `capture` | `capture.screenshot`, `playtest.record`, `playtest.start`, `playtest.stop` | Artifact paths on the evidence node. `record` leaves play running, so the intent's `must_not` includes the following stop or the worker calls `playtest.stop` before it returns |
| `input` | `input.walk_to`, `input.press`, `input.type_text`, `input.click`, `playtest.start`, `playtest.state` | Observations. Client playtest only. The worker stops play before returning so the next edit intent starts in Edit |
| `docs` | `skills.list`, `skills.ensure`, `skills.load`, `docs.latest_features`, `docs.search`, `docs.read`, `docs.engine_class` | No Studio instances. Notes land in the evidence summary |
| `assets` | `assets.search`, `assets.insert`, `assets.store_image`, `assets.generate_mesh`, `assets.generate_material`, `assets.generate_procedural_model`, `assets.wait_job` | Instance path the tool inserted, once `wait_job` has finished. `generate_material` does not assign the variant. A follow-up `datamodel` intent sets `Material` and `MaterialVariant` |
| `graph` | none | Service, instance, script, and system nodes from evidence files the intent names |

`agent.call` is reserved for a tool the catalog has not wrapped yet. The intent `inputs.tool` names it, and the evidence record stores the raw text excerpt. A loop does not use `subagent` or `agent.feedback`.

Long generations use `async` and `assets.wait_job`. `auto_setup_avatar` and `generate_scene` stay off this list until an intent names them and the person has agreed to the wait. Call those through `agent.call` with the timeouts in the adapter catalog.
