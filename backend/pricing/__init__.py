"""Pure pricing math: Black-Scholes-Merton, the Greeks, the IV solver.

Everything in this package takes numbers and returns numbers — no network, no
file I/O, no globals, no FastAPI imports. That purity is what makes it testable
in isolation and validatable against external references (see
docs/finance-standards.md).
"""
