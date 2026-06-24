"use client";

import { decimals, money } from "@/lib/format";
import type { OptionQuote } from "@/lib/types";

interface ChainTableProps {
  quotes: OptionQuote[];
  spot: number;
  selectedSymbol: string | null;
  onSelect: (quote: OptionQuote) => void;
}

function cell(value: number | null, dp: number): string {
  return value === null ? "—" : decimals(value, dp);
}

/** Strike closest to spot — handy visual anchor (the at-the-money row). */
function atmStrike(quotes: OptionQuote[], spot: number): number | null {
  if (quotes.length === 0) return null;
  return quotes.reduce((best, q) =>
    Math.abs(q.strike - spot) < Math.abs(best.strike - spot) ? q : best,
  ).strike;
}

export default function ChainTable({
  quotes,
  spot,
  selectedSymbol,
  onSelect,
}: ChainTableProps) {
  const atm = atmStrike(quotes, spot);

  return (
    <div className="chain-table-wrap">
      <table className="chain-table">
        <thead>
          <tr>
            <th className="r">Strike</th>
            <th className="r">Bid</th>
            <th className="r">Ask</th>
            <th className="r">Last</th>
            <th className="r">IV</th>
            <th className="r">Vol</th>
            <th className="r">OI</th>
          </tr>
        </thead>
        <tbody>
          {quotes.map((q) => {
            const selected = q.contract_symbol === selectedSymbol;
            const classes = [
              q.in_the_money ? "itm" : "",
              q.strike === atm ? "atm" : "",
              selected ? "selected" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <tr
                key={q.contract_symbol}
                className={classes}
                onClick={() => onSelect(q)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(q);
                  }
                }}
                aria-selected={selected}
              >
                <td className="r num strike">{money(q.strike)}</td>
                <td className="r num">{cell(q.bid, 2)}</td>
                <td className="r num">{cell(q.ask, 2)}</td>
                <td className="r num">{cell(q.last_price, 2)}</td>
                <td className="r num">{cell(q.implied_volatility, 4)}</td>
                <td className="r num muted">{q.volume ?? "—"}</td>
                <td className="r num muted">{q.open_interest ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
