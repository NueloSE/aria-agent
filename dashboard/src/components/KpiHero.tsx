import type { Performance, Status } from "../lib/api";
import { pct, signedPct, signedUsd, toneFor, usd } from "../lib/format";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export function KpiHero({ perf, status }: { perf: Performance | null; status: Status }) {
  const ret = perf?.total_return_pct ?? null;
  const value = perf?.total_value_usd ?? status.portfolio?.total_value_usd ?? null;
  const dd = status.portfolio?.drawdown_pct ?? 0;
  const Arrow = ret == null || ret === 0 ? Minus : ret > 0 ? ArrowUpRight : ArrowDownRight;

  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-border bg-border lg:grid-cols-[1.3fr_2fr]">
      {/* Headline: value + total return */}
      <div className="bg-card p-5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Portfolio value
        </p>
        <p className="mt-1 font-mono text-4xl font-semibold tabular-nums tracking-tight">
          {usd(value)}
        </p>
        <p className={`mt-1.5 inline-flex items-center gap-1 font-mono text-sm font-medium tabular-nums ${toneFor(ret)}`}>
          <Arrow size={15} aria-hidden />
          {signedPct(ret)} total return
          <span className="text-muted-foreground"> · from {usd(perf?.start_value_usd ?? 100)}</span>
        </p>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
        <Stat label="Realized PnL" value={signedUsd(perf?.realized_pnl_usd)} tone={toneFor(perf?.realized_pnl_usd)} />
        <Stat label="Unrealized PnL" value={signedUsd(perf?.unrealized_pnl_usd)} tone={toneFor(perf?.unrealized_pnl_usd)} />
        <Stat
          label="Drawdown"
          value={pct(dd)}
          tone={dd >= status.config.halt_drawdown_pct ? "text-loss" : dd >= status.config.halt_drawdown_pct / 2 ? "text-warn" : "text-gain"}
          sub={`halt ${pct(status.config.halt_drawdown_pct, 0)} · DQ ${pct(status.config.max_drawdown_pct, 0)}`}
        />
        <Stat
          label="Win rate"
          value={perf?.win_rate_pct == null ? "—" : pct(perf.win_rate_pct, 0)}
          tone="text-foreground"
          sub={perf ? `${perf.wins}W · ${perf.losses}L · ${perf.round_trips_total} closed` : undefined}
        />
      </div>
    </div>
  );
}

function Stat({ label, value, tone, sub }: { label: string; value: string; tone: string; sub?: string }) {
  return (
    <div className="bg-card p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-1 font-mono text-xl font-semibold tabular-nums ${tone}`}>{value}</p>
      {sub && <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}
