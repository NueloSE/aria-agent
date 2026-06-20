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
import { shortAddr, timeAgo } from "../lib/format";

const POLL_MS = 10_000;

export function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioPoint[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [perf, setPerf] = useState<Performance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

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
      setUpdatedAt(Date.now());
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
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
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
            <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
              <Pill>{status.config.network}</Pill>
              <Pill>{status.config.execution_mode === "paper" ? "paper trading" : status.config.execution_mode}</Pill>
              <Pill>{status.config.brain.split("/")[1] ?? status.config.brain}</Pill>
              <a
                href={`https://bscscan.com/address/${status.config.wallet}`}
                target="_blank"
                rel="noreferrer"
                title={status.config.wallet}
                className="hidden rounded-sm hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline"
              >
                {shortAddr(status.config.wallet)}
              </a>
              <span className="inline-flex items-center gap-2 border-l border-border pl-2">
                {updatedAt && !error && (
                  <span className="hidden md:inline">updated {timeAgo(new Date(updatedAt).toISOString())}</span>
                )}
                <LiveDot ok={!error} />
              </span>
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
            <NowBanner status={status} />
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

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-border bg-background/30 px-2 py-0.5 lowercase tracking-tight">
      {children}
    </span>
  );
}

const POSTURE_NOTE: Record<string, string> = {
  risk_on: "trading both plays at full size",
  neutral: "trading both plays at full size",
  cautious: "mean-reversion only, at half size",
  risk_off: "holding — no new entries",
};

/** One plain-English line a cold visitor can read to know what ARIA is doing right
 *  now — derived from halt state, the trading window, and the latest decision. */
function NowBanner({ status }: { status: Status }) {
  const d = status.last_decision;
  const reasoning = d?.reasoning?.split(" | ")[0]?.trim() ?? null;

  let tone = "bg-gain";
  let headline: string;
  let detail: string;

  if (status.halted) {
    tone = "bg-loss";
    headline = "Trading halted";
    detail = status.halt_reason ?? "Circuit breaker tripped — awaiting manual release.";
  } else if (!status.trading_allowed) {
    tone = "bg-warn";
    headline = "Standing by";
    detail = status.trading_reason || "Outside the competition window.";
  } else {
    const posture = status.regime?.posture;
    headline = "Active";
    detail = posture
      ? `Risk posture ${posture.replace("_", "-")} — ${POSTURE_NOTE[posture] ?? "monitoring the tape"}.`
      : "Reading the macro regime…";
  }

  return (
    <section
      aria-label="Current status"
      className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-center sm:gap-4"
    >
      <div className="flex shrink-0 items-center gap-2.5">
        <span className="relative flex h-2.5 w-2.5">
          {!status.halted && (
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${tone} opacity-60 motion-reduce:animate-none`} />
          )}
          <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${tone}`} />
        </span>
        <span className="text-base font-semibold">{headline}</span>
      </div>
      <p className="min-w-0 flex-1 text-sm text-muted-foreground sm:border-l sm:border-border sm:pl-4">
        {detail}
        {reasoning && !status.halted && (
          <span className="mt-1 block truncate font-mono text-xs text-foreground/70" title={reasoning}>
            latest: {reasoning}
            {d?.timestamp ? ` · ${timeAgo(d.timestamp)}` : ""}
          </span>
        )}
      </p>
    </section>
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
