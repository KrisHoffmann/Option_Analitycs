import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Fira_Sans, Fira_Code } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

// Fira Sans for UI text; Fira Code (monospace, tabular figures) for every
// number, so decimals and Greeks align in columns -- the legibility the brief
// demands of a quant tool.
const firaSans = Fira_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Options Analytics — Payoff & Risk",
  description:
    "Pricing and risk-analysis for equity options: Black-Scholes-Merton, the Greeks, implied volatility, and multi-leg payoff curves.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${firaSans.variable} ${firaCode.variable}`}>
      <body>
        <header className="app-header">
          <div className="app-header-inner">
            <div className="brand">
              <h1 className="app-title">Options Analytics</h1>
              <p className="app-subtitle">
                Pricing &amp; risk under Black-Scholes-Merton
              </p>
            </div>
            <Nav />
            <p className="app-note">
              Theoretical values under stated assumptions — not trading advice.
            </p>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
