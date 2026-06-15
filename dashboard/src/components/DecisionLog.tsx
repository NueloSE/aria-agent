import { useState } from "react";
import type { Decision } from "../lib/api";
import { pct, timeAgo, utcShort } from "../lib/format";
import { ChevronDown } from "lucide-react";

const REGIME_DOT: Record<string, string> = {
  trending: "bg-gain",
  ranging: "bg-warn",
  high_risk: "bg-loss",
};

function verdictTone(verdict: string | null): string {
  if (!verdict) return "text-muted-foreground";
  if (verdict.startsWith("vetoed") || verdict === "halted" || verdict === "halt_triggered")
    return "text-loss";
  if (verdict === "window_closed" || verdict === "auto_hold" || verdict === "forced_preservation")
    return "text-warn";
  return "text-muted-foreground";
}

export function DecisionLog({ decisions }: { decisions: Decision[] }) {
  if (decisions.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
        No decisions yet — start the agent loop to populate this log.
      </div>
    );
  }
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-card">
      {decisions.map((d) => (
        <DecisionRow key={d.cycle_id} d={d} />
      ))}
    </ul>
  );
}

function DecisionRow({ d }: { d: Decision }) {
  const [open, setOpen] = useState(false);
  // brain reasoning and strategy-gate rationale are joined with " | strategy: "
  const parts = d.reasoning.split(" | strategy: ");

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${REGIME_DOT[d.regime]}`} aria-hidden />
        <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground" title={utcShort(d.timestamp)}>
          {timeAgo(d.timestamp)}
        </span>
        <span className="w-32 shrink-0 text-xs capitalize text-muted-foreground">
          {d.regime.replace("_", " ")} · {d.mode.replace("_", " ").replace("narrative rotation", "narrative")}
        </span>
        <span className="w-24 shrink-0 font-medium capitalize">{d.action.replace("_", " ")}</span>
        <span className="w-16 shrink-0 font-mono text-xs">{d.token_symbol ?? "—"}</span>
        <span className="hidden w-20 shrink-0 font-mono text-xs text-muted-foreground sm:inline">
          conf {pct(d.confidence * 100, 0)}
        </span>
        <span className={`hidden flex-1 truncate text-xs md:inline ${verdictTone(d.safety_verdict)}`}>
          {d.safety_verdict ?? ""}
        </span>
        <ChevronDown
          size={14}
          aria-hidden
          className={`shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border bg-background/40 px-4 py-3">
          <Field label="Brain">{parts[0]}</Field>
          {parts[1] && <Field label="Strategy gates">{parts[1]}</Field>}
          <div className="flex flex-wrap gap-x-6 gap-y-1 pt-1">
            <Meta k="cycle" v={d.cycle_id.slice(0, 8)} />
            <Meta k="mode" v={d.mode} />
            <Meta k="verdict" v={d.safety_verdict ?? "—"} />
            <Meta k="outcome" v={d.outcome ?? "pending"} />
            {d.size_pct ? <Meta k="size" v={pct(d.size_pct, 1)} /> : null}
          </div>
        </div>
      )}
    </li>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="font-mono text-xs leading-relaxed text-foreground/90">{children}</p>
    </div>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <span className="font-mono text-[11px] text-muted-foreground">
      {k}=<span className="text-foreground/80">{v}</span>
    </span>
  );
}
