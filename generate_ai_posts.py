import os
import requests
from datetime import datetime
from slugify import slugify  # Make sure python-slugify is installed

# === CONFIGURATION ===
NUM_POSTS = 10
POSTS_DIR = "_posts"
NEWS_API_URL = "https://newsapi.org/v2/everything"
NEWS_API_KEY = "e5b2c5ce20e84308b3897c872cb830d1"  # Your actual NewsAPI key

PARAMS = {
    "q": "\"artificial intelligence\" OR \"AI technology\" OR \"machine learning\"",
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
    # Filter irrelevant content
    keywords = ["ai", "artificial intelligence", "machine learning", "neural", "deep learning"]
    content = (article["title"] + " " + (article["description"] or "")).lower()
    if not any(word in content for word in keywords):
        continue  # Skip if not relevant

    # Generate filename
    date = datetime.strptime(article["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
    safe_title = slugify(article['title'][:60])
    filename = f"{date.strftime('%Y-%m-%d')}-{safe_title}.md"
    filepath = os.path.join(POSTS_DIR, filename)

    # Write post
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"layout: post\n")
        f.write(f"title: \"{article['title']}\"\n")
        f.write(f"date: {date.strftime('%Y-%m-%d')}\n")
        f.write("---\n\n")
        f.write(f"{article['description'] or 'No description available.'}\n\n")
        f.write(f"Read more at: [{article['source']['name']}]({article['url']})\n")

print(f"✅ {len(articles)} filtered and relevant posts created in '{POSTS_DIR}' folder.")
