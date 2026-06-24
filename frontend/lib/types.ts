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
}

export interface PositionResponse {
  name: string;
  spots: number[];
  payoff_at_expiry: number[];
  current_value: number[];
  net_greeks: Greeks;
  net_greeks_spot: number;
}

// --- error shape (FastAPI) ---
export interface ApiErrorBody {
  detail: string | { msg: string }[];
}
