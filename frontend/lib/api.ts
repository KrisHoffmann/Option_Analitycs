// API client. The backend owns all pricing/Greek/payoff math; this module only
// sends requests and surfaces errors. Base URL comes from NEXT_PUBLIC_API_URL
// (set in Vercel for production; defaults to local dev).

import type {
  ApiErrorBody,
  ContractRequest,
  ImpliedVolatilityRequest,
  ImpliedVolatilityResponse,
  OptionChain,
  PositionRequest,
  PositionResponse,
  PositionScenarioRequest,
  PositionScenarioResponse,
  PriceComparisonRequest,
  PriceComparisonResponse,
  PriceResponse,
  SensitivityRequest,
  SensitivityResponse,
  TickersResponse,
  VolComparison,
  VolSurface,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/** A failed API call, carrying the backend's human-readable detail message. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function extractDetail(body: ApiErrorBody | undefined, status: number): string {
  if (!body) return `Request failed (${status}).`;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail) && body.detail.length > 0) {
    return body.detail.map((d) => d.msg).join("; ");
  }
  return `Request failed (${status}).`;
}

async function handleResponse<TRes>(response: Response): Promise<TRes> {
  if (!response.ok) {
    let body: ApiErrorBody | undefined;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = undefined;
    }
    throw new ApiError(extractDetail(body, response.status), response.status);
  }
  return (await response.json()) as TRes;
}

async function getJson<TRes>(path: string): Promise<TRes> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`);
  } catch {
    throw new ApiError(
      `Could not reach the pricing service at ${BASE_URL}. Is the backend running?`,
      0,
    );
  }
  return handleResponse<TRes>(response);
}

async function postJson<TReq, TRes>(path: string, payload: TReq): Promise<TRes> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(
      `Could not reach the pricing service at ${BASE_URL}. Is the backend running?`,
      0,
    );
  }
  return handleResponse<TRes>(response);
}

/** Payoff-at-expiry + current-value curves and net Greeks for a position. */
export function fetchPosition(
  request: PositionRequest,
): Promise<PositionResponse> {
  return postJson<PositionRequest, PositionResponse>("/position", request);
}

/** Position model value across a grid of spot and volatility shocks. */
export function fetchPositionScenario(
  request: PositionScenarioRequest,
): Promise<PositionScenarioResponse> {
  return postJson<PositionScenarioRequest, PositionScenarioResponse>(
    "/position-scenario",
    request,
  );
}

/** Price + all five Greeks for a single contract (point values). */
export function fetchPrice(request: ContractRequest): Promise<PriceResponse> {
  return postJson<ContractRequest, PriceResponse>("/price", request);
}

/** A price/Greek series as one input is swept over a range. */
export function fetchSensitivity(
  request: SensitivityRequest,
): Promise<SensitivityResponse> {
  return postJson<SensitivityRequest, SensitivityResponse>(
    "/sensitivity",
    request,
  );
}

/** Compare BSM with the CRR binomial model (European + American exercise). */
export function fetchPriceComparison(
  request: PriceComparisonRequest,
): Promise<PriceComparisonResponse> {
  return postJson<PriceComparisonRequest, PriceComparisonResponse>(
    "/price-comparison",
    request,
  );
}

/** Back out the implied volatility for an observed market price. */
export function fetchImpliedVolatility(
  request: ImpliedVolatilityRequest,
): Promise<ImpliedVolatilityResponse> {
  return postJson<ImpliedVolatilityRequest, ImpliedVolatilityResponse>(
    "/implied-volatility",
    request,
  );
}

/** The list of underlyings a chain can be fetched for. */
export function fetchTickers(): Promise<TickersResponse> {
  return getJson<TickersResponse>("/tickers");
}

/** The live options chain for a supported ticker. */
export function fetchChain(ticker: string): Promise<OptionChain> {
  return getJson<OptionChain>(`/chain/${encodeURIComponent(ticker)}`);
}

/** The implied-volatility surface (OTM-wing IV grid) for a supported ticker. */
export function fetchVolSurface(ticker: string): Promise<VolSurface> {
  return getJson<VolSurface>(`/vol-surface/${encodeURIComponent(ticker)}`);
}

/** Forward implied vs backward realized volatility for a supported ticker. */
export function fetchVolComparison(ticker: string): Promise<VolComparison> {
  return getJson<VolComparison>(
    `/vol-comparison/${encodeURIComponent(ticker)}`,
  );
}
