# Workers

A worker executes one active intent and returns one `prove.worker-result/1` document (`protocols/worker-result.schema.json`).

The catalog in `catalog.md` is the list of adapter methods that worker may call. A method absent from the row is outside the intent.

## Result

- `evidence` is the PROVE envelope. Playtest workers set `evidence.studio` to the adapter record from `evidence_record` or from `change_and_verify(...)["evidence"]`.
- `graph_patch` is the only change the worker makes to the place file. The session applies it after the result file is written.
- A Studio worker's patch may add the evidence node for this intent, the `supports` or `contradicts` edge, and `set_status` for this intent and the claims it `checks`.
- A `graph` worker's patch may add and update service, instance, script, and system nodes from evidence that already exists. It does not call Studio.
- `follow_ups` are intent objects with status `proposed`. The session copies them onto the graph and does not run them in this turn.

## Hashes

A script read or write sets `props.source_sha256` to the SHA-256 hex of the source UTF-8. The adapter parser has already removed the line-number prefixes. The place file stores that hash and does not store the body. The worker-result file stores the body as observations `script_path`, `source_sha256`, and `source`. After a successful write, the intent on the place graph no longer has `inputs.source`.

## Errors from the adapter

| Exception | Worker result |
| --- | --- |
| `AmbiguousStudioError`, `NeedsUserAction`, `PermissionDenied` | verdict `blocked`, intent status `blocked`, summary includes the exception message |
| `AmbiguousOutcome`, mutation `TimeoutError` | verdict `inconclusive`, intent status `done`, follow-up is a read of the target |
| `ModeError` | verdict `fail`. The follow-up either stops the playtest or passes the datamodel named in the error |
| `UnyieldingLuau` | verdict `fail`. The follow-up splits the snippet and yields. The same snippet is not sent again |
