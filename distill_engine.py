import os
import re
import json
import hashlib
import duckdb
import requests
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone

DB_FILE = "data/dom_distill.db"
HISTORY_DIR = "data/history"
EXPORT_DIR = "public"
API_DIR = os.path.join(EXPORT_DIR, "v1")
DOCS_DIR = os.path.join(API_DIR, "distilled")

# High-frequency developer targets routinely scraped by autonomous bots
TARGET_PAGES = {
    "python_release_notes": "https://docs.python.org/3/whatsnew/3.13.html",
    "github_status": "https://www.githubstatus.com/",
    "fastapi_features": "https://fastapi.tiangolo.com/features/",
    "docker_engine_release": "https://docs.docker.com/engine/release-notes/",
    "duckdb_news": "https://duckdb.org/news/"
}

STRIP_TAGS = [
    "script", "style", "noscript", "svg", "nav", "footer", 
    "header", "form", "iframe", "aside", "meta", "link"
]

def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def clean_html_to_markdown(raw_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(raw_html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled Resource"

    # Remove comments
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove chrome, scripts, trackers, navigation
    for tag_name in STRIP_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    # Identify primary article/content container
    main_content = (
        soup.find("main") or 
        soup.find("article") or 
        soup.find("div", {"role": "main"}) or 
        soup.find("div", class_=re.compile(r"content|documentation|body", re.I)) or 
        soup.body
    )

    if not main_content:
        return title, ""

    # Process tables into clean markdown tables
    for table in main_content.find_all("table"):
        md_table_rows = []
        rows = table.find_all("tr")
        for idx, tr in enumerate(rows):
            cells = [re.sub(r"\s+", " ", c.get_text()).strip() for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            md_table_rows.append("| " + " | ".join(cells) + " |")
            if idx == 0 and len(cells) > 0:
                md_table_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
        
        table_str = "\n" + "\n".join(md_table_rows) + "\n"
        table.replace_with(table_str)

    # Process code blocks
    for pre in main_content.find_all("pre"):
        code_text = pre.get_text()
        pre.replace_with(f"\n```\n{code_text.strip()}\n```\n")

    # Process headings
    for h_level in range(1, 7):
        for h in main_content.find_all(f"h{h_level}"):
            h_text = h.get_text().strip()
            h.replace_with(f"\n\n{'#' * h_level} {h_text}\n\n")

    # Process list items
    for li in main_content.find_all("li"):
        li_text = li.get_text().strip()
        li.replace_with(f"\n- {li_text}")

    # Process paragraphs
    for p in main_content.find_all("p"):
        p_text = re.sub(r"\s+", " ", p.get_text()).strip()
        p.replace_with(f"\n\n{p_text}\n\n")

    # Extract clean text and normalize multiple newlines
    distilled = main_content.get_text()
    distilled = re.sub(r"\n{3,}", "\n\n", distilled).strip()

    final_markdown = f"# {title}\n\n{distilled}"
    return title, final_markdown

def build_static_api(conn):
    os.makedirs(DOCS_DIR, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    cur = conn.execute("SELECT page_slug, title, source_url, raw_html_bytes, distilled_bytes, token_reduction_pct, last_updated_utc, distilled_markdown FROM distilled_pages")
    rows = cur.fetchall()

    catalog = []
    lines = [
        "# DOM Distill Wire",
        f"> Last Sync: {now_iso} UTC",
        "> Optimization: Raw HTML stripped of CSS, JS, tracking, and navigation (Avg 85-95% token savings).",
        "",
        "## Available Distilled Documents"
    ]

    for row in rows:
        slug, title, url, raw_sz, dist_sz, reduction, updated, md_content = row
        catalog.append({
            "slug": slug,
            "title": title,
            "source_url": url,
            "raw_bytes": raw_sz,
            "distilled_bytes": dist_sz,
            "token_reduction_pct": round(reduction, 2),
            "updated_utc": updated,
            "endpoint": f"v1/distilled/{slug}.md"
        })

        with open(os.path.join(DOCS_DIR, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(md_content)

        lines.append(f"- **{title}** (`{slug}`): {reduction:.1f}% reduction ({raw_sz // 1024} KB -> {dist_sz // 1024} KB) | `v1/distilled/{slug}.md`")

    with open(os.path.join(API_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(catalog)}, "documents": catalog}, f, indent=2)

    with open(os.path.join(EXPORT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    html = f"""<!DOCTYPE html><html><head><title>DOM Distill Wire</title></head>
    <body style='font-family:system-ui,sans-serif;max-width:850px;margin:2rem auto;line-height:1.6;padding:0 1rem;'>
    <h1>📰 DOM Distill Wire</h1>
    <p>Semantic reader-mode web extractor stripping raw DOM overhead for AI context windows.</p>
    <h3>Machine Feeds</h3>
    <ul>
      <li><a href='v1/index.json'>/v1/index.json</a> (Catalog &amp; Token Metrics)</li>
      <li><a href='llms.txt'>llms.txt</a> (Token-Efficient LLM Digest)</li>
      <li><a href='distilled.parquet'>distilled.parquet</a> (Columnar Parquet Snapshot)</li>
    </ul>
    <h3>Distilled Markdown Feeds</h3>
    <ul>
      {"".join([f"<li><a href='v1/distilled/{c['slug']}.md'>{c['title']}</a> ({c['token_reduction_pct']}% smaller)</li>" for c in catalog])}
    </ul>
    </body></html>"""
    with open(os.path.join(EXPORT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

def run():
    os.makedirs("data", exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = duckdb.connect(DB_FILE)
    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.execute(f.read())

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")

    month_dir = os.path.join(HISTORY_DIR, year_str, month_str)
    os.makedirs(month_dir, exist_ok=True)
    daily_history_file = os.path.join(month_dir, f"{date_str}.jsonl")

    conn.execute("BEGIN TRANSACTION")

    headers = {"User-Agent": "DOMDistillWire/1.0 (Machine-First Semantic Reader)"}

    for slug, url in TARGET_PAGES.items():
        try:
            r = requests.get(url, headers=headers, timeout=25)
            if r.status_code != 200:
                continue
            raw_html = r.text
        except Exception:
            continue

        raw_bytes = len(raw_html.encode("utf-8"))
        title, md_content = clean_html_to_markdown(raw_html)
        if not md_content:
            continue

        dist_bytes = len(md_content.encode("utf-8"))
        reduction_pct = ((raw_bytes - dist_bytes) / raw_bytes) * 100.0 if raw_bytes > 0 else 0.0
        content_hash = compute_hash(md_content)

        existing = conn.execute(f"SELECT content_hash FROM distilled_pages WHERE page_slug = '{slug}'").fetchone()

        escaped_title = title.replace("'", "''")
        escaped_md = md_content.replace("'", "''")

        if not existing:
            conn.execute(f"""
                INSERT INTO distilled_pages (
                    page_slug, source_url, title, raw_html_bytes, distilled_bytes,
                    token_reduction_pct, distilled_markdown, content_hash, last_updated_utc
                ) VALUES (
                    '{slug}', '{url}', '{escaped_title}', {raw_bytes}, {dist_bytes},
                    {reduction_pct}, '{escaped_md}', '{content_hash}', '{now_iso}'
                )
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, page_slug, reduction_pct, detail)
                VALUES ({commit_id}, '{now_iso}', 'INIT_DISTILL', '{slug}', {reduction_pct}, 'Initial semantic distillation')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "INIT_DISTILL",
                "page_slug": slug,
                "raw_bytes": raw_bytes,
                "distilled_bytes": dist_bytes,
                "reduction_pct": reduction_pct,
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

        elif existing[0] != content_hash:
            conn.execute(f"""
                UPDATE distilled_pages SET
                    title = '{escaped_title}',
                    raw_html_bytes = {raw_bytes},
                    distilled_bytes = {dist_bytes},
                    token_reduction_pct = {reduction_pct},
                    distilled_markdown = '{escaped_md}',
                    content_hash = '{content_hash}',
                    last_updated_utc = '{now_iso}'
                WHERE page_slug = '{slug}'
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, page_slug, reduction_pct, detail)
                VALUES ({commit_id}, '{now_iso}', 'CONTENT_DRIFT', '{slug}', {reduction_pct}, 'Web documentation content drift detected')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "CONTENT_DRIFT",
                "page_slug": slug,
                "raw_bytes": raw_bytes,
                "distilled_bytes": dist_bytes,
                "reduction_pct": reduction_pct,
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

    conn.execute("COMMIT")

    conn.execute(f"COPY (SELECT page_slug, source_url, title, raw_html_bytes, distilled_bytes, token_reduction_pct, content_hash, last_updated_utc FROM distilled_pages) TO '{EXPORT_DIR}/distilled.parquet' (FORMAT PARQUET)")
    build_static_api(conn)
    conn.close()

if __name__ == "__main__":
    run()
