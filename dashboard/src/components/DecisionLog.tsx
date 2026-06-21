import { useMemo, useState } from "react";
import type { Decision } from "../lib/api";
import { pct, timeAgo, utcShort } from "../lib/format";
import { ChevronDown, Ban, CircleSlash } from "lucide-react";

const REGIME_DOT: Record<string, string> = {
  trending: "bg-gain",
  ranging: "bg-warn",
  high_risk: "bg-loss",
};

const ACTION_TONE: Record<string, string> = {
  buy: "text-gain",
  sell: "text-warn",
  close_all: "text-loss",
  hold: "text-muted-foreground",
};

type Filter = "actions" | "rejected" | "all";

const isAction = (d: Decision) => d.action !== "hold";
const isRejection = (d: Decision) =>
  /judge rejected/i.test(d.reasoning) || (d.safety_verdict?.startsWith("vetoed") ?? false);
const isNoteworthy = (d: Decision) => isAction(d) || isRejection(d);

function verdictTone(verdict: string | null): string {
  if (!verdict) return "text-muted-foreground";
  if (verdict.startsWith("vetoed") || verdict === "halted" || verdict === "halt_triggered") return "text-loss";
  if (verdict === "window_closed" || verdict === "auto_hold" || verdict === "forced_preservation") return "text-warn";
  if (verdict === "approved") return "text-gain";
  return "text-muted-foreground";
}

export function DecisionLog({
  decisions,
  noteworthy,
}: {
  decisions: Decision[];
  // The agent's actual trades + rejections, fetched separately so they show even when
  // they're thousands of quiet holds back. Falls back to filtering the recent window.
  noteworthy?: Decision[];
}) {
  const [filter, setFilter] = useState<Filter>("actions");

  const note = useMemo(
    () => noteworthy ?? decisions.filter(isNoteworthy),
    [noteworthy, decisions],
  );

  const counts = useMemo(
    () => ({
      actions: note.filter(isAction).length,
      rejected: note.filter(isRejection).length,
      all: decisions.length,
    }),
    [note, decisions],
  );

  // Build the visible row list. "all" collapses consecutive quiet holds into one summary row.
  const rows = useMemo(() => {
    if (filter === "actions") return note.filter(isAction).map((d) => ({ kind: "row" as const, d }));
    if (filter === "rejected") return note.filter(isRejection).map((d) => ({ kind: "row" as const, d }));

    const out: Array<{ kind: "row"; d: Decision } | { kind: "collapsed"; n: number }> = [];
    let run = 0;
    for (const d of decisions) {
      if (isNoteworthy(d)) {
        if (run) { out.push({ kind: "collapsed", n: run }); run = 0; }
        out.push({ kind: "row", d });
      } else run++;
    }
    if (run) out.push({ kind: "collapsed", n: run });
    return out;
  }, [decisions, note, filter]);

  if (decisions.length === 0 && note.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
        No decisions yet — start the agent loop to populate this log.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-1 border-b border-border p-1.5" role="tablist" aria-label="Decision filter">
        <Tab id="actions" cur={filter} set={setFilter} label="Actions" n={counts.actions} />
        <Tab id="rejected" cur={filter} set={setFilter} label="Rejected" n={counts.rejected} />
        <Tab id="all" cur={filter} set={setFilter} label="All" n={counts.all} />
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-muted-foreground">
          {filter === "actions"
            ? "No trades yet — ARIA is scanning and holding."
            : filter === "rejected"
              ? "No judge rejections yet."
              : "Nothing here yet."}
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((r, i) =>
            r.kind === "collapsed" ? (
              <li key={`c${i}`} className="flex items-center gap-2 px-4 py-1.5 text-[11px] text-muted-foreground">
                <CircleSlash size={11} aria-hidden className="opacity-50" />
                {r.n} quiet {r.n === 1 ? "tick" : "ticks"} held — no setup
              </li>
            ) : (
              <DecisionRow key={r.d.cycle_id} d={r.d} />
            ),
          )}
        </ul>
      )}
    </div>
  );
}

function Tab({ id, cur, set, label, n }: { id: Filter; cur: Filter; set: (f: Filter) => void; label: string; n: number }) {
  const active = cur === id;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => set(id)}
      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
        active ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground"
      }`}
    >
      {label} <span className="font-mono tabular-nums opacity-70">{n}</span>
    </button>
  );
}

function DecisionRow({ d }: { d: Decision }) {
  const [open, setOpen] = useState(false);
  const parts = d.reasoning.split(" | strategy: ");
  const judged = parts.find((p) => /judge:/i.test(p));
  const rejected = isRejection(d);

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${REGIME_DOT[d.regime]}`} aria-hidden />
        <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground" title={utcShort(d.timestamp)}>
          {timeAgo(d.timestamp)}
        </span>
        <span className={`flex w-20 shrink-0 items-center gap-1 text-xs font-medium capitalize ${ACTION_TONE[d.action] ?? ""}`}>
          {rejected && d.action === "hold" && <Ban size={11} aria-hidden className="text-loss" />}
          {d.action === "hold" && rejected ? "rejected" : d.action.replace("_", " ")}
        </span>
        <span className="w-14 shrink-0 font-mono text-xs">{d.token_symbol ?? "—"}</span>
        <span className="hidden w-16 shrink-0 font-mono text-xs text-muted-foreground sm:inline">
          {pct(d.confidence * 100, 0)}
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
          <Field label="Brain / gate">{parts[0]}</Field>
          {parts[1] && !judged && <Field label="Strategy gates">{parts[1]}</Field>}
          {judged && <Field label="LLM judge">{judged.replace(/.*judge:\s*/i, "")}</Field>}
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
      <p className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
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
