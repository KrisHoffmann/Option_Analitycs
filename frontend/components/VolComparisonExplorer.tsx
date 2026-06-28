"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, fetchTickers, fetchVolComparison } from "@/lib/api";
import { money } from "@/lib/format";
import type { VolComparison } from "@/lib/types";
import InfoTip from "./InfoTip";
import VolComparisonChart from "./VolComparisonChart";

const DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "TSLA"];

/** A labelled forward/backward statistic for the readout row. */
function Readout({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="vc-readout-item">
      <span className="vc-readout-label">{label}</span>
      <span className="vc-readout-value num">{value}</span>
      {sub ? <span className="vc-readout-sub">{sub}</span> : null}
    </div>
  );
}

export default function VolComparisonExplorer() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_TICKERS);
  const [ticker, setTicker] = useState("SPY");
  const [data, setData] = useState<VolComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTickers()
      .then((r) => setTickers(r.tickers))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetchVolComparison(ticker)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError
              ? e.message
              : "Could not load the volatility comparison.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const fetchedAt = useMemo(
    () =>
      data
        ? new Date(data.fetched_at).toLocaleString("en-GB", {
            dateStyle: "medium",
            timeStyle: "short",
          })
        : null,
    [data],
  );

  const impliedSolved = data != null && data.implied_atm_vol !== null;

  return (
    <div className="chain-page">
      <div className="panel chain-bar">
        <div className="chain-bar-inner">
          <div className="field">
            <label htmlFor="vc-ticker">Underlying</label>
            <select
              id="vc-ticker"
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

          <div className="chain-meta">
            {data && (
              <>
                <span className="num">Spot ${money(data.spot)}</span>
                <span className="chain-meta-sub">
                  r {(data.risk_free_rate * 100).toFixed(1)}% · q{" "}
                  {(data.dividend_yield * 100).toFixed(2)}% · as of {fetchedAt} ·
                  free source, may be delayed
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <p className="surf-thesis">
        Implied volatility is forward-looking — the market&rsquo;s expectation
        priced into options. Realized volatility is backward-looking — what the
        stock actually did. This view holds the two side by side over a common
        horizon; their same-date gap is a risk measure, not a forecast or signal.
      </p>

      {loading ? (
        <div className="panel">
          <p className="skeleton">Loading the volatility comparison for {ticker}…</p>
        </div>
      ) : error ? (
        <div className="panel">
          <p className="error" style={{ margin: 16 }}>
            {error}
          </p>
        </div>
      ) : data ? (
        <>
          <div className="panel surf-panel">
            <div className="panel-head">
              <h2>
                {data.ticker} — implied vs realized volatility
                <InfoTip k="volRiskPremium" />
              </h2>
            </div>
            <div className="panel-body">
              <div className="vc-readout">
                <Readout label="Spot" value={`$${money(data.spot)}`} />
                <Readout
                  label="Realized (latest)"
                  value={
                    data.latest_realized_vol !== null
                      ? `${(data.latest_realized_vol * 100).toFixed(1)}%`
                      : "—"
                  }
                  sub={`trailing ${data.realized_window_trading_days}d`}
                />
                <Readout
                  label="Implied (ATM)"
                  value={
                    impliedSolved
                      ? `${(data.implied_atm_vol! * 100).toFixed(1)}%`
                      : "unsolved"
                  }
                  sub={
                    impliedSolved && data.implied_days_to_expiry !== null
                      ? `${data.implied_days_to_expiry}d · ${data.atm_method}`
                      : "no ATM read"
                  }
                />
                <Readout
                  label="Premium"
                  value={
                    data.vol_premium !== null
                      ? `${data.vol_premium >= 0 ? "+" : ""}${(data.vol_premium * 100).toFixed(1)} pts`
                      : "—"
                  }
                  sub="implied − realized"
                />
              </div>

              <VolComparisonChart
                ticker={data.ticker}
                realized={data.realized}
                windowDays={data.realized_window_trading_days}
                impliedAtmVol={data.implied_atm_vol}
                impliedDaysToExpiry={data.implied_days_to_expiry}
                premiumNote={data.vol_premium_note}
              />

              {!impliedSolved && (
                <p className="hint">
                  No at-the-money implied volatility could be solved from the
                  current chain for {data.ticker} (no contract bracketing the
                  forward cleared the quote filters). The realized history above
                  is unaffected; only the forward marker and premium are
                  withheld.
                </p>
              )}
            </div>
          </div>

          <div className="panel surf-panel">
            <div className="panel-body surf-limits">
              <h3>Reading this honestly</h3>
              <ul>
                <li>
                  <strong>Forward vs backward, not forecast vs outcome.</strong>{" "}
                  The implied point is the market&rsquo;s expectation over the
                  option&rsquo;s remaining life; the realized curve is what
                  already happened over a trailing window. We compare them on the
                  same date, not as a prediction checked against its result.
                </li>
                <li>
                  <strong>One implied observation, not a series.</strong> A free
                  data source gives only today&rsquo;s option chain, and this
                  tool stores no history, so there is no past implied-vol line to
                  draw — we show today&rsquo;s reading as a single forward marker
                  rather than fabricate one across the chart.
                </li>
                <li>
                  <strong>Horizon-matched.</strong> Realized vol uses a{" "}
                  {data.realized_window_trading_days}-trading-day window (about
                  one calendar month) to match the ~30-day implied horizon, and
                  is annualized by{" "}
                  <span className="num">√252</span> trading days — not √365.
                </li>
                <li>
                  <strong>Close-to-close estimator.</strong> Realized vol is the
                  standard deviation of daily close-to-close log returns.
                  Range-based estimators (Parkinson, Garman-Klass) are
                  lower-variance alternatives, consciously not used here for
                  simplicity.
                </li>
                <li>
                  Implied vol is the ATM-forward value from our own solver
                  (interpolated to{" "}
                  <span className="num">k = 0</span>), never the data
                  provider&rsquo;s field. Quotes are free and may be delayed;{" "}
                  <span className="num">r</span> is a fixed assumed rate and{" "}
                  <span className="num">q</span> a constant dividend-yield
                  approximation.
                </li>
              </ul>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
