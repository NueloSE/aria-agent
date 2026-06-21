import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { ChevronDown, Search } from "lucide-react";
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

// lightweight-charts parses colors with its own parser that rejects oklch() (and the
// browser won't convert our oklch tokens for us), so the chart gets hex equivalents of
// the Quantum Lab dark palette. Keep these in sync with index.css if the tokens change.
const CHART = {
  gain: "#00CA85", // --gain  oklch(0.74 0.17 160)
  loss: "#FF5251", // --loss  oklch(0.68 0.21 25)
  border: "#1B1F27", // --border  oklch(0.24 0.015 260)
  text: "#92959C", // --muted-foreground  oklch(0.67 0.01 260)
};

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
        textColor: CHART.text,
        fontFamily: cssVar("--font-mono") || "monospace",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: CHART.border },
        horzLines: { color: CHART.border },
      },
      rightPriceScale: { borderColor: CHART.border },
      timeScale: {
        borderColor: CHART.border,
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: CHART.gain,
      downColor: CHART.loss,
      wickUpColor: CHART.gain,
      wickDownColor: CHART.loss,
      borderUpColor: CHART.gain,
      borderDownColor: CHART.loss,
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
            <TokenSelect value={data?.symbol ?? ""} options={symbols} onChange={setSymbol} />
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

/* Searchable, brand-styled token picker — replaces the native <select> (52 tokens). */
function TokenSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    inputRef.current?.focus();
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const q = query.trim().toUpperCase();
  const filtered = q ? options.filter((o) => o.includes(q)) : options;

  const pick = (s: string) => {
    onChange(s);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-input px-2.5 py-1 font-mono text-xs text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {value || "—"}
        <ChevronDown size={13} aria-hidden className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-1.5 w-48 overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
          <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
            <Search size={13} aria-hidden className="shrink-0 text-muted-foreground" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search token…"
              className="w-full bg-transparent font-mono text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
          <ul role="listbox" className="max-h-60 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-xs text-muted-foreground">No match</li>
            ) : (
              filtered.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={s === value}
                    onClick={() => pick(s)}
                    className={`flex w-full items-center justify-between px-3 py-1.5 text-left font-mono text-xs transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none ${
                      s === value ? "text-primary" : "text-foreground"
                    }`}
                  >
                    {s}
                    {s === value && <span className="text-primary">•</span>}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
