<script lang="ts">
  import type { Board, Claim } from "./api";
  import { tone } from "./tone";

  let {
    board,
    busy = false,
    ongoal,
    onbind,
  }: {
    board: Board;
    busy?: boolean;
    ongoal: (body: Record<string, unknown>) => void;
    onbind: (body: Record<string, unknown>) => void;
  } = $props();

  let selected = $state("");
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

  let seenFile = "";
  $effect(() => {
    if (board.file === seenFile) return;
    seenFile = board.file;
    selected = "";
  });

  function pick(row: Claim) {
    selected = row.id;
    bindScript = row.path;
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

  function probeText(row: Claim): string {
    const probes = row.check_detail?.probes ?? [];
    return probes
      .map((item) => {
        const equals = item.equals === undefined ? "" : ` equals ${JSON.stringify(item.equals)}`;
        return `${item.id ?? "probe"} ${item.datamodel ?? ""}\n${item.expression ?? ""}${equals}`;
      })
      .join("\n\n");
  }
</script>

<div class="surface">
  <div class="heading">
    <div>
      <h2>Goals</h2>
      <p>{board.goals.length} goals · {board.claims.length} claims</p>
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
            <th>Check</th>
          </tr>
        </thead>
        <tbody>
          {#each board.claims as row}
            <tr class:selected={row.id === selected} onclick={() => pick(row)}>
              <td>
                <div>{row.name || row.id}</div>
                <div class="tone-muted">{row.statement}</div>
              </td>
              <td class={"tone-" + tone(row.status)}>{row.status}</td>
              <td class="mono path">{row.path || "—"}</td>
              <td class="mono">{row.check || "—"}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if claim}
      <div class="detail mono">
        <h3 class={"tone-" + tone(claim.status)}>{claim.id} · {claim.status}</h3>
        {claim.statement}
        {#if claim.path}
          {"\n"}{claim.path}
        {/if}
        {#if probeText(claim)}
          {"\n\n"}{probeText(claim)}
        {/if}
      </div>
    {/if}
    <div class="form-pad">
      <div class="form-grid">
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
      </div>
    </div>
  </div>
</div>
