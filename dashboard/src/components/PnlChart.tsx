import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PortfolioPoint } from "../lib/api";
import { usd, utcShort } from "../lib/format";

/* Equity curve: portfolio value over time. The y-axis hugs the actual data so small
   moves are visible (a $0.26 gain on $100 was invisible when the axis was forced down
   to the ~$70 DQ line). Gate proximity lives in the drawdown gauge, not here. */

export function PnlChart({
  points,
  startValue,
}: {
  points: PortfolioPoint[];
  startValue?: number;
}) {
  if (points.length === 0) {
    return (
      <Empty>
        No portfolio history yet. The chart fills in as the agent runs its cycles.
      </Empty>
    );
  }

  const data = points.map((p) => ({ t: p.timestamp, value: p.total_value_usd }));
  const vals = data.map((d) => d.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const range = hi - lo;
  // Keep a visible band even when nearly flat; scale padding to the data otherwise.
  const pad = Math.max(range * 0.25, hi * 0.0015, 0.02);
  const domain: [number, number] = [lo - pad, hi + pad];
  const decimals = hi < 1000 ? 2 : 0;
  const fmt = (v: number) =>
    `$${v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;

  return (
    <div className="h-64 w-full" role="img" aria-label="Portfolio value over time">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="valueFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.28} />
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
            tickFormatter={fmt}
            domain={domain}
            width={72}
            tickCount={5}
          />
          {startValue != null && startValue > domain[0] && startValue < domain[1] && (
            <ReferenceLine
              y={startValue}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
              label={{
                value: `start ${fmt(startValue)}`,
                position: "insideBottomLeft",
                fill: "var(--muted-foreground)",
                fontSize: 10,
              }}
            />
          )}
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
            formatter={(value) => [usd(typeof value === "number" ? value : Number(value)), "Portfolio"]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--primary)"
            strokeWidth={2}
            fill="url(#valueFill)"
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
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
