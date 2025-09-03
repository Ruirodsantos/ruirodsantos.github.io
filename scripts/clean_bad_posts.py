import os
import re

POSTS_DIR = "_posts"
PAYWALL_PHRASE = "ONLY AVAILABLE IN PAID PLANS"
TITLE_BLACKLIST = re.compile(
    r"(broadcasts?|fixtures?|schedule|tv\s+guide|premier league|bundesliga|rangers|celtic|espn|disney\+|kickoff|"
    r"line\s?up|derbies|round\s?\d+|vs\.)",
    re.IGNORECASE
)

def is_bad(content):
    if not content or len(content.strip()) < 140:
        return True
    if PAYWALL_PHRASE.lower() in content.lower():
        return True
    first_line = content.splitlines()[0] if content else ""
    if TITLE_BLACKLIST.search(first_line):
        return True
    return False

def main():
    if not os.path.isdir(POSTS_DIR):
        print("Nothing to clean.")
        return
    removed = 0
    for name in os.listdir(POSTS_DIR):
        if not name.endswith(".md"):
            continue
        path = os.path.join(POSTS_DIR, name)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if is_bad(text):
            os.remove(path)
            removed += 1
            print(f"🗑️ Removed: {name}")
    print(f"Cleaned. Removed {removed} bad file(s).")

if __name__ == "__main__":
    main()
