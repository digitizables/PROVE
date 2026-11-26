# Playbook: iterate on a failure

Use this when the latest evidence verdict is `fail` or `inconclusive`. `python -m prove plan` follows these steps and does not call Studio.

1. Read `failures`, `checks`, and `console.reset` from the evidence file. Quote the check id in the next intent's summary.
2. When the verdict is `inconclusive` because `console.reset` is true, the next intent is a playtest that snapshots Output again. The previous `passed` flag is not a claim.
3. When the adapter raised `AmbiguousOutcome` or a mutation timeout, the next intent is a read of the script or instance that was being written. A rewrite waits until that read is `done`.
4. When a check failed, cut one intent that addresses that check. A second failure stays on the claim until this one is re-verified.
5. Re-run the same verify intent shape (new id, `props.after` pointing at the fix) after the fix intent is `done`.
6. Three failed verifies of the same claim with no new observation: mark the intent `blocked` and ask the person. The graph keeps the failed evidence nodes.

The worker that failed does not call the adapter again inside the same intent.
