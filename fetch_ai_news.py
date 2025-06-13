import feedparser
from datetime import datetime
import os

FEED_URL = "https://feeds.feedburner.com/TechCrunch/artificial-intelligence"

NUM_POSTS_NOW = 10  # Show these now
POSTS_PER_DAY = 1   # From tomorrow

HTML_TEMPLATE = """
<article class="post">
  <h2>{title}</h2>
  <p class="date">📅 {date}</p>
  <p>{summary}</p>
  <a class="readmore" href="{link}">Read more</a>
</article>
"""

def fetch_ai_posts():
    feed = feedparser.parse(FEED_URL)
    today = datetime.now().strftime("%Y-%m-%d")

    html_output = ""

    for i, entry in enumerate(feed.entries[:NUM_POSTS_NOW]):
        date = datetime(*entry.published_parsed[:6]).strftime("%B %d, %Y")
        title = entry.title
        summary = entry.summary.split(".")[0] + "."  # 1-sentence summary
        link = entry.link

        html_output += HTML_TEMPLATE.format(title=title, date=date, summary=summary, link=link)

    return html_output

def update_index_html():
    path = "index.html"

    if not os.path.exists(path):
        print("index.html not found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find("<main id=\"home\">")
    end = content.find("</main>") + len("</main>")

    if start == -1 or end == -1:
        print("Main content section not found.")
        return

    new_main = f"<main id=\"home\">\n{fetch_ai_posts()}\n</main>"
    new_content = content[:start] + new_main + content[end:]

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("index.html updated successfully.")

if __name__ == "__main__":
    update_index_html()
