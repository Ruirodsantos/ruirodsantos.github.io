import os
import re
import requests
from datetime import datetime

# === CONFIGURATION ===
NUM_POSTS = 10
POSTS_DIR = "_posts"
NEWS_API_URL = "https://newsapi.org/v2/everything"
NEWS_API_KEY = "e5b2c5ce20e84308b3897c872cb830d1"  # Your real API key

PARAMS = {
    "q": "artificial intelligence",
    "language": "en",
    "sortBy": "publishedAt",
    "pageSize": NUM_POSTS,
    "apiKey": NEWS_API_KEY,
}

# === FETCH NEWS ===
response = requests.get(NEWS_API_URL, params=PARAMS)

if response.status_code != 200:
    print(f"❌ Failed to fetch articles. Status code: {response.status_code}")
    print(response.text)
    exit(1)

data = response.json()
print("🔍 Full API response:")
print(data)

articles = data.get("articles", [])
print(f"📰 Total articles fetched: {len(articles)}")

if not os.path.exists(POSTS_DIR):
    os.makedirs(POSTS_DIR)

# === CREATE POSTS ===
for article in articles:
    date = datetime.strptime(article["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
    clean_title = re.sub(r'[^\w\- ]', '', article['title'])[:50].strip().replace(' ', '-').lower()
    filename = f"{date.strftime('%Y-%m-%d')}-{clean_title}.md"
    filepath = os.path.join(POSTS_DIR, filename)

    if os.path.exists(filepath):
        print(f"⚠️ Skipping existing file: {filename}")
        continue

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"layout: post\n")
        f.write(f"title: \"{article['title']}\"\n")
        f.write(f"date: {date.strftime('%Y-%m-%d')}\n")
        f.write("---\n\n")
        f.write(f"{article['description'] or 'No description available.'}\n\n")
        f.write(f"Read more at: [{article['source']['name']}]({article['url']})\n")

    print(f"✅ Created: {filename}")

print(f"🎉 {len(articles)} posts processed.")
