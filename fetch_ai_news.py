import feedparser
from datetime import datetime

FEED_URLS = [
    "https://openai.com/blog/rss.xml",
    "https://deepmind.google/rss.xml",
    "https://www.anthropic.com/news/rss.xml"
]

MAX_POSTS = 10
fetched_posts = []

for url in FEED_URLS:
    feed = feedparser.parse(url)
    for entry in feed.entries:
        if len(fetched_posts) >= MAX_POSTS:
            break
        title = entry.title
        date = entry.published if 'published' in entry else datetime.now().strftime('%b %d, %Y')
        summary = entry.summary if 'summary' in entry else ''
        link = entry.link

        post_html = f"""
<article class="post">
  <h2>{title}</h2>
  <p class="date">🗓️ {date}</p>
  <p>{summary}</p>
  <a class="readmore" href="{link}" target="_blank">Read more</a>
</article>
""".strip()

        fetched_posts.append(post_html)

# Read and update index.html
if fetched_posts:
    with open("index.html", "r", encoding="utf-8") as file:
        html = file.read()

    start = html.find("<main>")
    end = html.find("</main>")

    if start != -1 and end != -1:
        new_html = html[:start + 6] + "\n\n" + "\n\n".join(fetched_posts) + "\n\n" + html[end:]
        with open("index.html", "w", encoding="utf-8") as file:
            file.write(new_html)
