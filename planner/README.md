# Planner

The planner reads one place file and one open goal. It appends intent nodes. It does not call the adapter.

`python -m prove plan <place>` is that step. It saves the place only when the graph changes. `example.place.json` is left unchanged. The command is described in `docs/runtime.md`.

An intent is valid when it matches `protocols/intent.schema.json`.

## Cutting an intent

- One worker, one `action`, one `done_when`.
- `summary` is one line, at most 200 characters.
- `inputs` holds only the arguments that worker's catalog row accepts.
- `must_not` lists the writes, saves, and systems outside this intent.
- `props.after` is null or the id of an intent that has to be `done` first.
- `props.order` is the sequence inside one goal. The session activates the lowest `order` whose `after` is satisfied and whose status is `proposed`.
- A read or explore comes before a write when the nodes the write would touch are `unverified` or `stale`.
- A verify comes after the write it checks, as its own intent, unless the person asked for one `change_and_verify` intent. That combined intent's `must_not` still names everything outside the write.
- A save intent exists only when the goal text says the person asked to save.

## After evidence

- `pass`: leave the goal `open` until every acceptance claim is `supported`, then set the goal `done`.
- No verify yet: when an `unverified` claim has `props.goal_id` and `props.check`, `plan` appends a `verify_output` that copies that check. A probe list is a check on its own. The script comes from `props.path` or from an `about` edge to the script or its system. An `unverified` or `stale` script, or an observed script with no local source text, is read first. The verify's `after` names that read. No script path, and no finished `overview` for the goal, appends one `overview`. A finished overview with still no path reports `need script path for <claim>` and does not explore again.
- `fail` or `inconclusive`: follow `docs/playbooks/iterate-on-failure.md`. Add the follow-up as `proposed`. Do not activate it in the same breath as applying the patch. `plan` does this. A failed check becomes a `write_source` intent whose `inputs.source` is still empty, then a `verify_output` whose `after` names that write. A `stale` or `unverified` script is read first. An observed script is read first when no local evidence file has its source text. `console.reset` becomes one more `verify_output` and leaves the claim status as it is.
- `blocked`: stop. The question node or the intent summary tells the person what is needed. Three verifies of the same claim with the same failure add a blocked intent and an open question.

Follow-ups proposed by a worker land as intent nodes with status `proposed`. The planner may reject one by setting it `rejected` and writing the reason on `props.reason`. The worker does not activate its own follow-up.
