import feedparser
from datetime import datetime

# RSS feeds from AI leaders
FEED_URLS = [
    "https://openai.com/blog/rss.xml",
    "https://deepmind.google/rss.xml",
    "https://www.anthropic.com/news/rss.xml"
]

# Max total posts (initial bulk)
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
  <a class="readmore" href="{link}">Read more</a>
</article>
"""
        if post_html not in fetched_posts:
            fetched_posts.append(post_html)

if fetched_posts:
    with open("index.html", "r") as file:
        html = file.read()

    # Replace <main> content
    start = html.find("<main>")
    end = html.find("</main>")
    if start != -1 and end != -1:
        new_html = html[:start + 6] + "\n" + "\n".join(fetched_posts) + "\n</main>" + html[end + 7:]
        with open("index.html", "w") as file:
            file.write(new_html)
