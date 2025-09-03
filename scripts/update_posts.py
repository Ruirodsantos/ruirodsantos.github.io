import os
import re
import textwrap
from datetime import datetime, timedelta, timezone

import requests
from dateutil import parser as dateparser
from slugify import slugify

# === CONFIG ===
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # repo secret
MAX_POSTS = 5
POSTS_DIR = "_posts"

QUERY = "artificial intelligence OR AI OR machine learning OR generative ai OR llm"
LANG = "en"
CATEGORY = "technology"


def require_api_key():
    if not API_KEY:
        raise ValueError("❌ NEWS_API_KEY is not set (repo secret).")


def utcnow():
    return datetime.now(timezone.utc)


def sanitize_title(title: str) -> str:
    return title.strip().replace('"', '\\"')


def best_date(article: dict) -> datetime.date:
    for key in ("pubDate", "pub_date", "date", "published_at"):
        val = article.get(key)
        if val:
            try:
                d = dateparser.parse(val)
                if not d.tzinfo:
                    d = d.replace(tzinfo=timezone.utc)
                return d.date()
            except Exception:
                pass
    return utcnow().date()


def short_excerpt(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return (text[: limit - 1] + "…") if len(text) > limit else text


def _call(params):
    r = requests.get(API_URL, params=params, timeout=30)
    # return both status + json to let caller decide
    try:
        data = r.json()
    except Exception:
        data = {}
    return r.status_code, data


def fetch_latest():
    """
    Progressive fallback to avoid 422:
      1) q + language + category + from/to
      2) q + language + from/to
      3) q + language + category
      4) q + language
    """
    now = utcnow()
    since = now - timedelta(hours=24)

    variants = [
        # Most specific
        {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "category": CATEGORY,
            "from_date": since.strftime("%Y-%m-%d"),
            "to_date": now.strftime("%Y-%m-%d"),
            "page": 1,
        },
        # No category
        {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "from_date": since.strftime("%Y-%m-%d"),
            "to_date": now.strftime("%Y-%m-%d"),
            "page": 1,
        },
        # No dates
        {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "category": CATEGORY,
            "page": 1,
        },
        # Minimal
        {
            "apikey": API_KEY,
            "q": "artificial intelligence OR AI",
            "language": LANG,
            "page": 1,
        },
    ]

    chosen_results = None
    last_err = None

    for ix, params in enumerate(variants, start=1):
        code, data = _call(params)
        if code == 200 and isinstance(data, dict) and data.get("results"):
            chosen_results = data["results"]
            break
        else:
            last_err = f"Variant {ix} -> status {code}, data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"

    if chosen_results is None:
        raise RuntimeError(f"All query variants failed. Last error: {last_err}")

    # Clean & dedupe
    cleaned = []
    seen = set()
    for a in chosen_results:
        title = (a.get("title") or "").strip()
        desc = (a.get("description") or "").strip()
        link = a.get("link")
        if not title or not desc or not link:
            continue
        norm = re.sub(r"\s+", " ", title.lower())
        if norm in seen:
            continue
        seen.add(norm)
        cleaned.append(a)

    # Sort desc by pub date
    def _ts(article):
        try:
            return dateparser.parse(article.get("pubDate") or article.get("pub_date") or "")
        except Exception:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    cleaned.sort(key=_ts, reverse=True)
    return cleaned[:MAX_POSTS]


def build_markdown(article: dict) -> str:
    title = sanitize_title(article["title"])
    date = best_date(article)
    link = article.get("link")
    src_name = article.get("source_id") or "Source"
    image = article.get("image_url") or ""
    excerpt = short_excerpt(article.get("content") or article.get("description") or "")

    fm = [
        "---",
        "layout: post",
        f'title: "{title}"',
        f"date: {date}",
    ]
    if image:
        fm.append(f'image: "{image}"')
    fm.append("categories: [ai, news]")
    fm.append("---")

    body = textwrap.dedent(
        f"""
        {excerpt}

        Read more at: [{src_name}]({link})
        """
    ).strip()

    return "\n".join(fm) + "\n\n" + body + "\n"


def write_post(article: dict) -> str:
    date = best_date(article)
    slug = slugify(article["title"])[:60]
    name = f"{date}-{slug}.md"
    path = os.path.join(POSTS_DIR, name)
    os.makedirs(POSTS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(article))
    return path


def main():
    require_api_key()
    items = fetch_latest()
    if not items:
        print("⚠️ No fresh items.")
        return
    written = []
    for art in items:
        try:
            written.append(write_post(art))
        except Exception as e:
            print("❌ Skipped one:", e)
    if written:
        print("✅ Created posts:")
        for p in written:
            print(" -", p)
    else:
        print("⚠️ Nothing written.")


if __name__ == "__main__":
    main()
