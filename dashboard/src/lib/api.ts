// Typed client for the ARIA dashboard API (proxied to :8000 in dev).

export interface Decision {
  cycle_id: string;
  timestamp: string;
  regime: "trending" | "ranging" | "high_risk";
  mode: string;
  action: string;
  token_symbol: string | null;
  size_pct?: number;
  confidence: number;
  safety_verdict: string | null;
  outcome: string | null;
  reasoning: string;
}

export interface PortfolioPoint {
  timestamp: string;
  total_value_usd: number;
  peak_value_usd: number;
  drawdown_pct: number;
  trades_today: number;
}

export interface Trade {
  id: number;
  cycle_id: string;
  timestamp: string;
  kind: "strategy" | "compliance";
  from_token: string;
  to_token: string;
  from_amount: string | null;
  to_amount: string | null;
  tx_hash: string | null;
  status: string;
}

export interface Position {
  symbol: string;
  amount: number;
  entry_price_usd: number;
  current_price_usd: number | null;
  value_usd: number | null;
  unrealized_pct: number | null;
  unrealized_usd: number | null;
  target_pct: number | null;
  stop_loss_pct: number | null;
  peak_gain_pct: number;
  opened_at: string;
}

export interface RoundTrip {
  token: string;
  usd_in: number;
  usd_out: number;
  pnl_usd: number;
  pnl_pct: number | null;
  opened_at: string | null;
  closed_at: string;
}

export interface Performance {
  total_value_usd: number | null;
  start_value_usd: number;
  total_return_pct: number | null;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
  round_trips_total: number;
  wins: number;
  losses: number;
  win_rate_pct: number | null;
  round_trips: RoundTrip[];
}

export interface Regime {
  posture: "risk_on" | "neutral" | "cautious" | "risk_off";
  reason: string;
  allow_new_entries: boolean;
  size_multiplier: number;
  fear_greed: number | null;
  fear_greed_label: string | null;
  mcap_7d: number | null;
  updated: string;
}

export interface Status {
  last_decision: Decision | null;
  portfolio: PortfolioPoint | null;
  halted: boolean;
  halt_reason: string | null;
  trading_allowed: boolean;
  trading_reason: string;
  override: "on" | "off" | null;
  window: { start: string | null; end: string | null };
  regime: Regime | null;
  config: {
    network: string;
    execution_mode: string;
    brain: string;
    halt_drawdown_pct: number;
    max_drawdown_pct: number;
    poll_interval_sec: number;
    poll_interval_flat_sec: number;
    macro_refresh_sec: number;
    wallet: string;
  };
  trades_today: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<Status>("/api/status"),
  decisions: (limit = 100) => request<Decision[]>(`/api/decisions?limit=${limit}`),
  portfolio: (limit = 1000) => request<PortfolioPoint[]>(`/api/portfolio?limit=${limit}`),
  trades: (limit = 50) => request<Trade[]>(`/api/trades?limit=${limit}`),
  positions: () => request<Position[]>("/api/positions"),
  performance: () => request<Performance>("/api/performance"),
  setWindow: (start: string | null, end: string | null) =>
    request("/api/window", { method: "POST", body: JSON.stringify({ start, end }) }),
  setOverride: (value: "on" | "off" | null) =>
    request("/api/override", { method: "POST", body: JSON.stringify({ value }) }),
  clearHalt: () => request("/api/clear-halt", { method: "POST" }),
};
