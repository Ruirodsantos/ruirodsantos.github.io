import feedparser
from slugify import slugify
from datetime import datetime
import os

# Feed RSS de notícias de IA
RSS_FEED_URL = "https://www.investing.com/rss/news_285.rss"

# Pasta onde os posts são salvos
POSTS_DIR = "_posts"

# Cria a pasta se não existir
os.makedirs(POSTS_DIR, exist_ok=True)

# Faz parsing do feed
feed = feedparser.parse(RSS_FEED_URL)

# Quantidade de posts novos
MAX_POSTS = 5

for entry in feed.entries[:MAX_POSTS]:
    # Data atual no formato YYYY-MM-DD
    today_date = datetime.today().strftime('%Y-%m-%d')

    # Slug gerado a partir do título
    post_slug = slugify(entry.title)

    # Caminho do ficheiro .md
    file_path = os.path.join(POSTS_DIR, f"{today_date}-{post_slug}.md")

    # Se o ficheiro já existir, não cria outro
    if os.path.exists(file_path):
        continue

    # Escreve o ficheiro com front matter e conteúdo
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"""---
title: "{entry.title}"
date: {today_date}
---

{entry.summary}
""")
