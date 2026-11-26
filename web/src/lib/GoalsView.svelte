<script lang="ts">
  import type { Board, Claim, Goal } from "./api";
  import { tone } from "./tone";

  let {
    board,
    busy = false,
    focusClaim = "",
    focusToken = 0,
    ongoal,
    onbind,
  }: {
    board: Board;
    busy?: boolean;
    focusClaim?: string;
    focusToken?: number;
    ongoal: (body: Record<string, unknown>) => void;
    onbind: (body: Record<string, unknown>) => void;
  } = $props();

  let selected = $state("");
  let showGoal = $state(false);
  let showBind = $state(false);
  let statement = $state("");
  let goalName = $state("");
  let contains = $state("");
  let absent = $state("");
  let script = $state("");
  let seconds = $state("3");
  let probe = $state("");
  let bindScript = $state("");
  let bindClass = $state("Script");
  let bindContains = $state("");
  let bindProbe = $state("");

  const claim = $derived(board.claims.find((item) => item.id === selected) ?? null);
  const linked = $derived(new Set(board.goals.map((goal) => goal.id)));
  const orphans = $derived(board.claims.filter((item) => !item.goal_id || !linked.has(item.goal_id)));

  let seenFile = "";
  $effect(() => {
    if (board.file === seenFile) return;
    seenFile = board.file;
    selected = "";
    showBind = false;
    showGoal = false;
  });

  let seenToken = 0;
  $effect(() => {
    if (!focusClaim || focusToken === seenToken) return;
    seenToken = focusToken;
    const row = board.claims.find((item) => item.id === focusClaim);
    if (row) pick(row);
  });

  function claimsFor(goal: Goal): Claim[] {
    return board.claims.filter((item) => item.goal_id === goal.id);
  }

  function pick(row: Claim) {
    selected = row.id;
    bindScript = row.path;
    bindClass = row.class_name || "Script";
  }

  function submitGoal(event: SubmitEvent) {
    event.preventDefault();
    ongoal({
      statement,
      name: goalName,
      contains,
      absent,
      script,
      seconds,
      probes: probe,
    });
  }

  function submitBind(event: SubmitEvent) {
    event.preventDefault();
    if (!claim) return;
    onbind({
      claim: claim.id,
      script: bindScript,
      class_name: bindClass,
      contains: bindContains,
      probes: bindProbe,
    });
  }

  function equalsText(value: unknown): string {
    if (value === undefined) return "";
    return `equals ${JSON.stringify(value)}`;
  }
</script>

<div class="surface">
  <div class="heading">
    <div>
      <h2>Goals</h2>
      <p>{board.goals.length} goals · {board.claims.length} claims</p>
    </div>
    <div class="heading-actions">
      <button class="ghost-btn" class:active={showGoal} type="button" onclick={() => (showGoal = !showGoal)}>New goal</button>
      <button class="ghost-btn" class:active={showBind} type="button" disabled={!claim} title={claim ? claim.id : "Select a claim"} onclick={() => (showBind = !showBind)}>
        Bind
      </button>
    </div>
  </div>
  <div class="pane-body flush">
    {#if board.goals.length === 0 && board.claims.length === 0}
      <p class="empty">No goals yet.</p>
    {:else}
      <table class="sessions">
        <thead>
          <tr>
            <th>Claim</th>
            <th>Status</th>
            <th>Script</th>
          </tr>
        </thead>
        <tbody>
          {#each board.goals as goal}
            <tr class="goal-band">
              <td colspan="3">
                <div class="goal-line">
                  <span class={"pill pill-" + tone(goal.status)}>{goal.status}</span>
                  <strong>{goal.name || goal.id}</strong>
                  <span class="statement">{goal.statement}</span>
                </div>
              </td>
            </tr>
            {#each claimsFor(goal) as row}
              <tr class:selected={row.id === selected} onclick={() => pick(row)}>
                <td>
                  <div>{row.name || row.id}</div>
                  <div class="tone-muted">{row.statement}</div>
                  {#if row.check}<span class="pill check-chip" title={row.check}>{row.check}</span>{/if}
                </td>
                <td><span class={"pill pill-" + tone(row.status)}>{row.status}</span></td>
                <td class="mono path">{row.path || "—"}</td>
              </tr>
            {/each}
          {/each}
          {#each orphans as row}
            <tr class:selected={row.id === selected} onclick={() => pick(row)}>
              <td>
                <div>{row.name || row.id}</div>
                <div class="tone-muted">{row.statement}</div>
                {#if row.check}<span class="pill check-chip" title={row.check}>{row.check}</span>{/if}
              </td>
              <td><span class={"pill pill-" + tone(row.status)}>{row.status}</span></td>
              <td class="mono path">{row.path || "—"}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if claim}
      <div class="detail">
        <h3>
          <span class="mono">{claim.id}</span>
          <span class={"pill pill-" + tone(claim.status)}>{claim.status}</span>
        </h3>
        <p>{claim.statement}</p>
        {#if claim.path}<p class="mono path">{claim.path}{#if claim.class_name} · {claim.class_name}{/if}</p>{/if}
        {#each claim.check_detail?.probes ?? [] as item}
          <div class="probe-line">
            <span class="k">{item.id ?? "probe"} {item.datamodel ?? ""}</span>
            <span class="mono">{item.expression ?? ""} {equalsText(item.equals)}</span>
          </div>
        {/each}
        {#if claim.check_detail?.expect_contains?.length}
          <div class="probe-line">
            <span class="k">contains</span>
            <span class="mono">{claim.check_detail.expect_contains.join(", ")}</span>
          </div>
        {/if}
        {#if claim.check_detail?.expect_absent?.length}
          <div class="probe-line">
            <span class="k">absent</span>
            <span class="mono">{claim.check_detail.expect_absent.join(", ")}</span>
          </div>
        {/if}
      </div>
    {/if}
    {#if showGoal || showBind}
      <div class="form-pad">
        <div class="form-grid" class:single={showGoal !== showBind}>
          {#if showGoal}
            <form onsubmit={submitGoal}>
              <h3>New goal</h3>
              <p class="note">Adds one claim. Plan turns it into a read and a verify.</p>
              <label class="field">Statement<input bind:value={statement} required /></label>
              <label class="field">Name<input bind:value={goalName} /></label>
              <label class="field">Contains<input bind:value={contains} /></label>
              <label class="field">Absent<input bind:value={absent} /></label>
              <label class="field">Script<input bind:value={script} placeholder="game.ServerScriptService.Hello" /></label>
              <label class="field">Seconds<input bind:value={seconds} /></label>
              <label class="field">Probe JSON<textarea bind:value={probe} placeholder={'{"id":"present","expression":"true","datamodel":"Server","equals":true}'}></textarea></label>
              <button class="primary-btn" type="submit" disabled={busy || !statement.trim()}>Add goal</button>
            </form>
          {/if}
          {#if showBind}
            <form onsubmit={submitBind}>
              <h3>Bind claim</h3>
              <p class="note">{claim ? claim.id : "Select a claim in the table."}</p>
              <label class="field">Script<input bind:value={bindScript} placeholder="game.ServerScriptService.Hello" /></label>
              <label class="field">
                Class
                <select bind:value={bindClass}>
                  <option>Script</option>
                  <option>LocalScript</option>
                  <option>ModuleScript</option>
                </select>
              </label>
              <label class="field">Contains<input bind:value={bindContains} /></label>
              <label class="field">Probe JSON<textarea bind:value={bindProbe}></textarea></label>
              <button class="primary-btn" type="submit" disabled={busy || !claim}>Bind</button>
            </form>
          {/if}
        </div>
      </div>
    {/if}
  </div>
</div>
