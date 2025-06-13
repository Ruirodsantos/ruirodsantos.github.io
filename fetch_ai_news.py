import feedparser
from datetime import datetime

FEED_URLS = [
    "https://openai.com/blog/rss.xml",
    "https://deepmind.google/rss.xml",
    "https://www.anthropic.com/news/rss.xml"
]

posts = []
for url in FEED_URLS:
    feed = feedparser.parse(url)
    for entry in feed.entries[:1]:
        title = entry.title
        date = entry.published if 'published' in entry else datetime.now().strftime('%b %d, %Y')
        summary = entry.summary if 'summary' in entry else ''
        link = entry.link
        posts.append(f"""
<article class="post">
  <h2>{title}</h2>
  <p class="date">🗓️ {date}</p>
  <p>{summary}</p>
  <a class="readmore" href="{link}">Read more</a>
</article>
""")

if posts:
    with open("index.html", "r") as file:
        html = file.read()

    main_start = html.find("<main>")
    main_end = html.find("</main>")
    old = html[main_start + 6:main_end].strip()
    new_html = html[:main_start + 6] + "\n" + "\n".join(posts) + "\n</main>" + html[main_end + 7:]

    with open("index.html", "w") as file:
        file.write(new_html)
