CREATE SEQUENCE IF NOT EXISTS seq_commit_id START 1;

CREATE TABLE IF NOT EXISTS distilled_pages (
    page_slug VARCHAR PRIMARY KEY,
    source_url VARCHAR,
    title VARCHAR,
    raw_html_bytes BIGINT,
    distilled_bytes BIGINT,
    token_reduction_pct DOUBLE,
    distilled_markdown VARCHAR,
    content_hash VARCHAR,
    last_updated_utc VARCHAR
);

CREATE TABLE IF NOT EXISTS ledger (
    commit_id BIGINT PRIMARY KEY,
    timestamp_utc VARCHAR,
    operation VARCHAR,
    page_slug VARCHAR,
    reduction_pct DOUBLE,
    detail VARCHAR
);
