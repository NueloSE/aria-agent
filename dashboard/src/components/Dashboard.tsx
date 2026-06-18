import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Decision,
  type Performance,
  type PortfolioPoint,
  type Position,
  type Status,
  type Trade,
} from "../lib/api";
import { KpiHero } from "./KpiHero";
import { RegimeStrip } from "./RegimeStrip";
import { PnlChart } from "./PnlChart";
import { PositionsPanel } from "./PositionsPanel";
import { DecisionLog } from "./DecisionLog";
import { Controls } from "./Controls";
import { TradesPanel } from "./TradesPanel";
import { Logo } from "./Logo";
import { shortAddr } from "../lib/format";

const POLL_MS = 10_000;

export function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioPoint[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [perf, setPerf] = useState<Performance | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, d, p, t, pos, pf] = await Promise.all([
        api.status(),
        api.decisions(150),
        api.portfolio(1000),
        api.trades(100),
        api.positions(),
        api.performance(),
      ]);
      setStatus(s);
      setDecisions(d);
      setPortfolio(p);
      setTrades(t);
      setPositions(pos);
      setPerf(pf);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="min-h-screen">
      <header className="bg-brand-gradient border-b border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-4">
          <div className="flex items-baseline gap-3">
            <a href="/" aria-label="ARIA home" className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <Logo size={26} />
              <h1 className="font-serif text-3xl tracking-tight">ARIA</h1>
            </a>
            <p className="hidden text-sm text-muted-foreground sm:block">
              Adaptive Regime Intelligence — reads the regime first
            </p>
          </div>
          {status && (
            <div className="flex items-center gap-3 font-mono text-xs text-muted-foreground">
              <span title={status.config.wallet} className="hidden sm:inline">{shortAddr(status.config.wallet)}</span>
              <span className="hidden sm:inline">·</span>
              <span>{status.config.execution_mode} · {status.config.brain.split("/")[1] ?? status.config.brain}</span>
              <LiveDot ok={!error} />
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-6">
        {error && (
          <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            Can't reach the agent API ({error}). Start it with{" "}
            <code className="font-mono text-xs">uvicorn aria.api:app --port 8000</code> — this page retries automatically.
          </div>
        )}

        {!status && !error ? (
          <Skeleton />
        ) : status ? (
          <>
            <KpiHero perf={perf} status={status} />
            <RegimeStrip status={status} />

            <section aria-labelledby="pnl-h">
              <h2 id="pnl-h" className="mb-2 text-base font-medium">Portfolio vs. risk gates</h2>
              <div className="rounded-xl border border-border bg-card p-4">
                <PnlChart points={portfolio} haltPct={status.config.halt_drawdown_pct} dqPct={status.config.max_drawdown_pct} />
                <p className="mt-2 text-xs text-muted-foreground">
                  <span className="text-warn">— —</span> halt ({status.config.halt_drawdown_pct}% from peak) ·{" "}
                  <span className="text-loss">— —</span> disqualification ({status.config.max_drawdown_pct}% from peak)
                </p>
              </div>
            </section>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
              <section aria-labelledby="pos-h" className="lg:col-span-2">
                <h2 id="pos-h" className="mb-2 text-base font-medium">Open positions</h2>
                <PositionsPanel positions={positions} />
              </section>
              <section aria-labelledby="ops-h">
                <h2 id="ops-h" className="mb-2 text-base font-medium">Operator</h2>
                <Controls status={status} onChanged={refresh} />
              </section>
            </div>

            <section aria-labelledby="log-h">
              <h2 id="log-h" className="mb-2 text-base font-medium">Decision log</h2>
              <DecisionLog decisions={decisions} />
            </section>

            <section aria-labelledby="trades-h">
              <h2 id="trades-h" className="mb-2 text-base font-medium">Trade performance</h2>
              <TradesPanel perf={perf} trades={trades} />
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

function LiveDot({ ok }: { ok: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`relative flex h-2 w-2`}>
        {ok && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-gain opacity-75 motion-reduce:animate-none" />}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${ok ? "bg-gain" : "bg-loss"}`} />
      </span>
      {ok ? "live" : "offline"}
    </span>
  );
}

function Skeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading dashboard">
      <div className="h-28 animate-pulse rounded-xl border border-border bg-card motion-reduce:animate-none" />
      <div className="h-20 animate-pulse rounded-xl border border-border bg-card motion-reduce:animate-none" />
      <div className="h-72 animate-pulse rounded-xl border border-border bg-card motion-reduce:animate-none" />
      <div className="h-48 animate-pulse rounded-xl border border-border bg-card motion-reduce:animate-none" />
    </div>
  );
}
