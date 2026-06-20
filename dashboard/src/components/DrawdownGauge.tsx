import { pct } from "../lib/format";

/* Half-donut gauge: current drawdown from peak, scaled 0 → disqualification line,
   with a tick at the halt (flatten) threshold. Green well clear, amber as it nears
   the halt, red past it. */

const R = 90;
const CX = 100;
const CY = 100;
const ARC_LEN = Math.PI * R; // length of the 180° path

// point on the top semicircle at fraction f along left→top→right (0..1)
function pointAt(f: number, radius = R): [number, number] {
  const deg = 180 - 180 * Math.max(0, Math.min(1, f));
  const a = (deg * Math.PI) / 180;
  return [CX + radius * Math.cos(a), CY - radius * Math.sin(a)];
}

export function DrawdownGauge({
  drawdownPct,
  haltPct,
  dqPct,
}: {
  drawdownPct: number;
  haltPct: number;
  dqPct: number;
}) {
  const scale = dqPct || 30;
  const dd = Math.max(0, drawdownPct);
  const f = Math.min(1, dd / scale);
  const tone =
    dd >= haltPct ? "var(--loss)" : dd >= haltPct / 2 ? "var(--warn)" : "var(--gain)";

  const haltF = Math.min(1, haltPct / scale);
  const [hx1, hy1] = pointAt(haltF, R - 12);
  const [hx2, hy2] = pointAt(haltF, R + 4);
  const arc = `M 10 100 A ${R} ${R} 0 0 0 190 100`;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 118" className="w-full max-w-[260px]" role="img"
        aria-label={`Drawdown ${pct(dd)} of ${pct(dqPct, 0)} disqualification limit`}>
        {/* track */}
        <path d={arc} fill="none" stroke="var(--border)" strokeWidth={12} strokeLinecap="round" />
        {/* fill */}
        <path
          d={arc}
          fill="none"
          stroke={tone}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${ARC_LEN * f} ${ARC_LEN}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
        {/* halt tick */}
        <line x1={hx1} y1={hy1} x2={hx2} y2={hy2} stroke="var(--warn)" strokeWidth={2} />
        {/* center readout */}
        <text x={CX} y={74} textAnchor="middle" className="fill-foreground"
          style={{ fontFamily: "var(--font-mono)", fontSize: 26, fontWeight: 600 }}>
          {dd.toFixed(1)}%
        </text>
        <text x={CX} y={92} textAnchor="middle" className="fill-muted-foreground"
          style={{ fontFamily: "var(--font-sans)", fontSize: 9, letterSpacing: "0.08em" }}>
          DRAWDOWN
        </text>
      </svg>
      <div className="mt-1 flex items-center gap-4 font-mono text-[11px] text-muted-foreground">
        <span><span className="text-warn">│</span> halt {pct(haltPct, 0)}</span>
        <span><span className="text-loss">│</span> DQ {pct(dqPct, 0)}</span>
      </div>
    </div>
  );
}
