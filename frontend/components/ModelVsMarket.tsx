"use client";

import { decimals, money } from "@/lib/format";
import type { Greeks, OptionQuote } from "@/lib/types";
import InfoTip from "./InfoTip";

export interface Comparison {
  computing: boolean;
  marketMid: number | null;
  referenceLabel: string; // "mid of bid/ask" or "last trade"
  modelIV: number | null;
  modelIVNote: string | null;
  modelPrice: number | null;
  modelVolLabel: string; // which vol the model price uses
  greeks: Greeks | null;
  assumedRate: number;
}

interface ModelVsMarketProps {
  quote: OptionQuote | null;
  expiry: string;
  spot: number;
  comparison: Comparison;
}

function val(value: number | null, dp: number, prefix = ""): string {
  return value === null ? "—" : `${prefix}${decimals(value, dp)}`;
}

export default function ModelVsMarket({
  quote,
  expiry,
  spot,
  comparison: c,
}: ModelVsMarketProps) {
  if (!quote) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h2>Model vs. market</h2>
        </div>
        <div className="panel-body">
          <p className="skeleton">
            Select a contract from the chain to compare the model price and
            implied volatility with the market quote.
          </p>
        </div>
      </div>
    );
  }

  const priceGap =
    c.modelPrice !== null && c.marketMid !== null
      ? c.modelPrice - c.marketMid
      : null;

  // Intrinsic value is trivial payoff arithmetic (allowed client-side per the
  // architecture doc); time value is the model price above intrinsic.
  const intrinsic =
    quote.option_type === "call"
      ? Math.max(spot - quote.strike, 0)
      : Math.max(quote.strike - spot, 0);
  const timeValue = c.modelPrice !== null ? c.modelPrice - intrinsic : null;

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Model vs. market</h2>
        <span className="hint num" style={{ margin: 0 }}>
          {quote.option_type} · K {money(quote.strike)} · exp {expiry}
        </span>
      </div>
      <div className="panel-body">
        <div className="kv-section">
          <h3 className="kv-title">Market</h3>
          <dl className="kv">
            <dt>Bid / Ask</dt>
            <dd className="num">
              {val(quote.bid, 2)} / {val(quote.ask, 2)}
            </dd>
            <dt>
              Mid <InfoTip k="mid" />
            </dt>
            <dd className="num">{val(c.marketMid, 2, "$")}</dd>
            <dt>Last</dt>
            <dd className="num">{val(quote.last_price, 2, "$")}</dd>
            <dt>
              Implied vol (quoted) <InfoTip k="impliedVolatility" />
            </dt>
            <dd className="num">{val(quote.implied_volatility, 4)}</dd>
          </dl>
        </div>

        <div className="kv-section">
          <h3 className="kv-title">Model (Black-Scholes-Merton)</h3>
          <dl className="kv">
            <dt>
              Implied vol (solved) <InfoTip k="impliedVolatility" />
            </dt>
            <dd className="num">
              {c.modelIV !== null ? (
                decimals(c.modelIV, 4)
              ) : (
                <span className="muted">{c.modelIVNote ?? "—"}</span>
              )}
            </dd>
            <dt>
              Model price <InfoTip k="modelPrice" />
            </dt>
            <dd className="num">{val(c.modelPrice, 2, "$")}</dd>
            <dt>
              Intrinsic value <InfoTip k="intrinsicValue" />
            </dt>
            <dd className="num">{val(intrinsic, 2, "$")}</dd>
            <dt>
              Time value <InfoTip k="timeValue" />
            </dt>
            <dd className="num">{val(timeValue, 2, "$")}</dd>
            <dt>Model − market mid</dt>
            <dd className="num">
              {priceGap === null
                ? "—"
                : `${priceGap >= 0 ? "+" : ""}${decimals(priceGap, 2)}`}
            </dd>
          </dl>
        </div>

        <div className="kv-section">
          <h3 className="kv-title">
            Greeks <span className="kv-sub">at the model volatility</span>
          </h3>
          {c.greeks ? (
            <dl className="kv">
              <dt>Delta</dt>
              <dd className="num">{decimals(c.greeks.delta, 4)}</dd>
              <dt>Gamma</dt>
              <dd className="num">{decimals(c.greeks.gamma, 4)}</dd>
              <dt>Theta (/yr)</dt>
              <dd className="num">{decimals(c.greeks.theta, 4)}</dd>
              <dt>Vega (/1.00)</dt>
              <dd className="num">{decimals(c.greeks.vega, 4)}</dd>
              <dt>Rho (/1.00)</dt>
              <dd className="num">{decimals(c.greeks.rho, 4)}</dd>
            </dl>
          ) : (
            <p className="hint">Not available for this contract.</p>
          )}
        </div>

        <p className="hint">
          BSM · European exercise · no dividends (q = 0) · assumed constant
          risk-free rate r = {decimals(c.assumedRate, 3)}. Model implied vol is
          solved from the {c.referenceLabel}; model price uses{" "}
          {c.modelVolLabel}. A model price is a value under these assumptions,
          not a fair price.
        </p>
      </div>
    </div>
  );
}
