name: Auto-Update AI Blog

on:
  schedule:
    - cron: '0 4 * * *'  # Runs daily at 08:00 Dubai time (UTC+4)
  workflow_dispatch:       # Allows manual trigger

jobs:
  update-blog:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Install Python dependencies
        run: pip install feedparser

      - name: Run AI news fetcher
        run: python fetch_ai_news.py

      - name: Commit and push changes
        run: |
          git config --global user.name 'Rui Blog Bot'
          git config --global user.email 'action@github.com'
          git add index.html
          git diff --cached --quiet || git commit -m "Auto-update: New AI news"
          git push
