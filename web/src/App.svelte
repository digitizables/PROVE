<script lang="ts">
  import { onMount } from "svelte";
  import { getBoard, getPlaces, postJson, type Board, type PlaceFile } from "./lib/api";
  import EvidenceView from "./lib/EvidenceView.svelte";
  import GoalsView from "./lib/GoalsView.svelte";
  import PlaceView from "./lib/PlaceView.svelte";

  type NavId = "place" | "goals" | "evidence";

  let nav = $state<NavId>("place");
  let sidebarExpanded = $state(loadExpanded());
  let places = $state<PlaceFile[]>([]);
  let file = $state("");
  let board = $state<Board | null>(null);
  let loadError = $state("");
  let notice = $state("");
  let busy = $state(false);
  let focusClaim = $state("");
  let focusIntent = $state("");
  let focusToken = $state(0);

  function loadExpanded(): boolean {
    try {
      return localStorage.getItem("prove.sidebar") !== "0";
    } catch {
      return true;
    }
  }

  $effect(() => {
    try {
      localStorage.setItem("prove.sidebar", sidebarExpanded ? "1" : "0");
    } catch {
      // The page still works when storage is blocked.
    }
  });

  async function loadPlaces(prefer?: string) {
    const payload = await getPlaces();
    places = payload.places;
    const wanted = prefer || file;
    if (wanted && places.some((item) => item.file === wanted)) {
      file = wanted;
    } else {
      file = places.find((item) => item.file.endsWith(".local.json"))?.file || places[0]?.file || "";
    }
  }

  async function loadBoard(name = file) {
    if (!name) {
      board = null;
      return;
    }
    board = await getBoard(name);
  }

  async function refresh(clearNotice = false) {
    if (clearNotice) notice = "";
    try {
      await loadPlaces(file);
      await loadBoard();
      loadError = "";
    } catch (caught) {
      loadError = caught instanceof Error ? caught.message : "The board did not load";
    }
  }

  function open(next: NavId, focus?: { claim?: string; intent?: string }) {
    focusClaim = focus?.claim || "";
    focusIntent = focus?.intent || "";
    focusToken += 1;
    nav = next;
  }

  async function mutate(path: string, body: Record<string, unknown>) {
    if (!file) return;
    busy = true;
    notice = "";
    try {
      const result = await postJson(path, { file, ...body });
      board = result.board;
      if (result.code && result.code !== 0) {
        notice = result.lines.join(" ");
      }
      await loadPlaces(file);
    } catch (caught) {
      notice = caught instanceof Error ? caught.message : "The board did not save";
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  });
</script>

<div class="app-window">
  <header class="titlebar">
    <div class="title-block">
      <div class="brand">PROVE</div>
      <div class="descriptor">{board?.title || "Place board"}</div>
    </div>
    <div class="title-spacer"></div>
    <select
      class="title-select"
      bind:value={file}
      onchange={() => loadBoard().catch((caught) => (loadError = caught instanceof Error ? caught.message : "The board did not load"))}
    >
      {#if places.length === 0}
        <option value="">No place file</option>
      {/if}
      {#each places as item}
        <option value={item.file}>{item.title || item.file}</option>
      {/each}
    </select>
  </header>

  <div class="shell">
    <aside class="sidebar" class:expanded={sidebarExpanded}>
      <div class="nav-group">
        <button class="nav-item" type="button" title={sidebarExpanded ? "Collapse" : "Expand"} onclick={() => (sidebarExpanded = !sidebarExpanded)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            {#if sidebarExpanded}
              <path d="M15 18l-6-6 6-6" />
            {:else}
              <path d="M9 18l6-6-6-6" />
            {/if}
          </svg>
          <span class="nav-label">Menu</span>
        </button>
        <button class="nav-item" class:active={nav === "place"} type="button" title="Place" onclick={() => (nav = "place")}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /></svg>
          <span class="nav-label">Place</span>
        </button>
        <button class="nav-item" class:active={nav === "goals"} type="button" title="Goals" onclick={() => (nav = "goals")}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" y1="22" x2="4" y2="15" /></svg>
          <span class="nav-label">Goals</span>
        </button>
        <button class="nav-item" class:active={nav === "evidence"} type="button" title="Evidence" onclick={() => (nav = "evidence")}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
          <span class="nav-label">Evidence</span>
        </button>
      </div>
      <div class="sidebar-spacer"></div>
      <button class="nav-item" type="button" title="Refresh" onclick={() => refresh(true)}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
        <span class="nav-label">Refresh</span>
      </button>
    </aside>

    <section class="workspace">
      {#if board}
        {#if nav === "place"}
          <PlaceView {board} {busy} onplan={() => mutate("/api/plan", {})} onanswer={(question, text) => mutate("/api/answer", { question, text })} onopen={open} />
        {:else if nav === "goals"}
          <GoalsView {board} {busy} {focusClaim} {focusToken} ongoal={(body) => mutate("/api/goal", body)} onbind={(body) => mutate("/api/bind", body)} />
        {:else}
          <EvidenceView {board} {focusIntent} {focusToken} />
        {/if}
      {:else}
        <div class="surface">
          <p class="empty">{loadError || "Loading the place board."}</p>
        </div>
      {/if}
      {#if (notice || loadError) && board}
        <p class="error-banner">{notice || loadError}</p>
      {/if}
    </section>
  </div>

  <footer class="footer-bar">
    <span class="mono">{board?.file || "graph/places"}</span>
    <span>local · does not call Studio</span>
  </footer>
</div>
