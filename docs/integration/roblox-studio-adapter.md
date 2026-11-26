# roblox-studio-adapter

Workers talk to Studio through [roblox-studio-adapter](https://github.com/digitizables/roblox-studio-adapter) **0.1.1** or newer. On this machine the checkout is `../roblox-studio-adapter`. The adapter launches Studio's own `mcp.bat`. PROVE does not open a second MCP transport and does not prefix tool names with `Roblox_Studio__`.

The adapter's `docs/agent-playbook.md` is the authority for Studio behavior. If this file and that playbook disagree about a tool, the playbook and the adapter code win. This file is the PROVE boundary: which calls are allowed, how a result becomes evidence, and when to stop for a person.

## Session

```python
from roblox_studio_adapter import RobloxStudio
from roblox_studio_adapter.evidence import evidence_record

with RobloxStudio.connect(name_contains=display_name) as agent:
    report = agent.playtest.run(
        seconds=3,
        screenshot=False,
        expect_contains=["hello from the agent"],
        expect_absent=["hello failed"],
    )
    studio = evidence_record(
        report,
        studio_id=agent.session.studio_id,
        intent_id=intent_id,
    )
```

- `connect()` raises `AmbiguousStudioError` when several windows are open and the selector matches none or more than one. Mark the intent `blocked` and ask the person. The place file stores `identity.display_name`, `place_id`, or `file_name`. It does not store `studio_id`. That id changes when Studio restarts. The evidence record may store it because the run file stays local.
- One `RobloxStudio` is one thread and one in-flight call. A second worker is a second connection.
- `agent.context.brief()` is session memory for the model. The place graph is the memory that survives the process.
- `agent.loop.change_and_verify(..., intent_id=intent_id)` returns `result["evidence"]` already filled in. `result["playtest"]` is still a Python `PlaytestReport`. Persist the evidence dict.

The method each worker may call is `workers/catalog.md`.

## Playtest evidence

`studio` on a `prove.evidence/1` record, when the worker played, is `roblox-studio-adapter.evidence/1`. The field list is the adapter file `docs/evidence.schema.json`. PROVE adds the envelope in `protocols/evidence.schema.json` and does not copy that field list.

Named checks:

| Adapter check | Meaning |
| --- | --- |
| `output.error_free` | The console delta had no error lines. Present when `forbid_errors` is true |
| `output.contains.N` | The delta contained `expect_contains[N]` |
| `output.absent.N` | The delta omitted `expect_absent[N]` |

`passed` null means the run was an observation (`forbid_errors` false and both lists empty).

`playtest.record` returns `status` (`completed`, `partial`, or `unknown`), `recording_id`, artifact paths, and warnings. Use it when the question is motion, timing, stutter, or flicker. A still question uses `capture.screenshot`. `partial` means the capture ended early.

## Verdict rules

Apply these when writing `prove.evidence/1.verdict`. The claim status changes only through the graph patch, using the words in `graph/README.md`.

| Situation | Verdict |
| --- | --- |
| `studio.passed` is true and `studio.console.reset` is false | `pass` |
| `studio.passed` is false | `fail` |
| `studio.passed` is null | `inconclusive` |
| `studio.console.reset` is true | `inconclusive`, including when `passed` is true. The checks saw the whole later log |
| The worker needs the person (`AmbiguousStudioError`, `NeedsUserAction`, `PermissionDenied`, high-risk confirmation) | `blocked` |
| A mutation raised `AmbiguousOutcome` or a mutation `TimeoutError` | `inconclusive`. The edit may already be in the place |

A `pass` may set the claim the intent checks to `supported`. A `fail` may set it to `contradicted`. `inconclusive` and `blocked` leave the claim status as it was.

## Safety

- Edit in Edit mode. `scripts.write` stops a running playtest because `multi_edit` is Edit-only. Play-mode instances disappear on stop.
- Script paths look like `game.ServerScriptService.Hello`. Tree and inspect paths look like `Workspace.Baseplate`.
- After `AmbiguousOutcome` or a mutation timeout, the next intent reads the place. The worker does not send the write again inside the failed intent.
- `agent.save()` only after the person asks. It never publishes. `NeedsUserAction` blocks the intent and the message goes to the person.
- Open Cloud publish, bans, secrets, and data-store writes go through `agent.cloud.invoke` only after the person confirms, with `allow_high_risk=True`. A 403 is `PermissionDenied`. Tell the person which scope is off.
- `agent.feedback` sends text to Roblox. A normal PROVE loop does not call it.
- DataStore and MemoryStore calls inside `execute_luau` hit the live game when those scopes are on.

## Adapter follow-ups

These would strengthen the next evidence loop. They are not in 0.1.1.

1. An evidence kind for `AmbiguousOutcome` that records the tool name and tells the next intent to read before any rewrite.
2. Playtest probes: Luau expressions run on Server and on Client before `run` stops, stored on the same evidence record. Today a worker that needs both copies has to call them itself, and stop then deletes the runtime DataModel.
3. A tighter error classification. `output.error_free` is a heuristic over Output text. A goal that cares about one message should pass that message in `expect_contains` or `expect_absent`.

Solo play is a Studio MCP limit (`start_stop_play`). Team Test and multi-client sessions are outside the adapter until Studio exposes them.
