#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, sys, hashlib, json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import requests
from slugify import slugify


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


MAX_POSTS = 3
POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-blog-bot/3.0"


RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.feedburner.com/venturebeat/SZYF",
    "https://www.technologyreview.com/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
]


EDITORIAL_PROMPT = (
    "You write a blog called AI but make it useful. "
    "A friendly conversational blog for everyday curious people who want to understand AI without the hype. "
    "For each post you receive a news article title and summary. "
    "Write an original blog post that: "
    "1. Explains what this AI development actually is in plain simple English using 2-3 paragraphs. Use analogies. Avoid jargon. "
    "2. Answers So what? How could I make money or save money from this? with 2-3 concrete specific realistic ideas for regular people or small business owners. "
    "Tone: Like a smart friend explaining it over coffee. Warm, direct, no fluff. "
    "RULES: Never copy or closely paraphrase the original article. "
    "No hype words like revolutionary or groundbreaking. "
