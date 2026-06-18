import type { Position } from "../lib/api";
import { signedPct, signedUsd, timeAgo, toneFor, usd } from "../lib/format";

export function PositionsPanel({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return (
      <div className="flex h-28 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border text-sm text-muted-foreground">
        <span>No open positions</span>
        <span className="text-xs">ARIA is in stables — waiting for a setup the judge approves.</span>
      </div>
    );
  }
  const deployed = positions.reduce((a, p) => a + (p.value_usd ?? 0), 0);
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-baseline justify-between border-b border-border px-4 py-2.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {positions.length} open · {usd(deployed)} deployed
        </span>
      </div>
      <ul className="divide-y divide-border">
        {positions.map((p) => (
          <PositionRow key={p.symbol} p={p} />
        ))}
      </ul>
    </div>
  );
}

function PositionRow({ p }: { p: Position }) {
  const gain = p.unrealized_pct ?? 0;
  const stop = -(p.stop_loss_pct ?? 5);
  const target = p.target_pct ?? 7;
  // position of the current-gain marker on the stop→target track (0–100%)
  const clamp = (n: number) => Math.max(0, Math.min(100, n));
  const markerPos = clamp(((gain - stop) / (target - stop)) * 100);
  const zeroPos = clamp(((0 - stop) / (target - stop)) * 100);
  const peakPos = clamp(((p.peak_gain_pct - stop) / (target - stop)) * 100);

  return (
    <li className="px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-semibold">{p.symbol}</span>
          <span className="font-mono text-[11px] text-muted-foreground">
            {usd(p.entry_price_usd)} → {usd(p.current_price_usd)}
          </span>
        </div>
        <div className="text-right">
          <span className={`font-mono text-sm font-semibold tabular-nums ${toneFor(p.unrealized_pct)}`}>
            {signedPct(p.unrealized_pct)}
          </span>
          <span className={`ml-2 font-mono text-xs tabular-nums ${toneFor(p.unrealized_usd)}`}>
            {signedUsd(p.unrealized_usd)}
          </span>
        </div>
      </div>

      {/* stop ↔ target track */}
      <div className="mt-2.5">
        <div className="relative h-1.5 rounded-full bg-muted" aria-hidden>
          {/* gain fill from break-even to marker */}
          <div
            className={`absolute top-0 h-full rounded-full ${gain >= 0 ? "bg-gain/50" : "bg-loss/50"}`}
            style={
              gain >= 0
                ? { left: `${zeroPos}%`, width: `${markerPos - zeroPos}%` }
                : { left: `${markerPos}%`, width: `${zeroPos - markerPos}%` }
            }
          />
          {/* peak marker */}
          {p.peak_gain_pct > 0 && (
            <div className="absolute top-1/2 h-2.5 w-0.5 -translate-y-1/2 bg-primary/60" style={{ left: `${peakPos}%` }} />
          )}
          {/* current marker */}
          <div
            className={`absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full ${gain >= 0 ? "bg-gain" : "bg-loss"}`}
            style={{ left: `${markerPos}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
          <span className="text-loss">stop {signedPct(stop, 0)}</span>
          <span>opened {timeAgo(p.opened_at)}{p.peak_gain_pct > 0 ? ` · peak ${signedPct(p.peak_gain_pct, 1)}` : ""}</span>
          <span className="text-gain">target {signedPct(target, 0)}</span>
        </div>
      </div>
    </li>
  );
}
