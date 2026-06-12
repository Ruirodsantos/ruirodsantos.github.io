#!/usr/bin/env python3
"""AI Pulse Hub - Article Generator v2
Uses Claude API with web_search to find AND write 750-900 word articles.
No dependency on NewsAPI or RSS feeds (which were silently failing)."""

import os, re, json, time, hashlib
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess
    subprocess.run(["pip","install","requests","--break-system-packages","-q"])
    import requests

POSTS_DIR = "_posts"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY","")
API_URL = "https://api.anthropic.com/v1/messages"
HEADERS = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}

IMAGES = [
    "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/1181671/pexels-photo-1181671.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/2599244/pexels-photo-2599244.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/373543/pexels-photo-373543.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/1148820/pexels-photo-1148820.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/3184418/pexels-photo-3184418.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/7567486/pexels-photo-7567486.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/5926382/pexels-photo-5926382.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
]

def get_category(text):
    t = text.lower()
    if any(w in t for w in ["invest","revenue","profit","ipo","valuation","billion","acquisition","merger","fundrais","raised","funding round","deal"]):
        return "business"
    if any(w in t for w in ["earn","income","salary","job","freelance","passive","side hustle","wage","money","monetiz","career"]):
        return "money"
    if any(w in t for w in ["regulation","law","policy","government","congress","senate","ban","rule","legislation","antitrust","court","legal"]):
        return "policy"
    if any(w in t for w in ["startup","founder","venture","seed","series a","series b","pitch","incubat"]):
        return "startups"
    if any(w in t for w in ["research","paper","study","benchmark","dataset","training","architecture","university","lab","arxiv","published"]):
        return "research"
    if any(w in t for w in ["google","microsoft","meta","amazon","apple","nvidia","openai","anthropic","chip","hardware","bigtech"]):
        return "bigtech"
    if any(w in t for w in ["tool","plugin","api","agent","assistant","feature","launch","release","update","product","app","platform","software"]):
        return "tools"
    return "ai"

def get_image(title):
    idx = int(hashlib.md5(title.encode()).hexdigest(),16) % len(IMAGES)
    return IMAGES[idx]

def slugify(title):
    s = title.lower()
    s = re.sub(r'[^\w\s-]','',s)
    s = re.sub(r'[-\s]+','-',s).strip('-')
    return s[:60]

def post_exists(title):
    slug = slugify(title)
    for f in Path(POSTS_DIR).glob("*.md"):
        if slug[:30] in f.name:
            return True
    return False

def call_claude(payload, timeout=120):
    r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=timeout)
    if r.status_code != 200:
        print(f"  API ERROR {r.status_code}: {r.text[:300]}")
        return None
    return r.json()

def extract_text(data):
    """Extract and concatenate all text blocks from a Claude response."""
    if not data:
        return ""
    blocks = data.get("content", [])
    return "\n".join(b.get("text","") for b in blocks if b.get("type") == "text")

def fetch_news_via_claude():
    """Use Claude + web_search to find today's top AI news stories."""
    prompt = """Search the web for 8 significant, distinct AI / artificial intelligence news stories published in the last 24-48 hours.

Cover a MIX of these areas: AI tool/product launches, major AI company news (OpenAI, Anthropic, Google, Microsoft, Meta, NVIDIA, xAI etc.), AI startup funding or acquisitions, AI research breakthroughs, AI policy/regulation, and practical ways people can use AI to work or make money.

After researching, respond with ONLY a JSON array (no markdown fences, no commentary) in this exact format:
[{"title": "...", "url": "...", "source": "...", "summary": "2-3 sentence summary of what happened and why it's notable"}]

The "url" must be a real, working URL to the original source article you found."""

    data = call_claude({
        "model": "claude-opus-4-5",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}]
    }, timeout=150)

    text = extract_text(data)
    if not text:
        print("  No text returned from news search call")
        return []

    text = text.strip()
    text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        print(f"  Could not find JSON array in response. First 300 chars: {text[:300]}")
        return []
    try:
        items = json.loads(match.group(0))
        return [it for it in items if it.get("title") and len(it.get("title",""))>15]
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}. First 300 chars: {text[:300]}")
        return []

def generate_article(title, summary, source_url, source_name):
    """Generate a 750-900 word original article with analysis."""
    prompt = f"""You are a senior technology journalist for The AI Pulse Hub, a daily AI news publication.

Write a comprehensive, original 750-900 word article about this story. Add real analysis and insight readers cannot get just from the headline.

TITLE: {title}
SUMMARY: {summary}
SOURCE: {source_name} ({source_url})

Write with these sections, in plain paragraphs (NO markdown headers, NO hashtags, NO bullet symbols):

Opening (70-90 words): A compelling hook, analogy, or surprising angle. Do NOT start with the company name.

What happened (100-130 words): Clear, jargon-free explanation. What, who, when.

Why this matters (160-200 words): Deep analysis. Who is affected and how? Historical context, comparisons to similar past events.

The bigger picture (150-180 words): How this fits the wider AI industry narrative. What trends does it reinforce or disrupt?

What this means for you (120-150 words): Practical implications for developers, business owners, and everyday people. Be specific.

What to watch next (80-100 words): Three concrete, forward-looking things to monitor.

Closing sentence: One punchy, memorable final line.

RULES:
- Short paragraphs (2-4 sentences)
- Conversational but authoritative tone
- Include specific names, companies, numbers where possible
- Original analysis, not just a summary
- Never write "this article" or "in this piece"
- No em-dashes
- Output ONLY the article body text, nothing else"""

    data = call_claude({
        "model": "claude-opus-4-5",
        "max_tokens": 1400,
        "messages": [{"role": "user", "content": prompt}]
    }, timeout=90)

    text = extract_text(data)
    if text:
        return text.strip()
    return f"{summary}\n\nThis story represents a significant development in the AI landscape. Stay tuned to The AI Pulse Hub for continued coverage."

def make_excerpt(content):
    clean = re.sub(r'<[^>]+>','',content)
    clean = ' '.join(clean.split())
    s = clean[:155]
    return (s.rsplit(' ',1)[0]+'...') if len(clean)>155 else clean

def build_post(article):
    title = article["title"].strip().replace('"',"'")
    if post_exists(title):
        print(f"  Skip (exists): {title[:50]}")
        return False

    print(f"  Generating article...")
    content = generate_article(title, article.get("summary",""), article.get("url",""), article.get("source",""))
    excerpt = make_excerpt(content)
    cat = get_category(title+" "+article.get("summary",""))
    image = get_image(title)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(title)
    fname = f"{date_str}-{slug}.md"
    words = len(content.split())
    read_time = max(3, round(words/200))
    safe_excerpt = excerpt.replace('"',"'")
    source_url = article.get('url','')
    source_name = article.get('source','Source')

    post = f"""---
layout: post
title: "{title}"
date: {date_str}
categories: [{cat}]
excerpt: "{safe_excerpt}"
image: {image}
reading_time: {read_time}
source_url: "{source_url}"
author: "The AI Pulse Hub Editorial Team"
---

{content}

---
*Originally reported by [{source_name}]({source_url}). The AI Pulse Hub provides independent analysis and commentary.*
"""
    Path(POSTS_DIR).mkdir(exist_ok=True)
    with open(f"{POSTS_DIR}/{fname}","w",encoding="utf-8") as f:
        f.write(post)
    print(f"  Created: {fname} ({read_time} min, {words} words, cat:{cat})")
    return True

def main():
    print("=== AI Pulse Hub Article Generator v2 ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    if not ANTHROPIC_KEY:
        print("FATAL: ANTHROPIC_API_KEY not set. Exiting.")
        return
    print("Searching for today's AI news via Claude web search...")
    articles = fetch_news_via_claude()
    print(f"Found {len(articles)} candidate stories")

    seen, unique = set(), []
    for a in articles:
        k = slugify(a["title"])
        if k not in seen:
            seen.add(k)
            unique.append(a)

    created = 0
    for a in unique[:8]:
        print(f"\nProcessing: {a['title'][:70]}")
        try:
            if build_post(a):
                created += 1
            time.sleep(1)
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nDone. Created {created} posts.")

if __name__ == "__main__":
    main()
