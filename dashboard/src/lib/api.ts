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

export interface Status {
  last_decision: Decision | null;
  portfolio: PortfolioPoint | null;
  halted: boolean;
  halt_reason: string | null;
  trading_allowed: boolean;
  trading_reason: string;
  override: "on" | "off" | null;
  window: { start: string | null; end: string | null };
  config: {
    network: string;
    execution_mode: string;
    brain: string;
    halt_drawdown_pct: number;
    max_drawdown_pct: number;
    cycle_interval_min: number;
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
  setWindow: (start: string | null, end: string | null) =>
    request("/api/window", { method: "POST", body: JSON.stringify({ start, end }) }),
  setOverride: (value: "on" | "off" | null) =>
    request("/api/override", { method: "POST", body: JSON.stringify({ value }) }),
  clearHalt: () => request("/api/clear-halt", { method: "POST" }),
};
