"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, fetchPriceComparison } from "@/lib/api";
import { money } from "@/lib/format";
import type { ContractRequest, PriceComparisonResponse } from "@/lib/types";
import InfoTip from "./InfoTip";

const STEPS = 200; // tree steps for the UI: close to BSM, still instant
const NEAR_ZERO = 0.005; // premium below this reads as "no early-exercise value"

export default function ModelComparison({
  contract,
}: {
  contract: ContractRequest;
}) {
  const [data, setData] = useState<PriceComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Re-fetch when any contract input changes.
  const key = JSON.stringify(contract);
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      fetchPriceComparison({ contract, steps: STEPS })
        .then((r) => {
          setData(r);
          setError(null);
        })
        .catch((e: unknown) =>
          setError(
            e instanceof ApiError ? e.message : "Could not compute the comparison.",
          ),
        );
    }, 200);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
    // contract is captured via `key`; eslint-disable handled by key dependency
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const premium = data?.early_exercise_premium ?? 0;
  const premiumIsZero = premium < NEAR_ZERO;

  return (
    <div className="panel" style={{ marginTop: 24 }}>
      <div className="panel-head">
        <h2>Model comparison</h2>
        <span className="hint num" style={{ margin: 0 }}>
          CRR · {STEPS} steps
        </span>
      </div>
      <div className="panel-body">
        {error ? (
          <p className="error">{error}</p>
        ) : !data ? (
          <p className="hint">Computing…</p>
        ) : (
          <>
            <div className="cmp-grid">
              <div className="cmp-cell">
                <span className="cmp-label">BSM</span>
                <span className="cmp-value num">${money(data.bsm_price)}</span>
                <span className="cmp-sub">European</span>
              </div>
              <div className="cmp-cell">
                <span className="cmp-label">CRR</span>
                <span className="cmp-value num">${money(data.crr_european)}</span>
                <span className="cmp-sub">European</span>
              </div>
              <div className="cmp-cell">
                <span className="cmp-label">CRR</span>
                <span className="cmp-value num">${money(data.crr_american)}</span>
                <span className="cmp-sub">American</span>
              </div>
            </div>

            <div className="cmp-premium">
              <span className="cmp-premium-label">
                Early-exercise premium
                <InfoTip k="earlyExercisePremium" />
              </span>
              <span className="cmp-premium-value num">
                ${money(premium)}
              </span>
            </div>

            <p className="hint">
              {premiumIsZero ? (
                <>
                  ≈ $0 for this contract: early exercise adds essentially no
                  value.{" "}
                  {contract.option_type === "call"
                    ? "An American call on a non-dividend-paying stock is never worth exercising early."
                    : "With these inputs there is little incentive to exercise this put early."}
                </>
              ) : (
                <>
                  American options can be exercised at any time before expiry;
                  this is the extra value that flexibility provides over otherwise
                  identical European exercise.
                </>
              )}
            </p>
            <p className="hint">
              BSM prices European exercise only; the binomial (CRR) model prices
              both. CRR European and BSM agree closely and converge as the step
              count grows.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
