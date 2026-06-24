import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Options Analytics",
  description:
    "Pricing and risk-analysis for equity options — Black-Scholes-Merton, the Greeks, implied volatility, and multi-leg payoffs.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
