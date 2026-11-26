<script lang="ts">
  import type { Board } from "./api";
  import { tone } from "./tone";

  let {
    board,
    busy = false,
    onplan,
    onanswer,
  }: {
    board: Board;
    busy?: boolean;
    onplan: () => void;
    onanswer: (question: string, text: string) => void;
  } = $props();

  let answerText = $state("");
  let answerFor = $state("");

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

  function submitAnswer(event: SubmitEvent) {
    event.preventDefault();
    const question = answerFor || board.brief.questions[0]?.id || "";
    if (!question || !answerText.trim()) return;
    onanswer(question, answerText.trim());
    answerText = "";
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
    {/if}
    {#if command}
      <div class="command mono">{command}</div>
      {#if board.brief.action === "run"}
        <p class="action-copy">Run this in the terminal. A verify stops a play that is already running.</p>
      {:else if board.brief.action === "fill"}
        <p class="action-copy">
          The current body is {board.brief.source_bytes ?? 0} bytes
          {#if board.brief.source_sha256}
            · <span class="mono">{board.brief.source_sha256}</span>
          {/if}
        </p>
      {/if}
    {/if}
    <div class="kv">
      <div><span class="k">Active intent</span><span class="v mono">{board.active_intent || "none"}</span></div>
      <div><span class="k">Next intent</span><span class="v mono">{board.next_intent || "none"}</span></div>
      <div><span class="k">Studio name</span><span class="v">{board.display_name || "—"}</span></div>
      <div><span class="k">Place id</span><span class="v mono">{board.place_id || "—"}</span></div>
      <div><span class="k">Universe id</span><span class="v mono">{board.universe_id || "—"}</span></div>
      <div><span class="k">Updated</span><span class="v mono">{board.updated_at || "—"}</span></div>
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
    {#if board.brief.scripts?.length}
      <div class="form-pad">
        <h3>Observed scripts</h3>
        {#each board.brief.scripts as script}
          <p class="note mono">{script.id} {script.path} {script.class_name}</p>
        {/each}
      </div>
    {/if}
  </div>
</div>
