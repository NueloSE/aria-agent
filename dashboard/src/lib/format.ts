export function usd(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v == null) return "—";
  return `${v.toFixed(digits)}%`;
}

export function signedPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function signedUsd(v: number | null | undefined): string {
  if (v == null) return "—";
  const s = Math.abs(v).toLocaleString("en-US", { style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${v >= 0 ? "+" : "−"}${s}`;
}

/** Tailwind text-color token for a PnL number. */
export function toneFor(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-gain" : "text-loss";
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function utcShort(iso: string): string {
  return new Date(iso).toISOString().slice(5, 16).replace("T", " ") + " UTC";
}

export function shortAddr(addr: string): string {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}
