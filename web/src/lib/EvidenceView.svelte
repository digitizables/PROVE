<script lang="ts">
  import { getEvidence, type Board, type Evidence, type IntentRow } from "./api";
  import { tone } from "./tone";

  let { board }: { board: Board } = $props();

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
              <td class={"tone-" + tone(row.status)}>{row.status}</td>
              <td class={"tone-" + tone(row.verdict)}>{row.verdict || "—"}</td>
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
      <div class="detail mono">
        <h3 class={"tone-" + tone(detail.verdict)}>{detail.intent_id} · {detail.missing ? "no file" : detail.verdict}</h3>
        {detail.summary || "No summary."}
        {#if detail.limits}
          {"\n"}{detail.limits}
        {/if}
        {#each detail.checks as check}
          {"\n"}{check.passed === true ? "pass" : check.passed === false ? "fail" : "open"} {check.id} {check.detail}
        {/each}
        {#each detail.observations as item}
          {"\n"}{item.kind}: {item.text}
        {/each}
      </div>
    {/if}
  </div>
</div>
