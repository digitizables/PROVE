<script lang="ts">
  import { getEvidence, type Board, type Evidence, type IntentRow } from "./api";
  import { tone } from "./tone";
  import { when } from "./when";

  let { board, focusIntent = "", focusToken = 0 }: { board: Board; focusIntent?: string; focusToken?: number } = $props();

  let selected = $state("");
  let detail = $state<Evidence | null>(null);
  let detailError = $state("");

  async function pick(row: IntentRow) {
    selected = row.id;
    detail = null;
    detailError = "";
    try {
      detail = await getEvidence(board.file, row.id);
    } catch (error) {
      detailError = error instanceof Error ? error.message : "Evidence did not load";
    }
  }

  let seenFile = "";
  $effect(() => {
    if (board.file === seenFile) return;
    seenFile = board.file;
    selected = "";
    detail = null;
    detailError = "";
  });

  let seenToken = 0;
  $effect(() => {
    if (!focusIntent || focusToken === seenToken) return;
    seenToken = focusToken;
    const row = board.intents.find((item) => item.id === focusIntent);
    if (row) pick(row);
  });

  function mark(passed: boolean | null): string {
    if (passed === true) return "pass";
    if (passed === false) return "fail";
    return "open";
  }
</script>

<div class="surface">
  <div class="heading">
    <div>
      <h2>Evidence</h2>
      <p>{board.intents.length} intents</p>
    </div>
  </div>
  <div class="pane-body flush">
    {#if board.intents.length === 0}
      <p class="empty">No intents yet.</p>
    {:else}
      <table class="sessions">
        <thead>
          <tr>
            <th>Order</th>
            <th>Intent</th>
            <th>Action</th>
            <th>Status</th>
            <th>Verdict</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {#each board.intents as row}
            <tr class:selected={row.id === selected} onclick={() => pick(row)}>
              <td class="mono">{row.order ?? "—"}</td>
              <td class="mono">{row.id}</td>
              <td>{row.worker} {row.action}</td>
              <td><span class={"pill pill-" + tone(row.status)}>{row.status}</span></td>
              <td>{#if row.verdict}<span class={"pill pill-" + tone(row.verdict)}>{row.verdict}</span>{:else}—{/if}</td>
              <td>{row.evidence_summary || row.summary}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if detailError}
      <p class="error-banner">{detailError}</p>
    {/if}
    {#if detail}
      <div class="detail">
        <h3>
          <span class="mono">{detail.intent_id}</span>
          <span class={"pill pill-" + tone(detail.missing ? "blocked" : detail.verdict)}>{detail.missing ? "no file" : detail.verdict || "open"}</span>
        </h3>
        <p>{detail.summary || "No summary."}</p>
        {#if detail.limits}<p class="tone-muted">{detail.limits}</p>{/if}
        {#if detail.captured_at}<p class="tone-muted">{when(detail.captured_at)}</p>{/if}
        {#each detail.checks as check}
          <div class="obs">
            <span class="k"><span class={"pill pill-" + tone(mark(check.passed))}>{mark(check.passed)}</span></span>
            <span class="mono">{check.id} {check.detail}</span>
          </div>
        {/each}
        {#each detail.observations as item}
          <div class="obs">
            <span class="k">{item.kind}</span>
            <span class="mono">{item.text}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
