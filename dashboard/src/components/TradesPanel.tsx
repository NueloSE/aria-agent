import { useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Performance, RoundTrip, Trade } from "../lib/api";
import { signedPct, signedUsd, timeAgo, toneFor, usd, utcShort } from "../lib/format";
import { ExternalLink } from "lucide-react";

function duration(open: string | null, close: string): string {
  if (!open) return "—";
  const m = (new Date(close).getTime() - new Date(open).getTime()) / 60000;
  if (m < 60) return `${Math.round(m)}m`;
  if (m < 1440) return `${(m / 60).toFixed(1)}h`;
  return `${(m / 1440).toFixed(1)}d`;
}

// Shared column template so the header and the virtualized rows stay aligned.
const RT_COLS = "grid grid-cols-[1.1fr_1.6fr_1fr_0.9fr_0.7fr_1fr] items-center gap-2 px-4";

export function TradesPanel({ perf, trades }: { perf: Performance | null; trades: Trade[] }) {
  const [showSwaps, setShowSwaps] = useState(false);
  const rts = perf?.round_trips ?? [];
  const compliance = trades.filter((t) => t.kind === "compliance").length;

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Closed round-trips{rts.length > 0 ? ` · ${rts.length}` : ""}
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
        <RoundTripsTable rts={rts} />
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
        {showSwaps && <SwapLegsTable trades={trades} />}
      </div>
    </div>
  );
}

function RoundTripsTable({ rts }: { rts: RoundTrip[] }) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const v = useVirtualizer({
    count: rts.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 41,
    overscan: 12,
  });

  return (
    <div>
      <div className={`${RT_COLS} border-b border-border py-2 text-[11px] uppercase tracking-wider text-muted-foreground`}>
        <span>Token</span>
        <span>In → Out</span>
        <span className="text-right">PnL</span>
        <span className="text-right">Return</span>
        <span className="text-right">Held</span>
        <span className="text-right">Closed</span>
      </div>
      <div ref={scrollRef} className="max-h-[24rem] overflow-y-auto">
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((vi) => {
            const rt = rts[vi.index];
            return (
              <div
                key={vi.key}
                className={`${RT_COLS} absolute left-0 top-0 w-full border-b border-border py-2.5`}
                style={{ transform: `translateY(${vi.start}px)`, height: 41 }}
              >
                <span className="font-mono text-sm font-semibold">{rt.token}</span>
                <span className="truncate font-mono text-xs tabular-nums text-muted-foreground">
                  {usd(rt.usd_in)} → {usd(rt.usd_out)}
                </span>
                <span className={`text-right font-mono text-xs font-semibold tabular-nums ${toneFor(rt.pnl_usd)}`}>
                  {signedUsd(rt.pnl_usd)}
                </span>
                <span className={`text-right font-mono text-xs tabular-nums ${toneFor(rt.pnl_pct)}`}>
                  {signedPct(rt.pnl_pct)}
                </span>
                <span className="text-right font-mono text-xs text-muted-foreground">
                  {duration(rt.opened_at, rt.closed_at)}
                </span>
                <span className="text-right font-mono text-xs text-muted-foreground" title={utcShort(rt.closed_at)}>
                  {timeAgo(rt.closed_at)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const SWAP_COLS = "grid grid-cols-[0.8fr_0.7fr_1.2fr_0.8fr_0.8fr_1fr] items-center gap-2 px-4";

function SwapLegsTable({ trades }: { trades: Trade[] }) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const v = useVirtualizer({
    count: trades.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 37,
    overscan: 12,
  });

  return (
    <div ref={scrollRef} className="max-h-[20rem] overflow-y-auto border-t border-border">
      <div style={{ height: v.getTotalSize(), position: "relative" }}>
        {v.getVirtualItems().map((vi) => {
          const t = trades[vi.index];
          return (
            <div
              key={vi.key}
              className={`${SWAP_COLS} absolute left-0 top-0 w-full border-b border-border py-2`}
              style={{ transform: `translateY(${vi.start}px)`, height: 37 }}
            >
              <span className="font-mono text-xs text-muted-foreground" title={utcShort(t.timestamp)}>
                {timeAgo(t.timestamp)}
              </span>
              <span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                  t.kind === "compliance" ? "border-border bg-muted text-muted-foreground" : "border-primary/30 bg-primary/10 text-primary"
                }`}>{t.kind}</span>
              </span>
              <span className="truncate font-mono text-xs">{t.from_token} → {t.to_token}</span>
              <span className="font-mono text-xs tabular-nums">{t.from_amount ?? "—"}</span>
              <span className={`font-mono text-xs ${
                t.status === "confirmed" ? "text-gain" : t.status.startsWith("failed") ? "text-loss" : "text-muted-foreground"
              }`}>{t.status}</span>
              <span>
                {t.tx_hash ? (
                  <a href={`https://bscscan.com/tx/${t.tx_hash}`} target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
                    {t.tx_hash.slice(0, 10)}… <ExternalLink size={11} aria-hidden />
                  </a>
                ) : <span className="text-xs text-muted-foreground">—</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
