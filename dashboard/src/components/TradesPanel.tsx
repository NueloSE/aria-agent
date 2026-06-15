import type { Trade } from "../lib/api";
import { timeAgo, utcShort } from "../lib/format";
import { ExternalLink } from "lucide-react";

export function TradesPanel({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
        No trades yet — strategy entries and compliance heartbeats appear here.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">When</th>
            <th className="px-4 py-2.5 font-medium">Kind</th>
            <th className="px-4 py-2.5 font-medium">Swap</th>
            <th className="px-4 py-2.5 font-medium">Amount</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Tx</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {trades.map((t) => (
            <tr key={t.id}>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground" title={utcShort(t.timestamp)}>
                {timeAgo(t.timestamp)}
              </td>
              <td className="px-4 py-2.5">
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                    t.kind === "compliance"
                      ? "border-border bg-muted text-muted-foreground"
                      : "border-primary/30 bg-primary/10 text-primary"
                  }`}
                >
                  {t.kind}
                </span>
              </td>
              <td className="px-4 py-2.5 font-mono text-xs">
                {t.from_token} → {t.to_token}
              </td>
              <td className="px-4 py-2.5 font-mono text-xs tabular-nums">
                {t.from_amount ?? "—"}
              </td>
              <td
                className={`px-4 py-2.5 font-mono text-xs ${
                  t.status === "confirmed"
                    ? "text-gain"
                    : t.status.startsWith("failed")
                      ? "text-loss"
                      : "text-muted-foreground"
                }`}
              >
                {t.status}
              </td>
              <td className="px-4 py-2.5">
                {t.tx_hash ? (
                  <a
                    href={`https://bscscan.com/tx/${t.tx_hash}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                  >
                    {t.tx_hash.slice(0, 10)}… <ExternalLink size={11} aria-hidden />
                  </a>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
