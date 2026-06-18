import { useState } from "react";
import type { Performance, Trade } from "../lib/api";
import { signedPct, signedUsd, timeAgo, toneFor, usd, utcShort } from "../lib/format";
import { ExternalLink } from "lucide-react";

function duration(open: string | null, close: string): string {
  if (!open) return "—";
  const m = (new Date(close).getTime() - new Date(open).getTime()) / 60000;
  if (m < 60) return `${Math.round(m)}m`;
  if (m < 1440) return `${(m / 60).toFixed(1)}h`;
  return `${(m / 1440).toFixed(1)}d`;
}

export function TradesPanel({ perf, trades }: { perf: Performance | null; trades: Trade[] }) {
  const [showSwaps, setShowSwaps] = useState(false);
  const rts = perf?.round_trips ?? [];
  const compliance = trades.filter((t) => t.kind === "compliance").length;

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Closed round-trips
        </span>
        {perf && (
          <span className="font-mono text-xs">
            realized{" "}
            <span className={`font-semibold tabular-nums ${toneFor(perf.realized_pnl_usd)}`}>
              {signedUsd(perf.realized_pnl_usd)}
            </span>
            <span className="text-muted-foreground"> · {perf.wins}W/{perf.losses}L · {compliance} heartbeat{compliance === 1 ? "" : "s"}</span>
          </span>
        )}
      </div>

      {rts.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-muted-foreground">
          No closed trades yet — open positions show above until ARIA exits them.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2 font-medium">Token</th>
                <th className="px-4 py-2 font-medium">In → Out</th>
                <th className="px-4 py-2 text-right font-medium">PnL</th>
                <th className="px-4 py-2 text-right font-medium">Return</th>
                <th className="px-4 py-2 text-right font-medium">Held</th>
                <th className="px-4 py-2 text-right font-medium">Closed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rts.map((rt, i) => (
                <tr key={`${rt.token}-${rt.closed_at}-${i}`}>
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-sm font-semibold">{rt.token}</span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs tabular-nums text-muted-foreground">
                    {usd(rt.usd_in)} → {usd(rt.usd_out)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono text-xs font-semibold tabular-nums ${toneFor(rt.pnl_usd)}`}>
                    {signedUsd(rt.pnl_usd)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono text-xs tabular-nums ${toneFor(rt.pnl_pct)}`}>
                    {signedPct(rt.pnl_pct)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">
                    {duration(rt.opened_at, rt.closed_at)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground" title={utcShort(rt.closed_at)}>
                    {timeAgo(rt.closed_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* raw swap ledger — the old flat list, available but not in the way */}
      <div className="border-t border-border">
        <button
          type="button"
          onClick={() => setShowSwaps((v) => !v)}
          aria-expanded={showSwaps}
          className="w-full px-4 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
        >
          {showSwaps ? "Hide" : "Show"} all swap legs ({trades.length})
        </button>
        {showSwaps && (
          <div className="overflow-x-auto border-t border-border">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-border">
                {trades.map((t) => (
                  <tr key={t.id}>
                    <td className="px-4 py-2 font-mono text-xs text-muted-foreground" title={utcShort(t.timestamp)}>
                      {timeAgo(t.timestamp)}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                        t.kind === "compliance" ? "border-border bg-muted text-muted-foreground" : "border-primary/30 bg-primary/10 text-primary"
                      }`}>{t.kind}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">{t.from_token} → {t.to_token}</td>
                    <td className="px-4 py-2 font-mono text-xs tabular-nums">{t.from_amount ?? "—"}</td>
                    <td className={`px-4 py-2 font-mono text-xs ${
                      t.status === "confirmed" ? "text-gain" : t.status.startsWith("failed") ? "text-loss" : "text-muted-foreground"
                    }`}>{t.status}</td>
                    <td className="px-4 py-2">
                      {t.tx_hash ? (
                        <a href={`https://bscscan.com/tx/${t.tx_hash}`} target="_blank" rel="noreferrer"
                          className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
                          {t.tx_hash.slice(0, 10)}… <ExternalLink size={11} aria-hidden />
                        </a>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
