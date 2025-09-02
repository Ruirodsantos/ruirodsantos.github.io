import os
import requests
from datetime import datetime
from slugify import slugify

# Diretório dos posts
POSTS_DIR = "_posts"

# Elimina todos os posts de 2025-06-13 em diante
def delete_old_posts():
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            date_str = filename.split("-")[0:3]
            date = "-".join(date_str)
            if date >= "2025-06-13":
                os.remove(os.path.join(POSTS_DIR, filename))
                print(f"❌ Apagado: {filename}")

# Gera conteúdo dividido em excerto + artigo completo
def fetch_post():
    res = requests.get("https://api.thenewsapi.com/v1/news/all?api_token=demo&language=en&limit=1&categories=tech")
    article = res.json()['data'][0]

    title = article['title']
    date = datetime.today().strftime('%Y-%m-%d')
    slug = slugify(title)
    url = article['url']
    description = article['description'] or "Read more at the source."

    # Texto extra
    full_text = f"""
Apple has once again stirred the tech world with the announcement of its M5 chip series.
Industry experts suggest the M5 Max may surpass even high-end desktop CPUs. 
The design remains faithful to the minimalism Apple is known for, but inside, it’s a beast.
Early benchmarks hint at massive GPU improvements, ideal for creatives and developers alike.

Read the full original source here: [{url}]({url})
"""
    return {
        "title": title,
        "slug": slug,
        "date": date,
        "excerpt": description,
        "full_text": full_text
    }

# Cria novo post com excerto e corpo
def create_post(post):
    filename = f"{post['date']}-{post['slug']}.md"
    path = os.path.join(POSTS_DIR, filename)

    with open(path, "w") as f:
        f.write(f"""---
layout: post
title: "{post['title']}"
date: {post['date']}
excerpt: >-
  {post['excerpt']}
---

{post['full_text']}
""")
    print(f"✅ Criado: {filename}")

if __name__ == "__main__":
    delete_old_posts()

    for _ in range(2):  # cria 2 posts
        post = fetch_post()
        create_post(post)

    print("\n🚀 Blog atualizado com novos conteúdos completos!")
