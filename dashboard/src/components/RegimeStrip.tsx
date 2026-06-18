import type { Status } from "../lib/api";
import { signedPct, timeAgo } from "../lib/format";
import { Activity, Gauge, Pause, ShieldAlert, TrendingDown, TrendingUp } from "lucide-react";

const POSTURE: Record<string, { label: string; cls: string; note: string }> = {
  risk_on: { label: "Risk-on", cls: "border-gain/30 bg-gain/10 text-gain", note: "both plays · full size" },
  neutral: { label: "Neutral", cls: "border-primary/30 bg-primary/10 text-primary", note: "both plays · full size" },
  cautious: { label: "Cautious", cls: "border-warn/30 bg-warn/10 text-warn", note: "mean-reversion only · half size" },
  risk_off: { label: "Risk-off", cls: "border-loss/30 bg-loss/10 text-loss", note: "no new entries" },
};

const REGIME: Record<string, { label: string; cls: string }> = {
  trending: { label: "Trending", cls: "text-gain" },
  ranging: { label: "Ranging", cls: "text-warn" },
  high_risk: { label: "High risk", cls: "text-loss" },
};

// Fear & Greed colour: extreme fear (red) → fear (amber) → neutral → greed (green)
function fgTone(fg: number | null): string {
  if (fg == null) return "text-muted-foreground";
  if (fg <= 25) return "text-loss";
  if (fg < 45) return "text-warn";
  if (fg <= 75) return "text-gain";
  return "text-warn"; // extreme greed is its own kind of risk
}

export function RegimeStrip({ status }: { status: Status }) {
  const r = status.regime;
  const posture = r ? POSTURE[r.posture] ?? POSTURE.neutral : null;
  const regime = REGIME[status.last_decision?.regime ?? "high_risk"];
  const m7 = r?.mcap_7d ?? null;

  return (
    <div className="flex flex-wrap items-stretch gap-px overflow-hidden rounded-xl border border-border bg-border">
      {/* Trading status */}
      <Item grow>
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Trading</span>
        <div className="mt-1">
          {status.halted ? (
            <Badge cls="border-loss/30 bg-loss/15 text-loss"><ShieldAlert size={13} aria-hidden /> Halted</Badge>
          ) : status.trading_allowed ? (
            <Badge cls="border-gain/30 bg-gain/15 text-gain"><Activity size={13} aria-hidden /> Active</Badge>
          ) : (
            <Badge cls="border-border bg-muted text-muted-foreground"><Pause size={13} aria-hidden /> Gated</Badge>
          )}
        </div>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          {status.trades_today} trade{status.trades_today === 1 ? "" : "s"} today · min 1/day
        </p>
      </Item>

      {/* Posture */}
      <Item grow>
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Risk posture</span>
        <div className="mt-1">
          {posture ? (
            <Badge cls={posture.cls}><Gauge size={13} aria-hidden /> {posture.label}</Badge>
          ) : (
            <span className="font-mono text-xs text-muted-foreground">awaiting macro…</span>
          )}
        </div>
        {posture && <p className="mt-1 text-[11px] text-muted-foreground">{posture.note}</p>}
      </Item>

      {/* Regime (LLM-classified) */}
      <Item grow>
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Regime</span>
        <p className={`mt-1 text-sm font-semibold ${regime.cls}`}>{regime.label}</p>
        <p className="mt-0.5 text-[11px] capitalize text-muted-foreground">
          {(status.last_decision?.mode ?? "—").replace(/_/g, " ")}
        </p>
      </Item>

      {/* Fear & Greed */}
      <Item grow>
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Fear &amp; Greed</span>
        <p className={`mt-1 font-mono text-lg font-semibold tabular-nums ${fgTone(r?.fear_greed ?? null)}`}>
          {r?.fear_greed ?? "—"}
        </p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{r?.fear_greed_label ?? ""}</p>
      </Item>

      {/* Market 7d */}
      <Item grow>
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Market 7d</span>
        <p className={`mt-1 inline-flex items-center gap-1 font-mono text-lg font-semibold tabular-nums ${m7 == null ? "text-muted-foreground" : m7 >= 0 ? "text-gain" : "text-loss"}`}>
          {m7 != null && (m7 >= 0 ? <TrendingUp size={14} aria-hidden /> : <TrendingDown size={14} aria-hidden />)}
          {signedPct(m7, 1)}
        </p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {r ? `updated ${timeAgo(r.updated)}` : "total mcap"}
        </p>
      </Item>
    </div>
  );
}

function Item({ children, grow }: { children: React.ReactNode; grow?: boolean }) {
  return <div className={`bg-card p-3 ${grow ? "min-w-35 flex-1" : ""}`}>{children}</div>;
}

function Badge({ children, cls }: { children: React.ReactNode; cls: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium ${cls}`}>
      {children}
    </span>
  );
}
