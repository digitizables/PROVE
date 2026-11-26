# Playbook: verify a change

Use this when a goal names a behavior Output, the tree, or a screenshot can decide.

1. If the script or instance the check depends on is `unverified` or `stale`, activate a read intent first. `props.after` on the verify intent names that read.
2. A write intent, when one is required, is its own intent. It runs in Edit. `must_not` lists the scripts and instances that stay untouched.
3. The verify intent uses the `playtest` worker unless the question is a still or a motion. A still is `capture`. Motion, timing, stutter, or flicker is `capture` with `playtest.record`.
4. `inputs` carries `seconds`, `expect_contains`, and `expect_absent`. `done_when` names the verdict that completes the intent.
5. The worker stores `evidence_record(...)` on the result as `evidence.studio`, then applies the verdict rules in `docs/integration/roblox-studio-adapter.md`.
6. On `pass`, the patch sets the checked claim to `supported` and the intent to `done`. On `fail`, the claim becomes `contradicted` and the intent is `done`. The failure playbook cuts the next intent. On `blocked`, the intent is `blocked` and the claim stays. On `inconclusive`, the intent is `done`, the evidence node is `inconclusive`, and the claim stays.

`change_and_verify` is appropriate when one intent both writes a small script and plays. The intent's `must_not` still lists everything outside that write. The stored object is `result["evidence"]`.
