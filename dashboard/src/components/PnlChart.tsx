import {
  Area,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ComposedChart,
} from "recharts";
import type { PortfolioPoint } from "../lib/api";
import { usd, utcShort } from "../lib/format";

interface ChartPoint {
  t: string;
  value: number;
  halt: number; // running peak × (1 − halt%)
  dq: number;   // running peak × (1 − DQ%)
}

export function PnlChart({
  points,
  haltPct,
  dqPct,
}: {
  points: PortfolioPoint[];
  haltPct: number;
  dqPct: number;
}) {
  if (points.length === 0) {
    return (
      <Empty>
        No portfolio history yet. The chart fills in as the agent runs its cycles.
      </Empty>
    );
  }

  const data: ChartPoint[] = points.map((p) => ({
    t: p.timestamp,
    value: p.total_value_usd,
    halt: p.peak_value_usd * (1 - haltPct / 100),
    dq: p.peak_value_usd * (1 - dqPct / 100),
  }));

  return (
    <div className="h-64 w-full" role="img" aria-label="Portfolio value over time with halt and disqualification thresholds">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="valueFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.25} />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={(t: string) => utcShort(t).slice(0, 11)}
            stroke="var(--muted-foreground)"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            minTickGap={48}
          />
          <YAxis
            stroke="var(--muted-foreground)"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${v}`}
            // pad below the DQ line and above the value line so neither hugs an edge
            domain={["dataMin - 8", "dataMax + 5"]}
            width={56}
          />
          <Tooltip
            contentStyle={{
              background: "var(--popover)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              color: "var(--foreground)",
              fontSize: 12,
              fontFamily: "var(--font-mono)",
            }}
            labelFormatter={(t) => utcShort(String(t))}
            formatter={(value, name) => [
              usd(typeof value === "number" ? value : Number(value)),
              { value: "Portfolio", halt: "Halt level", dq: "DQ level" }[String(name)] ?? String(name),
            ]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--primary)"
            strokeWidth={2}
            fill="url(#valueFill)"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="halt"
            stroke="var(--warn)"
            strokeWidth={1}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="dq"
            stroke="var(--loss)"
            strokeWidth={1}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
      {children}
    </div>
  );
}
