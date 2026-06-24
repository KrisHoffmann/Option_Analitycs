// API client. The backend owns all pricing/Greek/payoff math; this module only
// sends requests and surfaces errors. Base URL comes from NEXT_PUBLIC_API_URL
// (set in Vercel for production; defaults to local dev).

import type { ApiErrorBody, PositionRequest, PositionResponse } from "./types";

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

/** Payoff-at-expiry + current-value curves and net Greeks for a position. */
export function fetchPosition(
  request: PositionRequest,
): Promise<PositionResponse> {
  return postJson<PositionRequest, PositionResponse>("/position", request);
}
