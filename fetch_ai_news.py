import feedparser
from datetime import datetime
import os

FEED_URL = "https://feeds.feedburner.com/TechCrunch/artificial-intelligence"
NUM_INITIAL_POSTS = 10

HTML_TEMPLATE = """
<article class="post">
  <h2>{title}</h2>
  <p class="date">📅 {date}</p>
  <p>{summary}</p>
  <a class="readmore" href="{link}">Read more</a>
</article>
"""

def fetch_ai_posts(limit=10):
    feed = feedparser.parse(FEED_URL)
    posts_html = ""

    for entry in feed.entries[:limit]:
        title = entry.title
        summary = entry.summary.split(".")[0] + "."  # One sentence
        link = entry.link
        date = datetime(*entry.published_parsed[:6]).strftime("%B %d, %Y")
        posts_html += HTML_TEMPLATE.format(title=title, date=date, summary=summary, link=link)

    return posts_html

def update_index_html():
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    start = html.find('<main id="home">')
    end = html.find("</main>", start) + len("</main>")
    if start == -1 or end == -1:
        print("Couldn't find <main> section.")
        return

    new_main = f'<main id="home">\n{fetch_ai_posts(NUM_INITIAL_POSTS)}\n</main>'
    updated = html[:start] + new_main + html[end:]

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(updated)

    print("✅ 10 posts added to index.html")

if __name__ == "__main__":
    update_index_html()
