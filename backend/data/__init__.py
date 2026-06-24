"""Options-chain data access, behind a single interface.

Downstream code depends on our own `Chain` type, never on a provider's raw
shape. One adapter module does the provider-specific fetching and maps to
`Chain`, so swapping the data source is a one-file change (see
docs/architecture.md).
"""
