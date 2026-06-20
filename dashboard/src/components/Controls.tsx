import { useState } from "react";
import { api, type Status } from "../lib/api";
import { Lock, OctagonX, Play, RotateCcw, ShieldCheck } from "lucide-react";

/* Operator controls. Every action writes agent_state keys the loop reads each
   cycle — nothing here trades directly. Times are entered and displayed in UTC
   because the competition clock is UTC. */

function isoToLocalInput(iso: string | null): string {
  return iso ? iso.slice(0, 16) : "";
}

export function Controls({ status, onChanged }: { status: Status; onChanged: () => void }) {
  const [start, setStart] = useState(isoToLocalInput(status.window.start));
  const [end, setEnd] = useState(isoToLocalInput(status.window.end));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);

  // On the public demo host the API is read-only: controls render so judges can see
  // what's available, but every input and button is inert (the API also returns 403).
  const readonly = !!status.config.readonly;
  const locked = busy || readonly;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const saveWindow = () =>
    run(() => api.setWindow(start ? `${start}:00Z` : null, end ? `${end}:00Z` : null));

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div>
        <h3 className="text-base font-medium">Competition window</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          All times UTC. The agent only trades inside this window — changes apply within one cycle.
        </p>
      </div>

      {readonly && (
        <p className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          <Lock size={13} aria-hidden className="shrink-0" />
          Read-only view. Operator controls run on the private, localhost-only API — disabled here on the public dashboard.
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">Start (UTC)</span>
          <input
            type="datetime-local"
            value={start}
            disabled={locked}
            onChange={(e) => setStart(e.target.value)}
            className="w-full rounded-md border border-border bg-input px-3 py-2 font-mono text-sm text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">End (UTC)</span>
          <input
            type="datetime-local"
            value={end}
            disabled={locked}
            onChange={(e) => setEnd(e.target.value)}
            className="w-full rounded-md border border-border bg-input px-3 py-2 font-mono text-sm text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          />
        </label>
      </div>

      <button
        type="button"
        disabled={locked}
        onClick={saveWindow}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
      >
        Save window
      </button>

      <hr className="border-border" />

      <div className="flex flex-wrap items-center gap-2">
        {status.override === "off" || confirmStop ? null : (
          <button
            type="button"
            disabled={locked}
            onClick={() => setConfirmStop(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-loss/40 bg-loss/10 px-4 py-2 text-sm font-medium text-loss transition-colors hover:bg-loss/20 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-loss focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          >
            <OctagonX size={15} aria-hidden /> Emergency stop
          </button>
        )}
        {confirmStop && (
          <button
            type="button"
            disabled={locked}
            onClick={() => {
              setConfirmStop(false);
              run(() => api.setOverride("off"));
            }}
            className="inline-flex items-center gap-1.5 rounded-md bg-destructive px-4 py-2 text-sm font-semibold text-destructive-foreground hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-loss focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          >
            <OctagonX size={15} aria-hidden /> Confirm: stop all trading
          </button>
        )}
        {status.override !== null && (
          <button
            type="button"
            disabled={locked}
            onClick={() => run(() => api.setOverride(null))}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          >
            <RotateCcw size={15} aria-hidden /> Clear override ({status.override})
          </button>
        )}
        {status.override !== "on" && (
          <button
            type="button"
            disabled={locked}
            onClick={() => run(() => api.setOverride("on"))}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          >
            <Play size={15} aria-hidden /> Force trading on
          </button>
        )}
        {status.halted && (
          <button
            type="button"
            disabled={locked}
            onClick={() => run(() => api.clearHalt())}
            className="inline-flex items-center gap-1.5 rounded-md border border-warn/40 bg-warn/10 px-4 py-2 text-sm font-medium text-warn transition-colors hover:bg-warn/20 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warn focus-visible:ring-offset-2 focus-visible:ring-offset-card"
          >
            <ShieldCheck size={15} aria-hidden /> Clear halt (manual restart)
          </button>
        )}
      </div>

      {status.halted && status.halt_reason && (
        <p className="rounded-md border border-loss/30 bg-loss/10 px-3 py-2 font-mono text-xs text-loss">
          HALTED: {status.halt_reason}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error} — check that the API server is running, then retry.
        </p>
      )}
    </div>
  );
}
