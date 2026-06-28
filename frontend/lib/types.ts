// Wire types, mirrored field-for-field to the backend Pydantic schemas in
// backend/api/schemas.py (and data/chain.py). Field names stay snake_case to
// match the JSON exactly, so there is no mapping layer to drift. When the
// Python schemas change, change these in the same commit.

export type OptionType = "call" | "put";
export type Instrument = "call" | "put" | "underlying";
export type Side = "long" | "short";

// --- contract pricing ---
export interface ContractRequest {
  option_type: OptionType;
  spot: number;
  strike: number;
  time_to_expiry: number; // years
  risk_free_rate: number; // decimal
  volatility: number; // decimal
  dividend_yield?: number; // decimal; default 0 server-side
}

export interface Greeks {
  delta: number;
  gamma: number;
  theta: number; // per year
  vega: number; // per 1.00 (100 vol points)
  rho: number; // per 1.00 (100 rate points)
}

export interface PriceResponse {
  price: number;
  greeks: Greeks;
}

// --- positions ---
export interface LegInput {
  instrument: Instrument;
  quantity: number;
  side: Side;
  strike: number | null; // null for an underlying leg
  time_to_expiry: number | null; // years; null for an underlying leg
}

export interface SpotGridSpec {
  spot_min: number;
  spot_max: number;
  num_points: number;
}

export interface PositionRequest {
  legs: LegInput[];
  grid: SpotGridSpec;
  spot: number; // current underlying; net Greeks evaluated here
  risk_free_rate: number;
  volatility: number; // flat vol for current-value curve
  dividend_yield?: number; // decimal; default 0 server-side
}

export interface PositionResponse {
  name: string;
  spots: number[];
  payoff_at_expiry: number[];
  current_value: number[];
  net_greeks: Greeks;
  net_greeks_spot: number;
}

// --- Greek-sensitivity series ---
export type SensitivityVariable =
  | "spot"
  | "strike"
  | "time_to_expiry"
  | "risk_free_rate"
  | "volatility";
export type SensitivityMetric =
  | "price"
  | "delta"
  | "gamma"
  | "theta"
  | "vega"
  | "rho";

export interface SensitivityRequest {
  contract: ContractRequest;
  variable: SensitivityVariable;
  metric: SensitivityMetric;
  variable_min: number;
  variable_max: number;
  num_points: number;
}

export interface SensitivityResponse {
  variable: string;
  metric: string;
  variable_values: number[];
  metric_values: number[];
}

// --- BSM vs binomial (CRR) comparison ---
export interface PriceComparisonRequest {
  contract: ContractRequest;
  steps: number;
}

export interface PriceComparisonResponse {
  bsm_price: number;
  greeks: Greeks;
  crr_european: number;
  crr_american: number;
  early_exercise_premium: number;
  steps: number;
}

// --- implied volatility ---
export interface ImpliedVolatilityRequest {
  option_type: OptionType;
  market_price: number;
  spot: number;
  strike: number;
  time_to_expiry: number;
  risk_free_rate: number;
}

export interface ImpliedVolatilityResponse {
  implied_volatility: number;
}

// --- options chain (mirrors backend/data/chain.py) ---
export interface OptionQuote {
  contract_symbol: string;
  option_type: string;
  strike: number;
  last_price: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  open_interest: number | null;
  implied_volatility: number | null; // provider's IV (decimal)
  in_the_money: boolean | null;
}

export interface ExpiryChain {
  expiry: string; // ISO date
  time_to_expiry: number; // years
  calls: OptionQuote[];
  puts: OptionQuote[];
}

export interface OptionChain {
  ticker: string;
  spot: number;
  fetched_at: string; // ISO datetime
  expiries: ExpiryChain[];
}

export interface TickersResponse {
  tickers: string[];
}

// --- volatility surface (mirrors backend/api/schemas.py VolSurfaceResponse,
//     which in turn mirrors pricing/vol_surface.py dataclasses) ---
export interface SurfacePoint {
  option_type: OptionType;
  strike: number;
  log_moneyness: number; // k = ln(K / F), forward moneyness
  time_to_expiry: number; // years
  implied_volatility: number; // BSM IV (decimal), from our solver
  mid_price: number;
  open_interest: number;
  relative_spread: number;
}

export interface FilterCounts {
  candidates: number;
  retained: number;
  no_two_sided_quote: number;
  spread_too_wide: number;
  insufficient_open_interest: number;
  stale_quote: number;
  solver_failed: number;
}

export interface ExpirySlice {
  expiry: string; // ISO date
  time_to_expiry: number; // years
  forward: number; // F = S * e^((r - q)T)
  points: SurfacePoint[];
  filtered: FilterCounts;
}

export interface VolSurface {
  ticker: string;
  spot: number;
  fetched_at: string; // ISO datetime
  risk_free_rate: number; // decimal
  dividend_yield: number; // decimal
  slices: ExpirySlice[];
}

// --- implied vs realized volatility (mirrors backend/api/schemas.py
//     VolComparisonResponse, which mirrors pricing/vol_comparison.py) ---
export interface RealizedVolPoint {
  date: string; // ISO date
  realized_vol: number; // annualized realized vol (decimal)
}

export interface VolComparison {
  ticker: string;
  spot: number;
  fetched_at: string; // ISO datetime
  risk_free_rate: number; // decimal
  dividend_yield: number; // decimal

  // Backward-looking series.
  realized_window_trading_days: number;
  trading_days_per_year: number;
  realized: RealizedVolPoint[];
  latest_realized_vol: number | null;

  // Forward-looking single observation (today's near-dated ATM-forward IV).
  implied_atm_vol: number | null;
  implied_expiry: string | null; // ISO date
  implied_days_to_expiry: number | null;
  implied_time_to_expiry: number | null;
  forward: number | null;
  atm_method: string | null; // "interpolated" | "nearest-strike"

  // Same-date spread and its mandatory framing.
  vol_premium: number | null;
  vol_premium_note: string;
}

// --- error shape (FastAPI) ---
export interface ApiErrorBody {
  detail: string | { msg: string }[];
}
