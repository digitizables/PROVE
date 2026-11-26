<script lang="ts">
  import type { Board } from "./api";
  import { tone } from "./tone";
  import { when } from "./when";

  let {
    board,
    busy = false,
    onplan,
    onanswer,
    onopen,
  }: {
    board: Board;
    busy?: boolean;
    onplan: () => void;
    onanswer: (question: string, text: string) => void;
    onopen: (nav: "goals" | "evidence", focus?: { claim?: string; intent?: string }) => void;
  } = $props();

  let answerText = $state("");
  let answerFor = $state("");
  let copied = $state(false);

  $effect(() => {
    const ids = board.brief.questions.map((item) => item.id);
    if (ids.length && !ids.includes(answerFor)) answerFor = ids[0];
  });

  const command = $derived.by(() => {
    const file = `graph/places/${board.file}`;
    const action = board.brief.action;
    if (action === "run" && board.brief.intent) return `python -m prove run ${file}`;
    if (action === "plan") return `python -m prove plan ${file}`;
    if (action === "fill" && board.brief.intent) return `python -m prove fill ${file} ${board.brief.intent} --file BODY`;
    if (action === "answer" && board.brief.questions[0]) {
      return `python -m prove answer ${file} ${board.brief.questions[0].id} --text "..."`;
    }
    return "";
  });

  const latest = $derived(
    [...board.intents].reverse().find((row) => row.verdict) ?? board.intents[board.intents.length - 1] ?? null,
  );

  const doneGoals = $derived(board.goals.filter((goal) => goal.status === "done"));

  function submitAnswer(event: SubmitEvent) {
    event.preventDefault();
    const question = answerFor || board.brief.questions[0]?.id || "";
    if (!question || !answerText.trim()) return;
    onanswer(question, answerText.trim());
    answerText = "";
  }

  async function copyCommand() {
    if (!command) return;
    await navigator.clipboard.writeText(command);
    copied = true;
    setTimeout(() => (copied = false), 1200);
  }
</script>

<div class="surface">
  <div class="heading">
    <div>
      <h2>Place</h2>
      <p>{board.display_name || board.title}</p>
    </div>
    <div class="heading-actions">
      <button class="ghost-btn" type="button" disabled={busy} onclick={onplan}>Plan</button>
    </div>
  </div>
  <div class="pane-body">
    <div class="action-line">
      <span class={"tone-" + tone(board.brief.action)}>{board.brief.action}</span>
      {#if board.brief.intent}
        <span class="mono tone-muted">{board.brief.intent}</span>
      {/if}
    </div>
    {#if board.brief.summary || board.brief.reason}
      <p class="action-copy">{board.brief.summary || board.brief.reason}</p>
    {:else if board.brief.action === "done" && doneGoals.length === 0}
      <p class="action-copy">No open goal.</p>
    {/if}
    {#if command}
      <div class="command-row">
        <div class="command mono">{command}</div>
        <button class="ghost-btn" type="button" onclick={copyCommand}>{copied ? "Copied" : "Copy"}</button>
      </div>
      {#if board.brief.action === "run"}
        <p class="action-copy">Run this in the terminal. A verify stops a play that is already running.</p>
      {:else if board.brief.action === "plan"}
        <p class="action-copy">Plan writes the next intent into this place file.</p>
      {:else if board.brief.action === "fill"}
        <p class="action-copy">
          The current body is {board.brief.source_bytes ?? 0} bytes
          {#if board.brief.source_sha256}
            · <span class="mono">{board.brief.source_sha256}</span>
          {/if}
        </p>
      {/if}
    {/if}
    <div class="meta-row">
      {#if board.display_name}<span class="pill">{board.display_name}</span>{/if}
      {#if board.place_id}<span class="pill mono">{board.place_id}</span>{/if}
      {#if board.universe_id}<span class="pill mono">{board.universe_id}</span>{/if}
      <span class="pill" title={board.updated_at}>{when(board.updated_at)}</span>
      {#if board.active_intent}<span class="pill mono">active {board.active_intent}</span>{/if}
    </div>

    {#if board.brief.questions.length}
      <div class="form-pad">
        <h3>Questions</h3>
        <form onsubmit={submitAnswer}>
          {#each board.brief.questions as question}
            <p class="note"><span class="mono">{question.id}</span> — {question.text}</p>
          {/each}
          <label class="field">
            Question
            <select bind:value={answerFor}>
              {#each board.brief.questions as question}
                <option value={question.id}>{question.id}</option>
              {/each}
            </select>
          </label>
          <label class="field">
            Answer
            <input bind:value={answerText} />
          </label>
          <button class="primary-btn" type="submit" disabled={busy || !answerText.trim()}>Answer</button>
        </form>
      </div>
    {/if}

    {#if board.goals.length}
      <h3 class="section-label">Goals</h3>
      <table class="sessions">
        <tbody>
          {#each board.goals as goal}
            <tr class="clickable" onclick={() => onopen("goals")}>
              <td>
                <div class="goal-line">
                  <span class={"pill pill-" + tone(goal.status)}>{goal.status}</span>
                  <strong>{goal.name || goal.id}</strong>
                  <span class="statement">{goal.statement}</span>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if board.claims.length}
      <h3 class="section-label">Claims</h3>
      <table class="sessions">
        <tbody>
          {#each board.claims as claim}
            <tr class="clickable" onclick={() => onopen("goals", { claim: claim.id })}>
              <td>
                <div class="goal-line">
                  <span class={"pill pill-" + tone(claim.status)}>{claim.status}</span>
                  <strong>{claim.name || claim.id}</strong>
                  {#if claim.check}<span class="pill check-chip" title={claim.check}>{claim.check}</span>{/if}
                </div>
                {#if claim.statement}<div class="tone-muted">{claim.statement}</div>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if latest}
      <h3 class="section-label">Latest evidence</h3>
      <table class="sessions">
        <tbody>
          <tr class="clickable" onclick={() => onopen("evidence", { intent: latest.id })}>
            <td class="mono">{latest.order ?? "—"}</td>
            <td class="mono">{latest.id}</td>
            <td><span class={"pill pill-" + tone(latest.verdict || latest.status)}>{latest.verdict || latest.status}</span></td>
            <td>{latest.evidence_summary || latest.summary}</td>
          </tr>
        </tbody>
      </table>
    {/if}

    {#if board.brief.scripts?.length}
      <h3 class="section-label">Observed scripts</h3>
      {#each board.brief.scripts as script}
        <p class="note mono">{script.id} {script.path} {script.class_name}</p>
      {/each}
    {/if}
  </div>
</div>
