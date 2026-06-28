"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Payoff" },
  { href: "/greeks", label: "Greeks" },
  { href: "/chain", label: "Chain" },
  { href: "/surface", label: "Surface" },
  { href: "/vol-compare", label: "IV vs RV" },
  { href: "/scenario", label: "Scenario" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="app-nav" aria-label="Primary">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`nav-link${active ? " active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
