"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, fetchTickers, fetchVolSurface } from "@/lib/api";
import { money } from "@/lib/format";
import { centralWindow } from "@/lib/scale";
import type { VolSurface } from "@/lib/types";
import { viridis } from "@/lib/viridis";
import InfoTip from "./InfoTip";
import SmileSlices from "./SmileSlices";
import VolSurfaceScatter from "./VolSurfaceScatter";

const DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "TSLA"];

/** Fixed IV colour scale across the whole surface (so colour is comparable
 *  between expiries), padded a touch and rounded outward to clean bounds. */
function ivScale(surface: VolSurface): [number, number] {
  const ivs = surface.slices.flatMap((s) =>
    s.points.map((p) => p.implied_volatility),
  );
  if (ivs.length === 0) return [0.1, 0.5];
  const lo = Math.floor(Math.min(...ivs) * 20) / 20; // round to 5% grid
  const hi = Math.ceil(Math.max(...ivs) * 20) / 20;
  return [lo, hi === lo ? lo + 0.05 : hi];
}

/** Horizontal viridis legend with numeric IV ticks -- colour is never the only
 *  encoding, the scale is always labelled. */
function ColorLegend({ lo, hi }: { lo: number; hi: number }) {
  const stops = Array.from({ length: 11 }, (_, i) => i / 10);
  const mid = (lo + hi) / 2;
  return (
    <div className="surf-legend">
      <span className="surf-legend-cap">
        Implied volatility
        <InfoTip k="impliedVolatility" />
      </span>
      <div className="surf-legend-bar-wrap">
        <div className="surf-legend-bar">
          {stops.map((t) => (
            <span
              key={t}
              style={{ background: viridis(t), flex: 1 }}
              aria-hidden="true"
            />
          ))}
        </div>
        <div className="surf-legend-ticks num">
          <span>{(lo * 100).toFixed(0)}%</span>
          <span>{(mid * 100).toFixed(0)}%</span>
          <span>{(hi * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}

export default function VolSurfaceExplorer() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_TICKERS);
  const [ticker, setTicker] = useState("SPY");
  const [surface, setSurface] = useState<VolSurface | null>(null);
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
    setSurface(null);
    fetchVolSurface(ticker)
      .then((s) => {
        if (!cancelled) setSurface(s);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? e.message : "Could not load the surface.",
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

  const [ivLo, ivHi] = useMemo(
    () => (surface ? ivScale(surface) : [0.1, 0.5]),
    [surface],
  );

  const totalPoints = useMemo(
    () =>
      surface
        ? surface.slices.reduce((n, s) => n + s.points.length, 0)
        : 0,
    [surface],
  );

  // Data-driven view window (central ~90% of points by forward log-moneyness),
  // shared by both charts so the liquid deep-OTM tail doesn't crush the smile.
  const kWindow = useMemo<[number, number]>(() => {
    if (!surface) return [-0.5, 0.5];
    const ks = surface.slices.flatMap((s) =>
      s.points.map((p) => p.log_moneyness),
    );
    return ks.length ? centralWindow(ks, 0.05) : [-0.5, 0.5];
  }, [surface]);

  const fetchedAt = surface
    ? new Date(surface.fetched_at).toLocaleString("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : null;

  return (
    <div className="chain-page">
      <div className="panel chain-bar">
        <div className="chain-bar-inner">
          <div className="field">
            <label htmlFor="s-ticker">Underlying</label>
            <select
              id="s-ticker"
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
            {surface && (
              <>
                <span className="num">Spot ${money(surface.spot)}</span>
                <span className="chain-meta-sub">
                  r {(surface.risk_free_rate * 100).toFixed(1)}% · q{" "}
                  {(surface.dividend_yield * 100).toFixed(2)}% · as of {fetchedAt}{" "}
                  · free source, may be delayed
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <p className="surf-thesis">
        IV surface built from market quotes under BSM assumptions — the smile is
        evidence that BSM&rsquo;s constant-volatility assumption fails in
        practice.
      </p>

      {loading ? (
        <div className="panel">
          <p className="skeleton">Building the surface for {ticker}…</p>
        </div>
      ) : error ? (
        <div className="panel">
          <p className="error" style={{ margin: 16 }}>
            {error}
          </p>
        </div>
      ) : surface && totalPoints > 0 ? (
        <>
          <div className="panel surf-panel">
            <div className="panel-head">
              <h2>
                {surface.ticker} — implied-volatility surface
                <InfoTip k="volSurface" />
              </h2>
              <ColorLegend lo={ivLo} hi={ivHi} />
            </div>
            <div className="panel-body">
              <VolSurfaceScatter
                surface={surface}
                ivMin={ivLo}
                ivMax={ivHi}
                kWindow={kWindow}
              />
              <div className="surf-notes">
                <p>
                  <strong>What the shape says.</strong> Each dot is one OTM
                  contract&rsquo;s implied volatility, placed at its forward
                  log-moneyness{" "}
                  <InfoTip k="logMoneyness" /> and true time to expiry. The
                  vertical{" "}
                  <span className="num">k = 0</span> line is at-the-money-forward{" "}
                  <InfoTip k="forwardPrice" />. IV rising as you move left into
                  downside strikes is the volatility skew{" "}
                  <InfoTip k="volSkew" />; IV changing down a column at fixed
                  moneyness is the term structure{" "}
                  <InfoTip k="termStructure" />.
                </p>
                <p>
                  <strong>Two different facts, same cause.</strong> The skew
                  above is measured <em>on the points that exist</em>. The thin
                  upside wing is a separate, plainer fact: far-OTM index calls
                  often have no two-sided market, so they are filtered out — a
                  coverage asymmetry{" "}
                  <InfoTip k="coverageAsymmetry" />, not a volatility reading.
                  Both trace back to the same demand for downside protection.
                </p>
              </div>
            </div>
          </div>

          <div className="panel surf-panel">
            <div className="panel-head">
              <h2>Smile slices — IV versus moneyness, per expiry</h2>
            </div>
            <div className="panel-body">
              <SmileSlices surface={surface} kWindow={kWindow} />
              <p className="surf-notes">
                Toggle expiries above. Drawn as curves, the skew is unmistakable:
                the lines lift toward low <span className="num">k</span>. If BSM
                held, every line would be flat and they would stack on top of one
                another.
              </p>
            </div>
          </div>

          <div className="panel surf-panel">
            <div className="panel-head">
              <h2>Data-quality audit — what was filtered, per expiry</h2>
            </div>
            <div className="panel-body" style={{ padding: 0 }}>
              <div className="chain-table-wrap">
                <table className="chain-table surf-audit">
                  <thead>
                    <tr>
                      <th>Expiry</th>
                      <th className="r">Days</th>
                      <th className="r">Shown</th>
                      <th className="r">Filtered</th>
                      <th className="r">No quote</th>
                      <th className="r">Wide spread</th>
                      <th className="r">Low OI</th>
                      <th className="r">Stale</th>
                      <th className="r">No solve</th>
                    </tr>
                  </thead>
                  <tbody>
                    {surface.slices.map((s) => {
                      const f = s.filtered;
                      const dropped = f.candidates - f.retained;
                      return (
                        <tr key={s.expiry}>
                          <td className="strike">{s.expiry}</td>
                          <td className="r num">
                            {Math.round(s.time_to_expiry * 365)}
                          </td>
                          <td className="r num">{f.retained}</td>
                          <td className="r num muted">{dropped}</td>
                          <td className="r num muted">{f.no_two_sided_quote}</td>
                          <td className="r num muted">{f.spread_too_wide}</td>
                          <td className="r num muted">
                            {f.insufficient_open_interest}
                          </td>
                          <td className="r num muted">{f.stale_quote}</td>
                          <td className="r num muted">{f.solver_failed}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="panel surf-panel">
            <div className="panel-body surf-limits">
              <h3>Reading this honestly</h3>
              <ul>
                <li>
                  We invert each price with a <strong>European</strong> BSM model
                  even though listed equity options are American. We restrict to
                  the OTM wing — where the early-exercise premium is smallest — to
                  keep that approximation defensible, but it is still an
                  approximation.
                </li>
                <li>
                  Quotes come from a free, delayed source. Bid/ask can be stale or
                  one-sided, especially far from the money; the filters above
                  remove the worst of it rather than perfect it.
                </li>
                <li>
                  Gaps are shown, never filled. There is no interpolation and no
                  fitted (e.g. SVI) surface between the dots — absence of a point
                  means no contract cleared the filters, not zero volatility.
                </li>
                <li>
                  The dividend yield <span className="num">q</span> is a constant
                  continuous approximation of discrete dividends, and{" "}
                  <span className="num">r</span> is a fixed assumed rate, not a
                  live curve.
                </li>
              </ul>
            </div>
          </div>
        </>
      ) : surface ? (
        <div className="panel">
          <p className="skeleton">
            No contracts cleared the quote filters for {ticker} right now. This
            happens when markets are closed and quotes come back one-sided.
          </p>
        </div>
      ) : null}
    </div>
  );
}
