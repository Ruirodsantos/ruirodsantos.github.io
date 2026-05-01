#!/usr/bin/env python3
"""Re-categorize all existing posts based on title + excerpt keywords."""
import os, re

POSTS_DIR = "_posts"

def get_category(text):
    t = text.lower()
    if any(w in t for w in ["invest","stock","market","fund","revenue","profit","ipo","valuation","billion","acquisition","deal","merger","fundrais","raised","worth","price"]):
        return "business"
    if any(w in t for w in ["earn","income","salary","job","freelance","passive","side hustle","pay","wage","money","monetiz"]):
        return "money"
    if any(w in t for w in ["regulation","law","policy","government","congress","senate","ban","rule","legislation","antitrust","court","legal","compli"]):
        return "policy"
    if any(w in t for w in ["startup","founder","venture","seed","series a","series b","raise","funding","pitch","incubat"]):
        return "startups"
    if any(w in t for w in ["research","paper","study","benchmark","dataset","training","architecture","university","lab","scientist","arxiv","published"]):
        return "research"
    if any(w in t for w in ["robot","hardware","chip","gpu","nvidia","device","phone","autonomous","vehicle","sensor","quantum","processor"]):
        return "bigtech"
    if any(w in t for w in ["tool","plugin","api","agent","assistant","feature","launch","release","update","product","app","platform","software","version"]):
        return "tools"
    return "ai"

def recat_post(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Extract title and excerpt for categorization
    title = re.search(r'title:\s*"?([^"\n]+)"?', content)
    excerpt = re.search(r'excerpt:\s*"?([^"\n]+)"?', content)
    text = (title.group(1) if title else "") + " " + (excerpt.group(1) if excerpt else "")
    
    cat = get_category(text)
    
    # Replace or add categories line
    if re.search(r'^categories:', content, re.MULTILINE):
        new_content = re.sub(r'^categories:.*$', f'categories: [{cat}]', content, flags=re.MULTILINE)
    else:
        # Add after 'date:' line
        new_content = re.sub(r'(^date:.*$)', r'\1\ncategories: [' + cat + ']', content, flags=re.MULTILINE, count=1)
    
    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {os.path.basename(filepath)}: {cat}")
    else:
        print(f"No change {os.path.basename(filepath)}")

if __name__ == "__main__":
    for fname in sorted(os.listdir(POSTS_DIR)):
        if fname.endswith(".md"):
            recat_post(os.path.join(POSTS_DIR, fname))
    print("Done!")
