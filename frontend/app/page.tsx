import PayoffVisualizer from "@/components/PayoffVisualizer";

// Server component: static shell + the client visualizer as the interactive
// leaf (per the Next.js "push client components down" guideline).
export default function Home() {
  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <div>
            <h1 className="app-title">Options Analytics</h1>
            <p className="app-subtitle">
              Multi-leg payoff &amp; risk under Black-Scholes-Merton
            </p>
          </div>
          <p className="app-subtitle" style={{ maxWidth: 380, textAlign: "right" }}>
            Theoretical values for analysis under stated model assumptions — not
            trading advice.
          </p>
        </div>
      </header>
      <main>
        <PayoffVisualizer />
      </main>
    </>
  );
}
