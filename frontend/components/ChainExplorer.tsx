"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  fetchChain,
  fetchImpliedVolatility,
  fetchPrice,
  fetchTickers,
} from "@/lib/api";
import { money } from "@/lib/format";
import type { OptionChain, OptionType } from "@/lib/types";
import ChainTable from "./ChainTable";
import ModelVsMarket, { type Comparison } from "./ModelVsMarket";

const DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "TSLA"];

const EMPTY_COMPARISON: Comparison = {
  computing: false,
  marketMid: null,
  referenceLabel: "—",
  modelIV: null,
  modelIVNote: null,
  modelPrice: null,
  modelVolLabel: "—",
  greeks: null,
  assumedRate: 0.04,
};

export default function ChainExplorer() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_TICKERS);
  const [ticker, setTicker] = useState("AAPL");
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [loadingChain, setLoadingChain] = useState(false);
  const [chainError, setChainError] = useState<string | null>(null);
  const [expiryIndex, setExpiryIndex] = useState(0);
  const [optionType, setOptionType] = useState<OptionType>("call");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [riskFreeRate, setRiskFreeRate] = useState(0.04);
  const [comparison, setComparison] = useState<Comparison>(EMPTY_COMPARISON);

  // Ticker list (once). Falls back to the static default if it can't load.
  useEffect(() => {
    fetchTickers()
      .then((r) => setTickers(r.tickers))
      .catch(() => undefined);
  }, []);

  // Chain whenever the ticker changes.
  useEffect(() => {
    let cancelled = false;
    setLoadingChain(true);
    setChainError(null);
    setChain(null);
    setSelectedSymbol(null);
    setExpiryIndex(0);
    fetchChain(ticker)
      .then((c) => {
        if (!cancelled) setChain(c);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setChainError(
            e instanceof ApiError ? e.message : "Could not load the chain.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingChain(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const expiry = chain?.expiries[expiryIndex] ?? null;
  const quotes = expiry
    ? optionType === "call"
      ? expiry.calls
      : expiry.puts
    : [];
  const selectedQuote =
    quotes.find((q) => q.contract_symbol === selectedSymbol) ?? null;

  // Model-vs-market comparison for the selected contract.
  useEffect(() => {
    if (!chain || !expiry || !selectedSymbol) {
      setComparison(EMPTY_COMPARISON);
      return;
    }
    const list = optionType === "call" ? expiry.calls : expiry.puts;
    const quote = list.find((q) => q.contract_symbol === selectedSymbol);
    if (!quote) {
      setComparison(EMPTY_COMPARISON);
      return;
    }

    let cancelled = false;
    const { spot } = chain;
    const strike = quote.strike;
    const tte = expiry.time_to_expiry;
    const hasMid =
      quote.bid !== null && quote.ask !== null && quote.bid > 0 && quote.ask > 0;
    const marketMid = hasMid ? (quote.bid! + quote.ask!) / 2 : null;
    const referencePrice =
      marketMid ??
      (quote.last_price !== null && quote.last_price > 0
        ? quote.last_price
        : null);
    const referenceLabel = hasMid
      ? "mid of bid/ask"
      : referencePrice !== null
        ? "last trade"
        : "—";
    const providerIV = quote.implied_volatility;

    setComparison((c) => ({ ...c, computing: true }));

    (async () => {
      let modelIV: number | null = null;
      let modelIVNote: string | null = null;
      if (tte <= 0) {
        modelIVNote = "expires today (no time value)";
      } else if (referencePrice === null) {
        modelIVNote = "no bid/ask or last price";
      } else {
        try {
          const r = await fetchImpliedVolatility({
            option_type: optionType,
            market_price: referencePrice,
            spot,
            strike,
            time_to_expiry: tte,
            risk_free_rate: riskFreeRate,
          });
          modelIV = r.implied_volatility;
        } catch (e) {
          modelIVNote = e instanceof ApiError ? e.message : "could not solve";
        }
      }

      // Treat a provider IV below 1% as a stale/zero-quote artifact (common when
      // the market is closed and bid/ask come back 0) and fall back to our
      // solved IV, so the model price isn't anchored to garbage.
      const providerIVUsable = providerIV !== null && providerIV >= 0.01;
      const volForModel = providerIVUsable ? providerIV : modelIV;
      const modelVolLabel = providerIVUsable
        ? "the quoted IV"
        : modelIV !== null
          ? "the solved IV"
          : "—";

      let modelPrice: number | null = null;
      let greeks = null;
      const volToUse =
        volForModel !== null && volForModel > 0
          ? volForModel
          : tte <= 0
            ? 0.0001 // expiry: price is intrinsic regardless of vol
            : null;
      if (volToUse !== null) {
        try {
          const p = await fetchPrice({
            option_type: optionType,
            spot,
            strike,
            time_to_expiry: tte,
            risk_free_rate: riskFreeRate,
            volatility: volToUse,
          });
          modelPrice = p.price;
          greeks = p.greeks;
        } catch {
          /* leave model price null */
        }
      }

      if (!cancelled) {
        setComparison({
          computing: false,
          marketMid,
          referenceLabel,
          modelIV,
          modelIVNote,
          modelPrice,
          modelVolLabel,
          greeks,
          assumedRate: riskFreeRate,
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chain, expiry, expiryIndex, optionType, selectedSymbol, riskFreeRate]);

  const fetchedAt = chain
    ? new Date(chain.fetched_at).toLocaleString("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : null;

  return (
    <div className="chain-page">
      <div className="panel chain-bar">
        <div className="chain-bar-inner">
          <div className="field">
            <label htmlFor="c-ticker">Underlying</label>
            <select
              id="c-ticker"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
            >
              {tickers.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="c-expiry">Expiry</label>
            <select
              id="c-expiry"
              value={expiryIndex}
              disabled={!chain}
              onChange={(e) => {
                setExpiryIndex(Number(e.target.value));
                setSelectedSymbol(null);
              }}
            >
              {chain?.expiries.map((ex, i) => (
                <option key={ex.expiry} value={i}>
                  {ex.expiry} ({(ex.time_to_expiry * 365).toFixed(0)}d)
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>Type</label>
            <div className="segmented">
              {(["call", "put"] as OptionType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={optionType === t ? "active" : ""}
                  aria-pressed={optionType === t}
                  onClick={() => {
                    setOptionType(t);
                    setSelectedSymbol(null);
                  }}
                >
                  {t === "call" ? "Calls" : "Puts"}
                </button>
              ))}
            </div>
          </div>

          <div className="field" style={{ maxWidth: 110 }}>
            <label htmlFor="c-rate">
              Rate <span className="unit">(dec.)</span>
            </label>
            <input
              id="c-rate"
              type="number"
              step={0.005}
              value={riskFreeRate}
              onChange={(e) => setRiskFreeRate(Number(e.target.value))}
            />
          </div>

          <div className="chain-meta">
            {chain && (
              <>
                <span className="num">Spot ${money(chain.spot)}</span>
                <span className="chain-meta-sub">
                  as of {fetchedAt} · free source, may be delayed
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="chain-grid">
        <div className="panel">
          <div className="panel-head">
            <h2>
              {ticker} options chain
              {expiry ? ` · ${expiry.expiry}` : ""}
            </h2>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {loadingChain ? (
              <p className="skeleton">Fetching chain for {ticker}…</p>
            ) : chainError ? (
              <p className="error" style={{ margin: 16 }}>
                {chainError}
              </p>
            ) : quotes.length === 0 ? (
              <p className="skeleton">No contracts for this expiry.</p>
            ) : (
              <ChainTable
                quotes={quotes}
                spot={chain?.spot ?? 0}
                selectedSymbol={selectedSymbol}
                onSelect={(q) => setSelectedSymbol(q.contract_symbol)}
              />
            )}
          </div>
        </div>

        <ModelVsMarket
          quote={selectedQuote}
          expiry={expiry?.expiry ?? ""}
          spot={chain?.spot ?? 0}
          comparison={comparison}
        />
      </div>
    </div>
  );
}
