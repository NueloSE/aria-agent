import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { api, type CandlesResponse } from "../lib/api";
import { usd } from "../lib/format";

/* OHLC candles for a tracked token, built server-side from ARIA's accumulated CMC
   price series (CMC's free tier sells no OHLCV, so candles are aggregated from the
   quotes we already pay a credit for each cycle). Themed from the brand tokens. */

const TIMEFRAMES: { label: string; bucket: number }[] = [
  { label: "15m", bucket: 900 },
  { label: "1H", bucket: 3600 },
  { label: "4H", bucket: 14400 },
];

const REFRESH_MS = 30_000;

// lightweight-charts parses colors itself and rejects oklch(), so resolve each brand
// token to an rgb() string by letting the browser compute it on a throwaway element.
function themeColor(varName: string): string {
  const probe = document.createElement("span");
  probe.style.color = `var(${varName})`;
  probe.style.display = "none";
  document.body.appendChild(probe);
  const rgb = getComputedStyle(probe).color;
  probe.remove();
  return rgb || "rgb(148,148,160)";
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function CandleChart() {
  const holder = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const [data, setData] = useState<CandlesResponse | null>(null);
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const [bucket, setBucket] = useState(900);
  const [error, setError] = useState<string | null>(null);

  // Fetch candles for the selected symbol/timeframe and keep them fresh.
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await api.candles(symbol, bucket);
        if (!alive) return;
        setData(r);
        setError(null);
        if (!symbol && r.symbol) setSymbol(r.symbol);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [symbol, bucket]);

  // Create the chart once.
  useEffect(() => {
    if (!holder.current) return;
    const chart = createChart(holder.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: themeColor("--muted-foreground"),
        fontFamily: cssVar("--font-mono") || "monospace",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: themeColor("--border") },
        horzLines: { color: themeColor("--border") },
      },
      rightPriceScale: { borderColor: themeColor("--border") },
      timeScale: {
        borderColor: themeColor("--border"),
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
    });
    const gain = themeColor("--gain");
    const loss = themeColor("--loss");
    const series = chart.addSeries(CandlestickSeries, {
      upColor: gain,
      downColor: loss,
      wickUpColor: gain,
      wickDownColor: loss,
      borderUpColor: gain,
      borderDownColor: loss,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Push new data into the series.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !data) return;
    series.setData(
      data.candles.map(
        (c): CandlestickData => ({
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }),
      ),
    );
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  const symbols = data?.symbols ?? [];
  const last = data?.candles[data.candles.length - 1];
  const first = data?.candles[0];
  const change =
    last && first && first.open ? ((last.close - first.open) / first.open) * 100 : null;
  const enoughData = (data?.candles.length ?? 0) >= 2;

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm font-semibold">{data?.symbol ?? "—"}<span className="text-muted-foreground">/USD</span></span>
          {last && (
            <span className="font-mono text-sm tabular-nums">{usd(last.close)}</span>
          )}
          {change != null && (
            <span className={`font-mono text-xs tabular-nums ${change >= 0 ? "text-gain" : "text-loss"}`}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {symbols.length > 1 && (
            <select
              aria-label="Token"
              value={data?.symbol ?? ""}
              onChange={(e) => setSymbol(e.target.value)}
              className="rounded-md border border-border bg-input px-2 py-1 font-mono text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
          <div className="flex items-center rounded-md border border-border p-0.5" role="tablist" aria-label="Timeframe">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.bucket}
                type="button"
                role="tab"
                aria-selected={bucket === tf.bucket}
                onClick={() => setBucket(tf.bucket)}
                className={`rounded px-2 py-0.5 font-mono text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  bucket === tf.bucket ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="relative">
        <div ref={holder} className="h-72 w-full" />
        {!enoughData && (
          <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground">
            {error
              ? `Couldn't load candles (${error})`
              : "Building candles from the live price feed — the chart fills in as ARIA accumulates quotes."}
          </div>
        )}
      </div>
    </div>
  );
}
