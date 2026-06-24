// Contextual tooltip texts for every technical term in the UI, in one place so
// they're easy to review and edit. Each entry is two plain sentences: what the
// number *means in context*, then why it matters for understanding the position.
//
// House rule: no P&L / profit / buy-sell / signal framing. Greeks are phrased as
// what changes when the value changes; everything stays on the pricing/risk side.

export interface GlossaryEntry {
  term: string;
  body: string;
}

export const GLOSSARY = {
  // ---- the Greeks ----
  delta: {
    term: "Delta",
    body: "How much the option's value moves for a $1 move in the underlying: a delta of 0.62 means the option gains about $0.62 in value when the underlying moves $1. It tells you how stock-like the position currently is — its directional exposure to the underlying.",
  },
  gamma: {
    term: "Gamma",
    body: "How fast delta itself changes as the stock moves: a gamma of 0.05 means delta shifts by about 0.05 for each $1 move in the stock. It matters because high gamma means your directional exposure can change quickly, so a position that looks balanced now may not stay that way.",
  },
  theta: {
    term: "Theta",
    body: "How much value the option loses as one year of time passes, holding everything else fixed — divide by 365 for the daily figure. It matters because an option is a wasting asset: time decay works against long options and in favour of short ones.",
  },
  vega: {
    term: "Vega",
    body: "How much the option's value changes for a 1.00 (100 percentage-point) change in volatility — divide by 100 for the change per one volatility point. It isolates the position's exposure to shifts in how much movement the market expects, separate from the stock's direction.",
  },
  rho: {
    term: "Rho",
    body: "How much the option's value changes for a 1.00 (100 percentage-point) change in the risk-free interest rate — divide by 100 for the change per one rate point. It is usually the smallest Greek, mattering most for long-dated options where discounting has more time to act.",
  },

  // ---- volatility & price concepts ----
  impliedVolatility: {
    term: "Implied volatility",
    body: "The volatility that makes the model's price match the option's market price — the market's expectation of how much the stock will move, read backwards out of the option's price. It matters because it is the one model input you can't observe directly, and comparing it across contracts shows where the market expects the most movement.",
  },
  modelPrice: {
    term: "Model price",
    body: "What the Black-Scholes-Merton model says the contract is worth given your inputs (spot, strike, time, rate, volatility). It is a value under stated assumptions, not a fair price — differences from the market usually reflect those assumptions or the data rather than a mispricing.",
  },
  intrinsicValue: {
    term: "Intrinsic value",
    body: "What the option would be worth if it expired right now: for a call, the stock price minus the strike (never below zero); for a put, the strike minus the stock. It is the floor under the option's price — everything above it is time value.",
  },
  timeValue: {
    term: "Time value",
    body: "The part of an option's price above its intrinsic value — what the option is worth for the chance the stock moves favourably before expiry. It shrinks toward zero as expiry approaches, which is exactly what theta measures.",
  },

  // ---- inputs ----
  spot: {
    term: "Spot price",
    body: "The underlying stock's current price. Every price and Greek here is computed at this spot, and the payoff curves show how the position's value changes as the spot moves.",
  },
  strike: {
    term: "Strike",
    body: "The fixed price at which the option can be exercised. Its distance from the spot sets whether an option is in-, at-, or out-of-the-money, which drives most of the option's behaviour.",
  },
  timeToExpiry: {
    term: "Time to expiry",
    body: "How long until the option expires, in years (0.5 = six months). More time means more chance for the stock to move, so longer-dated options carry more time value and decay more slowly.",
  },
  riskFreeRate: {
    term: "Risk-free rate",
    body: "The assumed annual interest rate used to discount future payoffs back to today, entered as a decimal (0.04 = 4%). Here it is a constant you choose, not a live feed; it mainly affects longer-dated options.",
  },
  volatility: {
    term: "Volatility",
    body: "How much the stock is assumed to move, annualized, as a decimal (0.25 = 25%). It is the single biggest driver of an option's time value — higher volatility means a wider range of outcomes and a more valuable option.",
  },

  // ---- market quotes ----
  bid: {
    term: "Bid",
    body: "The highest price a buyer is currently willing to pay for the contract. Together with the ask it brackets where the option is trading right now.",
  },
  ask: {
    term: "Ask",
    body: "The lowest price a seller is currently willing to accept for the contract. The gap between bid and ask (the spread) widens for illiquid options and indicates less reliable pricing.",
  },
  mid: {
    term: "Mid",
    body: "The midpoint between the bid and ask, used here as a single reference market price. It is a steadier input than the last trade, which can be hours stale on an illiquid contract.",
  },

  // ---- strategies ----
  verticalSpread: {
    term: "Vertical spread",
    body: "A long and a short option of the same type and expiry at different strikes. It confines the position's value to a defined range between the two strikes, trading away the open-ended exposure of a single option.",
  },
  straddle: {
    term: "Straddle",
    body: "A call and a put at the same strike and expiry held together. Its value responds to the size of the stock's move rather than its direction — rising as the stock moves far either way, decaying as it sits still.",
  },
  strangle: {
    term: "Strangle",
    body: "An out-of-the-money call and put held together, with the call strike above spot and the put strike below. It behaves like a straddle but needs a larger move before its value responds, since both legs start out-of-the-money.",
  },
  calendarSpread: {
    term: "Calendar spread",
    body: "A short near-dated option and a long far-dated option at the same strike, capturing the difference in their rates of time decay. Its two legs don't expire together, so read its value from the current-value curve near the near-date expiry.",
  },
  coveredCall: {
    term: "Covered call",
    body: "Long stock with a short call written against it. The short call caps the position's value above its strike in exchange for the premium received, while the stock keeps the full downside exposure.",
  },
  ironCondor: {
    term: "Iron condor",
    body: "A short out-of-the-money put spread and a short out-of-the-money call spread held together. Its value is highest when the stock stays between the short strikes, and the two long wings define the maximum risk.",
  },
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
