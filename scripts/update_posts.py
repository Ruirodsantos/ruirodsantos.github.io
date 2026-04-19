#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, sys, hashlib, json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify




NEWS_API_URL = "https://newsdata.io/api/1/news"
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"




LANG = "en"
MAX_POSTS = 3
POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/v2/1.0"
IMG_EXT_OK = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}




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
    "Keep total length between 350-500 words. "
