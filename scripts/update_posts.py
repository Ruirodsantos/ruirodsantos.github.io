import os
import re
import json
import requests
from datetime import datetime, timedelta
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")  # support either name
if not API_KEY:
    raise ValueError("API_KEY not found. Set NEWS_API_KEY or NEWSDATA_API_KEY in repo secrets/vars.")

POSTS_DIR = "_posts"
os.makedirs(POSTS_DIR, exist_ok=True)

# Keywords/themes we DO want
QUERY = "artificial intelligence OR AI OR generative ai OR llm OR openai OR anthropic OR google ai OR meta ai"

# Obvious non-AI/schedule/sports blacklists
TITLE_BLACKLIST = re.compile(
    r"(broadcasts?|fixtures?|schedule|tv\s+guide|premier league|bundesliga|rangers|celtic|espn|disney\+|kickoff|"
    r"line\s?up|derbies|round\s?\d+|vs\.)",
    re.IGNORECASE
)

# Phrase that indicates paywalled junk
PAYWALL_PHRASE = "ONLY AVAILABLE IN PAID PLANS"

MAX_PER_RUN = int(os.getenv("POSTS_PER_RUN", "5"))

def fetch_latest():
    params = {
        "apikey": API_KEY,
        "q": QUERY,
        "language": "en",
        "category": "technology",
        "page": 1,
    }
    r = requests.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])

def looks_bad(article):
    title = (article.get("title") or "").strip()
    desc = (article.get("description") or "").strip()
    content = (article.get("content") or "").strip()

    # obvious sports/schedule stuff
    if TITLE_BLACKLIST.search(title):
        return True

    # too short body
    body = content or desc
    if len(body) < 140:
        return True

    # paywalled marker
    if PAYWALL_PHRASE.lower() in body.lower():
        return True

    return False

def make_post(article):
    # date
    iso = article.get("pubDate") or ""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d %H:%M:%S")
    except Exception:
        d = datetime.utcnow()
    date_str = d.strftime("%Y-%m-%d")

    title = article["title"].strip()
    slug = slugify(title)[:60]
    filename = f"{date_str}-{slug}.md"
    path = os.path.join(POSTS_DIR, filename)

    source = article.get("source_id") or "source"
    link = article.get("link") or ""
    desc = (article.get("description") or "").strip()
    content = (article.get("content") or desc).strip()

    # front matter + content
    fm = [
        "---",
        f'title: "{title.replace(\'"\', "\\\"")}"',
        f"date: {date_str}",
        f"source: {source}",
        f"link: {link}",
        "layout: post",
        "---",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(fm))
        f.write(content if content else desc)
        f.write("\n")
    return path

def main():
    results = fetch_latest()
    created = 0
    for art in results:
        if not art.get("title"):
            continue
        if looks_bad(art):
            continue
        try:
            p = make_post(art)
            created += 1
            print(f"✅ Created: {p}")
        except Exception as e:
            print(f"❌ Skip due to error: {e}")
        if created >= MAX_PER_RUN:
            break

    print(f"Done. Created {created} post(s).")

if __name__ == "__main__":
    main()
