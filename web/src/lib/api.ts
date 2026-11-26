export type PlaceFile = {
  file: string;
  id: string;
  title: string;
  display_name: string;
  updated_at: string;
};

export type Question = { id: string; text: string };

export type ScriptRow = { id: string; path: string; class_name: string };

export type Brief = {
  action: string;
  place_id: string;
  questions: Question[];
  open_goals: string[];
  intent?: string;
  worker?: string;
  intent_action?: string;
  summary?: string;
  reason?: string;
  path?: string;
  class_name?: string;
  source_bytes?: number;
  source_sha256?: string;
  source_evidence?: string;
  scripts?: ScriptRow[];
};

export type Goal = {
  id: string;
  name: string;
  status: string;
  statement: string;
};

export type Probe = {
  id?: string;
  expression?: string;
  datamodel?: string;
  equals?: unknown;
};

export type CheckDetail = {
  seconds?: number;
  screenshot?: boolean;
  forbid_errors?: boolean;
  expect_contains?: string[];
  expect_absent?: string[];
  probes?: Probe[];
};

export type Claim = {
  id: string;
  name: string;
  status: string;
  statement: string;
  goal_id: string;
  path: string;
  class_name: string;
  check: string;
  check_detail: CheckDetail | null;
};

export type IntentRow = {
  id: string;
  name: string;
  status: string;
  worker: string;
  action: string;
  summary: string;
  order: number | null;
  after: string | null;
  verdict: string;
  evidence_summary: string;
};

export type Board = {
  file: string;
  id: string;
  title: string;
  updated_at: string;
  display_name: string;
  place_id: string | null;
  universe_id: string | null;
  active_intent: string | null;
  next_intent: string | null;
  brief: Brief;
  goals: Goal[];
  claims: Claim[];
  intents: IntentRow[];
};

export type Evidence = {
  intent_id: string;
  missing: boolean;
  verdict: string;
  summary: string;
  limits: string;
  captured_at: string;
  observations: { kind: string; text: string }[];
  checks: { id: string; passed: boolean | null; detail: string }[];
};

export type Mutation = {
  ok: boolean;
  code?: number;
  lines: string[];
  board: Board;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const payload = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error || `Board request failed (${response.status})`);
  }
  return payload;
}

export function getPlaces(): Promise<{ places: PlaceFile[] }> {
  return request("/api/places");
}

export function getBoard(file: string): Promise<Board> {
  return request(`/api/board?file=${encodeURIComponent(file)}`);
}

export function getEvidence(file: string, intent: string): Promise<Evidence> {
  const query = new URLSearchParams({ file, intent });
  return request(`/api/evidence?${query}`);
}

export function postJson(path: string, body: Record<string, unknown>): Promise<Mutation> {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
