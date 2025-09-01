import os
import requests
from datetime import datetime
from slugify import slugify  # Add this for safe filenames

# === CONFIGURATION ===
NUM_POSTS = 10
POSTS_DIR = "_posts"
NEWS_API_URL = "https://newsapi.org/v2/everything"
NEWS_API_KEY = os.getenv("NEWS_API_KEY")  # use GitHub secret instead of hardcoding

PARAMS = {
    "q": "artificial intelligence",
    "language": "en",
    "sortBy": "publishedAt",
    "pageSize": NUM_POSTS,
    "apiKey": NEWS_API_KEY,
}

# === FETCH NEWS ===
response = requests.get(NEWS_API_URL, params=PARAMS)
articles = response.json().get("articles", [])

if not os.path.exists(POSTS_DIR):
    os.makedirs(POSTS_DIR)

# === CREATE POSTS ===
for article in articles:
    try:
        date = datetime.strptime(article["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
        slug = slugify(article["title"])[:50]
        filename = f"{date.strftime('%Y-%m-%d')}-{slug}.md"
        filepath = os.path.join(POSTS_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(f"layout: post\n")
            f.write(f"title: \"{article['title']}\"\n")
            f.write(f"date: {date.strftime('%Y-%m-%d')}\n")
            f.write("---\n\n")

            f.write(f"**{article['description'] or 'No description available.'}**\n\n")
            f.write(f"*Author:* {article.get('author', 'Unknown')}\n\n")
            f.write(f"*Source:* [{article['source']['name']}]({article['url']})\n\n")
            f.write("### Full Article\n\n")
            f.write(f"[Click here to read the full article]({article['url']})\n")

        print(f"✅ Saved: {filename}")

    except Exception as e:
        print(f"❌ Failed to save article: {e}")
