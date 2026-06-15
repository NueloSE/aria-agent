import { useCallback, useEffect, useState } from "react";
import { api, type Decision, type PortfolioPoint, type Status, type Trade } from "../lib/api";
import { StatusBar } from "./StatusBar";
import { PnlChart } from "./PnlChart";
import { DecisionLog } from "./DecisionLog";
import { Controls } from "./Controls";
import { TradesPanel } from "./TradesPanel";
import { Logo } from "./Logo";

const POLL_MS = 10_000;

export function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioPoint[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, d, p, t] = await Promise.all([
        api.status(),
        api.decisions(100),
        api.portfolio(1000),
        api.trades(50),
      ]);
      setStatus(s);
      setDecisions(d);
      setPortfolio(p);
      setTrades(t);
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
        <div className="mx-auto flex max-w-6xl items-baseline justify-between px-4 py-5">
          <div className="flex items-baseline gap-3">
            <a href="/" aria-label="ARIA home" className="flex items-center gap-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md">
              <Logo size={26} />
              <h1 className="font-serif text-3xl tracking-tight">ARIA</h1>
            </a>
            <p className="hidden text-sm text-muted-foreground sm:block">
              Adaptive Regime Intelligence — reads the regime first
            </p>
          </div>
          <p className="font-mono text-xs text-muted-foreground">
            {status ? `every ${status.config.cycle_interval_min}min · live` : "connecting…"}
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        {error && (
          <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            Can't reach the agent API ({error}). Start it with{" "}
            <code className="font-mono text-xs">uvicorn aria.api:app --port 8000</code> — this page
            retries automatically.
          </div>
        )}

        {!status && !error ? (
          <Skeleton />
        ) : status ? (
          <>
            <StatusBar status={status} />

            <section aria-labelledby="pnl-h">
              <h2 id="pnl-h" className="mb-2 text-xl font-semibold">
                Portfolio vs. risk gates
              </h2>
              <div className="rounded-lg border border-border bg-card p-4">
                <PnlChart
                  points={portfolio}
                  haltPct={status.config.halt_drawdown_pct}
                  dqPct={status.config.max_drawdown_pct}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  <span className="text-warn">— —</span> halt level ({status.config.halt_drawdown_pct}% from peak) ·{" "}
                  <span className="text-loss">— —</span> disqualification ({status.config.max_drawdown_pct}% from peak)
                </p>
              </div>
            </section>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <section aria-labelledby="log-h" className="lg:col-span-2">
                <h2 id="log-h" className="mb-2 text-xl font-semibold">
                  Decision log
                </h2>
                <DecisionLog decisions={decisions} />
              </section>

              <section aria-labelledby="ops-h">
                <h2 id="ops-h" className="mb-2 text-xl font-semibold">
                  Operator
                </h2>
                <Controls status={status} onChanged={refresh} />
              </section>
            </div>

            <section aria-labelledby="trades-h">
              <h2 id="trades-h" className="mb-2 text-xl font-semibold">
                Trades
              </h2>
              <TradesPanel trades={trades} />
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading dashboard">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg border border-border bg-card motion-reduce:animate-none" />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-lg border border-border bg-card motion-reduce:animate-none" />
      <div className="h-48 animate-pulse rounded-lg border border-border bg-card motion-reduce:animate-none" />
    </div>
  );
}
