#!/usr/bin/env python3
"""AI Pulse Hub - Article Generator. Generates 700-900 word original articles."""

import os, re, json, time, random, hashlib
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
NEWS_API_KEY = os.environ.get("NEWS_API_KEY","")

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

def fetch_news():
    articles = []
    if NEWS_API_KEY:
        queries = ["artificial intelligence","AI startup funding","machine learning breakthrough","OpenAI Anthropic Google AI","AI regulation policy"]
        for q in queries:
            try:
                r = requests.get("https://newsapi.org/v2/everything",params={"q":q,"language":"en","sortBy":"publishedAt","pageSize":4,"apiKey":NEWS_API_KEY},timeout=10)
                if r.status_code == 200:
                    for a in r.json().get("articles",[]):
                        if a.get("title") and "[Removed]" not in a.get("title","") and len(a.get("title","")) > 20:
                            articles.append({"title":a["title"],"url":a.get("url",""),"description":a.get("description","") or a.get("content",""),"source":a.get("source",{}).get("name","")})
                time.sleep(0.3)
            except Exception as e:
                print(f"NewsAPI error: {e}")
    if len(articles) < 5:
        feeds = ["https://techcrunch.com/category/artificial-intelligence/feed/","https://venturebeat.com/category/ai/feed/","https://www.technologyreview.com/topic/artificial-intelligence/feed/"]
        for feed in feeds:
            try:
                r = requests.get(feed,timeout=10,headers={"User-Agent":"Mozilla/5.0"})
                titles = re.findall(r'<title><![CDATA[(.*?)]]></title>',r.text)
                links = re.findall(r'<link>(https?://[^<]+)</link>',r.text)
                descs = re.findall(r'<description><![CDATA[(.*?)]]></description>',r.text,re.DOTALL)
                src = re.search(r'https?://([^/]+)',feed)
                src_name = src.group(1).replace("www.","") if src else "source"
                for i,title in enumerate(titles[1:6]):
                    desc = re.sub(r'<[^>]+>','',descs[i] if i < len(descs) else "")[:400]
                    articles.append({"title":title.strip(),"url":links[i+1] if i+1 < len(links) else "","description":desc,"source":src_name})
            except Exception as e:
                print(f"Feed error: {e}")
    return articles

def generate_article(title, description, source_url, source_name):
    if not ANTHROPIC_KEY:
        return generate_fallback(title, description)
    prompt = f"""You are a senior technology journalist for The AI Pulse Hub, a daily AI news publication.

Write a comprehensive, original 750-900 word article about this story. Add real analysis and insight that readers cannot get just from reading the headline.

TITLE: {title}
SUMMARY: {description}
SOURCE: {source_name}

Write with these exact sections (plain text, NO markdown headers, NO hashtags):

Opening (70-90 words): Start with a compelling hook, analogy, or surprising fact. Do NOT start with the company name. Make the reader want to keep reading.

What happened (100-130 words): Clear, jargon-free explanation of the news. What, who, when.

Why this matters (160-200 words): Deep analysis. Who is affected and how? What does this change? Give historical context and compare to similar past events.

The bigger picture (150-180 words): How this fits into the wider AI industry narrative. What trends does it reinforce or disrupt? What would industry insiders say about this?

What this means for you (120-150 words): Practical implications. Tailor to three types of readers: developers, business owners, and everyday people. Be specific.

What to watch next (80-100 words): Three specific forward-looking things to monitor. Concrete, actionable.

Closing sentence (1 sentence): End with a punchy, memorable line that gives a final perspective.

RULES:
- Short paragraphs (2-4 sentences max)
- Conversational but authoritative tone
- Include specific names, companies, and numbers where possible
- Original analysis, not just a summary
- Never write "this article" or "in this piece"
- No em-dashes
- Output ONLY the article text, nothing else"""

    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-opus-4-5","max_tokens":1300,"messages":[{"role":"user","content":prompt}]},
            timeout=90)
        if r.status_code == 200:
            content = r.json()["content"][0]["text"]
            print(f"  Generated {len(content.split())} words via Claude API")
            return content
        else:
            print(f"  API error: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"  API exception: {e}")
    return generate_fallback(title, description)

def generate_fallback(title, description):
    desc = description or ""
    return f"{desc}\n\nThis story represents a significant development in the AI landscape. As artificial intelligence continues to reshape industries and daily life, stories like this one highlight both the opportunities and challenges that come with rapid technological change.\n\nStay tuned to The AI Pulse Hub for continued coverage and analysis as this story develops."

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

def make_excerpt(content):
    clean = re.sub(r'<[^>]+>','',content)
    clean = ' '.join(clean.split())
    s = clean[:155]
    return (s.rsplit(' ',1)[0]+'...') if len(clean)>155 else clean

def build_post(article):
    title = article["title"].strip().replace('"',"'")
    if post_exists(title):
        print(f"  Skip: {title[:50]}")
        return False
    content = generate_article(title, article.get("description",""), article.get("url",""), article.get("source",""))
    excerpt = make_excerpt(content)
    cat = get_category(title+" "+article.get("description",""))
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
    print(f"=== AI Pulse Hub Article Generator ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"API: {'Claude API active' if ANTHROPIC_KEY else 'Fallback mode (no API key)'}")
    articles = fetch_news()
    print(f"Fetched {len(articles)} raw articles")
    seen,unique = set(),[]
    for a in articles:
        k = slugify(a["title"])
        if k not in seen and len(a["title"])>20:
            seen.add(k)
            unique.append(a)
    print(f"Unique: {len(unique)}")
    created = 0
    for a in unique[:8]:
        print(f"\nProcessing: {a['title'][:60]}...")
        try:
            if build_post(a):
                created += 1
            time.sleep(2)
        except Exception as e:
            print(f"  Error: {e}")
    print(f"\nDone. Created {created} posts.")

if __name__ == "__main__":
    main()
