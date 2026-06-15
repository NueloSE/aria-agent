import type { Status } from "../lib/api";
import { pct, shortAddr, timeAgo, usd } from "../lib/format";
import { Activity, Pause, ShieldAlert, Wallet } from "lucide-react";

const REGIME_STYLES: Record<string, string> = {
  trending: "bg-gain/15 text-gain border-gain/30",
  ranging: "bg-warn/15 text-warn border-warn/30",
  high_risk: "bg-loss/15 text-loss border-loss/30",
};

const REGIME_LABELS: Record<string, string> = {
  trending: "Trending",
  ranging: "Ranging",
  high_risk: "High risk",
};

export function StatusBar({ status }: { status: Status }) {
  const d = status.last_decision;
  const p = status.portfolio;
  const regime = d?.regime ?? "high_risk";

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
      <Cell label="Regime">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium ${REGIME_STYLES[regime]}`}
        >
          <Activity size={13} aria-hidden />
          {REGIME_LABELS[regime]}
        </span>
        <p className="mt-1 text-xs text-muted-foreground">
          {d ? `${d.mode.replace("_", " ")} · ${timeAgo(d.timestamp)}` : "no decisions yet"}
        </p>
      </Cell>

      <Cell label="Portfolio">
        <p className="font-mono text-lg font-semibold tabular-nums">
          {usd(p?.total_value_usd)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          peak {usd(p?.peak_value_usd)}
        </p>
      </Cell>

      <Cell label="Drawdown">
        <p
          className={`font-mono text-lg font-semibold tabular-nums ${
            (p?.drawdown_pct ?? 0) >= status.config.halt_drawdown_pct
              ? "text-loss"
              : (p?.drawdown_pct ?? 0) >= status.config.halt_drawdown_pct / 2
                ? "text-warn"
                : "text-gain"
          }`}
        >
          {pct(p?.drawdown_pct)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          halt {pct(status.config.halt_drawdown_pct, 0)} · DQ {pct(status.config.max_drawdown_pct, 0)}
        </p>
      </Cell>

      <Cell label="Trading">
        {status.halted ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-loss/30 bg-loss/15 px-2.5 py-0.5 text-sm font-medium text-loss">
            <ShieldAlert size={13} aria-hidden /> Halted
          </span>
        ) : status.trading_allowed ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-gain/30 bg-gain/15 px-2.5 py-0.5 text-sm font-medium text-gain">
            <Activity size={13} aria-hidden /> Active
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2.5 py-0.5 text-sm font-medium text-muted-foreground">
            <Pause size={13} aria-hidden /> Gated
          </span>
        )}
        <p className="mt-1 truncate text-xs text-muted-foreground" title={status.trading_reason}>
          {status.trading_reason}
        </p>
      </Cell>

      <Cell label="Trades today">
        <p className="font-mono text-lg font-semibold tabular-nums">{status.trades_today}</p>
        <p className="mt-1 text-xs text-muted-foreground">min 1/day rule</p>
      </Cell>

      <Cell label="Agent">
        <p className="inline-flex items-center gap-1.5 font-mono text-sm" title={status.config.wallet}>
          <Wallet size={13} aria-hidden className="text-muted-foreground" />
          {shortAddr(status.config.wallet)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {status.config.network} · {status.config.brain}
        </p>
      </Cell>
    </div>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      {children}
    </div>
  );
}
