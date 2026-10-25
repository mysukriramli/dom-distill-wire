# 📰 DOM Distill Wire

An autonomous, zero-maintenance data infrastructure running entirely on GitHub Actions. It pulls technical documentation and web portals, strips UI chrome and client-side tracking, and emits clean, semantic Markdown and tables optimized for LLM context windows.

## Token Reduction Metrics
- **Average Token Savings**: 85% – 95%
- **Sanitization**: Strips scripts, styles, SVGs, navbars, and footers while preserving code blocks and converting HTML tables to clean Markdown.

## Machine Feeds
- [`v1/index.json`](public/v1/index.json) (Catalog & reduction stats)
- [`llms.txt`](public/llms.txt) (Token-efficient LLM digest)
- `distilled.parquet` (Columnar database snapshot)

## Architecture
- **Parser**: BeautifulSoup4 semantic DOM extractor
- **Database**: DuckDB + Parquet
- **Ledger**: Append-only Git-committed JSONL in `/data/history`
- **Delivery**: GitHub Pages (Fastly CDN)
