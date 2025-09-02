import requests
import os
from datetime import datetime
from slugify import slugify

POSTS_DIR = "_posts"

def fetch_post():
    url = "https://huggingface.co/api/spaces/yuntian-deng/ChatGPT"
    res = requests.get(url)

    try:
        data = res.json()
    except Exception as e:
        raise ValueError(f"Erro ao interpretar JSON: {e}\nResposta: {res.text}")

    if 'data' not in data or not data['data']:
        raise KeyError(f"Nenhum conteúdo encontrado na resposta da API:\n{data}")

    article = data['data'][0]
    return article

def get_existing_dates():
    dates = []
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            try:
                date_str = filename.split("-")[0:3]
                date_str = "-".join(date_str)
                dates.append(date_str)
            except Exception:
                continue
    return sorted(set(dates))

def save_post(article, date):
    title = article["title"]
    content = article["content"]

    filename = f"{date}-{slugify(title)}.md"
    filepath = os.path.join(POSTS_DIR, filename)

    if os.path.exists(filepath):
        print(f"Post já existe: {filepath}")
        return

    with open(filepath, "w") as f:
        f.write(f"---\nlayout: post\ntitle: \"{title}\"\n---\n\n")
        f.write(content)

    print(f"Post guardado: {filepath}")

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    existing_dates = get_existing_dates()

    if today in existing_dates:
        print(f"Já existe post para hoje ({today}) — nada feito.")
        return

    try:
        article = fetch_post()
        save_post(article, today)
    except Exception as e:
        print(f"Erro ao gerar o post: {e}")
        exit(1)

if __name__ == "__main__":
    main()
