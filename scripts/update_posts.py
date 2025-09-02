# 📁 update_posts.py (atualizado)
import os
import requests
import json
from datetime import datetime
from slugify import slugify

API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsdata.io/api/1/news?apikey={}&q=artificial%20intelligence&language=en"
BLOG_PATH = "./posts"

os.makedirs(BLOG_PATH, exist_ok=True)

response = requests.get(BASE_URL.format(API_KEY))
data = response.json()

for article in data.get("results", []):
    title = article.get("title", "")
    date_str = article.get("pubDate", "")
    link = article.get("link", "")
    content = article.get("description", "") or article.get("content", "")
    image_url = article.get("image_url")
    source = article.get("source_id", "Unknown")

    # ⚠️ Filtro de conteúdo fraco
    if not title or not content or "ONLY AVAILABLE IN PAID PLANS" in content.upper():
        continue

    slug = slugify(title)
    date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()

    # 📄 Gerar ficheiro do post
    post_path = os.path.join(BLOG_PATH, f"{slug}.md")
    with open(post_path, "w") as f:
        f.write(f"---\n")
        f.write(f"title: {title}\n")
        f.write(f"date: {date}\n")
        f.write(f"link: {link}\n")
        f.write(f"source: {source}\n")
        if image_url:
            f.write(f"image: {image_url}\n")
        f.write(f"---\n\n")
        f.write(content.strip())
