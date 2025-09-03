import os
import re
import textwrap
from datetime import datetime, timedelta, timezone

import requests
from dateutil import parser as dateparser
from slugify import slugify

# === CONFIG ===
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # set in repo Secrets
MAX_POSTS = 5
POSTS_DIR = "_posts"

QUERY = "artificial intelligence OR AI OR machine learning OR generative ai OR llm"
LANG = "en"
CATEGORY = "technology"


def have_key():
    if not API_KEY:
        raise ValueError("❌ NEWS_API_KEY is not set (repository secret).")


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
    """
    Perform the API call and ALWAYS return (status_code, json_dict)
    If JSON parsing fails, return {} as the dict.
    """
    try:
        r = requests.get(API_URL, params=params, timeout=30)
        try:
            data = r.json()
        except Exception:
            data = {}
        return r.status_code, data
    except Exception as e:
        # network error
        return 0, {"status": "error", "results": str(e)}


def extract_items(data):
    """
    Return a list of article dicts if present, else [].
    Newsdata sometimes sends 'results' as list even with 422.
    """
    if not isinstance(data, dict):
        return []
    results = data.get("results")
    if isinstance(results, list):
        return results
    return []


def fetch_latest():
    """
    Progressive fallbacks. We now accept any HTTP status as long as we
    get a non-empty 'results' list of items that look like articles.
    """
    now = utcnow()
    since = now - timedelta(hours=24)

    date_from = since.strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")

    variants = [
        # 1) Most specific
        {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "category": CATEGORY,
            "from_date": date_from,
            "to_date": date_to,
            "page": 1,
        },
        # 2) No category
        {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "from_date": date_from,
            "to_date": date_to,
            "page": 1,
        },
        # 3) No dates
        {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "category": CATEGORY,
            "page": 1,
        },
        # 4) Minimal
        {
            "apikey": API_KEY,
            "q": "artificial intelligence OR AI",
            "language": LANG,
            "page": 1,
        },
    ]

    last_note = None
    for ix, params in enumerate(variants, start=1):
        code, data = _call(params)
        items = extract_items(data)
        if items:
            # Filter valid-looking articles
            valid = []
            seen = set()
            for a in items:
                title = (a.get("title") or "").strip()
                desc = (a.get("description") or "").strip()
                link = a.get("link")
                if not title or not desc or not link:
                    continue
                norm = re.sub(r"\s+", " ", title.lower())
                if norm in seen:
                    continue
                seen.add(norm)
                valid.append(a)

            # Sort by pub date desc
            def _ts(article):
                try:
                    return dateparser.parse(
                        article.get("pubDate") or article.get("pub_date") or ""
                    )
                except Exception:
                    return datetime(1970, 1, 1, tzinfo=timezone.utc)

            valid.sort(key=_ts, reverse=True)
            if valid:
                print(f"✅ Using variant {ix} (status {code}) with {len(valid)} items")
                return valid[:MAX_POSTS]
            else:
                last_note = f"Variant {ix} had results but none valid."
        else:
            last_note = (
                f"Variant {ix} returned status {code} with keys "
                f"{list(data.keys()) if isinstance(data, dict) else 'N/A'}"
            )

    print(f"⚠️ All query variants produced no usable items. Last note: {last_note}")
    return []


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
    have_key()
    items = fetch_latest()
    if not items:
        print("ℹ️ No posts created today (API returned no usable results).")
        # exit 0 so GitHub Actions doesn't fail the job
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
        print("ℹ️ Nothing written (all candidates filtered out).")


if __name__ == "__main__":
    main()
