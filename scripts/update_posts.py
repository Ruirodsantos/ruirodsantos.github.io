# Script para atualizar os posts do blog Jekyll
import os
import datetime

# Caminho para a pasta _posts
POSTS_DIR = "_posts"

# Lista de arquivos a manter manualmente (posts antigos até 2025-06-13)
KEEP_DATES = [
    "2025-06-04",
    "2025-06-05",
    "2025-06-06",
    "2025-06-07",
    "2025-06-08",
    "2025-06-09",
    "2025-06-10",
    "2025-06-11",
    "2025-06-12",
    "2025-06-13",
]

# Apaga os posts do dia 2025-08-31
for filename in os.listdir(POSTS_DIR):
    if filename.startswith("2025-08-31"):
        os.remove(os.path.join(POSTS_DIR, filename))

# Posts que vamos adicionar:
posts = [
    {
        "date": "2025-08-31",
        "title": "Meta vs Google: Will Meta Catch Search Supremacy?",
        "body": "Meta Platforms could overtake Google in digital ad revenue by 2026, according to Bernstein analysts. With rapid advancements in AI and a more engaged user base on platforms like Instagram and Threads, Meta is gaining ground fast."
    },
    {
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "title": "September 1st AI Highlights: OpenAI's New Agent is Coming",
        "body": "OpenAI is rumored to be releasing a new agent model this September. While details are scarce, insiders suggest the agent could combine planning, tool use, and real-time task execution with GPT-5 level reasoning."
    }
]

# Função para criar o conteúdo em Markdown
def create_post(post):
    filename = f"{post['date']}-{post['title'].lower().replace(' ', '-').replace(':', '').replace('?', '').replace("'", '').replace(',', '').replace('.', '')}.md"
    filepath = os.path.join(POSTS_DIR, filename)

    with open(filepath, "w") as f:
        f.write("""---
layout: post
title: \"{title}\"
date: {date}
---

{body}
""".format(title=post['title'], date=post['date'], body=post['body']))

# Criação dos novos posts
for post in posts:
    create_post(post)

print("✔️ Posts atualizados com sucesso.")
