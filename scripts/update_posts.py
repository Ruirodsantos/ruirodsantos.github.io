import requests
import datetime
import os
from slugify import slugify

# Configura o endpoint da API
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY")

# Palavras-chave que queremos seguir
KEYWORDS = ["artificial intelligence", "machine learning", "AI", "AGI"]

# Garante que temos a pasta de posts
POSTS_FOLDER = "_posts"
os.makedirs(POSTS_FOLDER, exist_ok=True)

def fetch_post():
    query = " OR ".join(KEYWORDS)
    params = {
        "apikey": API_KEY,
        "q": query,
        "language": "en",
        "country": "us",
        "category": "technology"
    }
    res = requests.get(API_URL, params=params)
    data = res.json()

    if "results" not in data:
        raise ValueError("Resposta inválida da API: \n" + str(data))

    for article in data["results"]:
        if article.get("title") and article.get("description"):
            return article

    raise ValueError("Nenhum artigo válido encontrado")

def generate_post_content(article):
    date = datetime.datetime.utcnow().date()
    slug = slugify(article['title'])[:50]
    filename = f"{POSTS_FOLDER}/{date}-{slug}.md"

    content = f"""---
title: "{article['title']}"
date: {date}
excerpt: "{article['description']}"
categories: [ai, news]
---

Source: [{article['source_id']}]({article['link']})

{article.get('content') or article['description']}
"""
    return filename, content.strip()

def save_post(filename, content):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    try:
        article = fetch_post()
        filename, content = generate_post_content(article)
        save_post(filename, content)
        print(f"✅ Post criado: {filename}")
    except Exception as e:
        print(f"❌ Erro: {e}")
        exit(1)

if __name__ == "__main__":
    main()
