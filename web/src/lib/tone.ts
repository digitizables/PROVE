export function tone(status: string | null | undefined): string {
  if (!status) return "muted";
  if (["pass", "supported", "done", "ok"].includes(status)) return "ok";
  if (["fail", "contradicted", "blocked", "answer"].includes(status)) return "danger";
  if (["active", "run", "fill", "plan"].includes(status)) return "accent";
  return "muted";
}
