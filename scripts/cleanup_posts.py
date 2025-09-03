import os
import re
from pathlib import Path

POSTS_DIR = Path("_posts")

# padrões de datas a remover: 2025-06-04 .. 2025-06-13
DATE_PATTERNS = [
    r"2025-06-0[4-9]-",   # 04..09
    r"2025-06-1[0-3]-",   # 10..13
]

def should_delete(filename: str) -> bool:
    return any(re.match(pat, filename) for pat in DATE_PATTERNS)

def main():
    if not POSTS_DIR.exists():
        print("⚠️ _posts/ não existe.")
        return

    to_delete = []
    for f in POSTS_DIR.iterdir():
        if f.is_file() and should_delete(f.name):
            to_delete.append(f)

    if not to_delete:
        print("ℹ️ Nada para apagar (0 ficheiros).")
        return

    print(f"🧹 A apagar {len(to_delete)} ficheiro(s):")
    for f in to_delete:
        print(" -", f)
        f.unlink()

    print("✅ Limpeza concluída.")

if __name__ == "__main__":
    main()
