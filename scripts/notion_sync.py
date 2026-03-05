#!/usr/bin/env python3
"""
notion_sync.py — синхронизация корпуса текстов из Git в Notion.

Маппинг директорий → Notion:
  texts/01-subjectivity/     → «1. О субъектности человека и AI»
  texts/04-self-observation/ → «1. О субъектности человека и AI»
  texts/02-law/              → «2. Право в эпоху AI»
  texts/03-cultural-patterns/ → «3. Культурно-исторические паттерны»

Требует:
  ~/.config/clody_spark/notion.json: {"token": "secret_..."}

Использование:
  python scripts/notion_sync.py              # добавить новые страницы
  python scripts/notion_sync.py --dry-run    # показать что будет сделано
  python scripts/notion_sync.py --force      # перезаписать существующие
  python scripts/notion_sync.py --file texts/01-subjectivity/foo.md

Настройка Notion интеграции:
  1. https://www.notion.so/my-integrations → создать интеграцию
  2. Скопировать токен (secret_...) в ~/.config/clody_spark/notion.json
  3. На странице «Тексты» в Notion: ••• → Connections → добавить интеграцию
"""

import json
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# ── Конфигурация ──────────────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".config/clody_spark/notion.json"
REPO_ROOT   = Path(__file__).parent.parent
TEXTS_DIR   = REPO_ROOT / "texts"

NOTION_API     = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Маппинг директорий корпуса → Notion page_id
SECTION_MAP = {
    "01-subjectivity":     "301a67037d6e81aaa43ada46d2ede3e8",
    "04-self-observation": "301a67037d6e81aaa43ada46d2ede3e8",
    "02-law":              "301a67037d6e81a7a8c6c768ef8bacac",
    "03-cultural-patterns": "301a67037d6e812a80f0f3249347639f",
}

RATE_DELAY  = 0.35   # ~3 запроса/сек — лимит Notion API
MAX_CONTENT = 1990   # символов в одном rich_text объекте

# ── HTTP ───────────────────────────────────────────────────────────────────────

def notion_req(method, endpoint, token, data=None):
    url  = f"{NOTION_API}/{endpoint}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    req  = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization":   f"Bearer {token}",
            "Notion-Version":  NOTION_VERSION,
            "Content-Type":    "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Notion {method} {endpoint}: {e.code} {e.read().decode()}")


def get_children(token, page_id):
    out, cursor = [], None
    while True:
        qs = f"page_size=100{'&start_cursor=' + cursor if cursor else ''}"
        r  = notion_req("GET", f"blocks/{page_id}/children?{qs}", token)
        out.extend(r.get("results", []))
        if not r.get("has_more"):
            break
        cursor = r["next_cursor"]
    return out


def create_page(token, parent_id, title, blocks):
    return notion_req("POST", "pages", token, {
        "parent":     {"page_id": parent_id},
        "properties": {"title": {"title": [_text(title)]}},
        "children":   blocks[:100],
    })


def append_blocks(token, page_id, blocks):
    for i in range(0, len(blocks), 100):
        notion_req("PATCH", f"blocks/{page_id}/children", token,
                   {"children": blocks[i:i+100]})
        time.sleep(RATE_DELAY)


def delete_all_children(token, page_id):
    for block in get_children(token, page_id):
        notion_req("DELETE", f"blocks/{block['id']}", token)
        time.sleep(RATE_DELAY)


# ── Rich text ──────────────────────────────────────────────────────────────────

def _text(content, bold=False, italic=False, code=False, url=None):
    obj = {"type": "text", "text": {"content": content[:MAX_CONTENT]}}
    if url:
        obj["text"]["link"] = {"url": url}
    ann = {}
    if bold:   ann["bold"]   = True
    if italic: ann["italic"] = True
    if code:   ann["code"]   = True
    if ann:    obj["annotations"] = ann
    return obj


def rich_text(raw):
    """Парсить inline-форматирование (**bold**, *italic*, `code`, [text](url))."""
    parts = []
    i = 0
    while i < len(raw):
        # Bold **text**
        if raw[i:i+2] == "**":
            end = raw.find("**", i + 2)
            if end != -1:
                parts.append(_text(raw[i+2:end], bold=True))
                i = end + 2
                continue
        # Italic *text* (не **)
        if raw[i] == "*" and raw[i:i+2] != "**":
            end = raw.find("*", i + 1)
            if end != -1:
                parts.append(_text(raw[i+1:end], italic=True))
                i = end + 1
                continue
        # Code `text`
        if raw[i] == "`":
            end = raw.find("`", i + 1)
            if end != -1:
                parts.append(_text(raw[i+1:end], code=True))
                i = end + 1
                continue
        # Link [text](url)
        if raw[i] == "[":
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", raw[i:])
            if m:
                parts.append(_text(m.group(1), url=m.group(2)))
                i += len(m.group(0))
                continue
        # Plain text — до следующего спецсимвола
        j = i + 1
        while j < len(raw) and raw[j] not in ("*", "`", "["):
            j += 1
        chunk = raw[i:j]
        if chunk:
            # Разбить длинный кусок по MAX_CONTENT
            while chunk:
                parts.append(_text(chunk[:MAX_CONTENT]))
                chunk = chunk[MAX_CONTENT:]
        i = j

    return parts or [_text(raw or "")]


def _block(btype, key, rich):
    return {btype: {key: rich_text(rich)}} | {"type": btype}


def para_block(text):
    return {"type": "paragraph", "paragraph": {"rich_text": rich_text(text)}}


# ── Markdown → Notion blocks ───────────────────────────────────────────────────

_SPECIAL = re.compile(r"^(#{1,6} |---$|> |[-*] |\d+\. )")

def md_to_blocks(md):
    """Конвертировать Markdown в список Notion blocks (h1 пропускается — это title)."""
    lines  = md.split("\n")
    blocks = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # h1 — title страницы, пропускаем
        if re.match(r"^# [^#]", line):
            i += 1
            continue

        # h2
        if line.startswith("## "):
            blocks.append({"type": "heading_2",
                           "heading_2": {"rich_text": rich_text(line[3:].strip())}})
            i += 1; continue

        # h3
        if line.startswith("### "):
            blocks.append({"type": "heading_3",
                           "heading_3": {"rich_text": rich_text(line[4:].strip())}})
            i += 1; continue

        # Divider
        if line.strip() == "---":
            blocks.append({"type": "divider", "divider": {}})
            i += 1; continue

        # Blockquote
        if line.startswith("> "):
            blocks.append({"type": "quote",
                           "quote": {"rich_text": rich_text(line[2:].strip())}})
            i += 1; continue

        # Bullet list
        if re.match(r"^[-*] ", line):
            blocks.append({"type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": rich_text(line[2:].strip())}})
            i += 1; continue

        # Numbered list
        m = re.match(r"^\d+\. (.+)", line)
        if m:
            blocks.append({"type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": rich_text(m.group(1))}})
            i += 1; continue

        # Пустая строка
        if not line.strip():
            i += 1; continue

        # Абзац — собираем подряд идущие строки до пустой или спецмаркера
        para = []
        while i < len(lines) and lines[i].strip() and not _SPECIAL.match(lines[i]):
            para.append(lines[i])
            i += 1
        if para:
            blocks.append(para_block("\n".join(para)))

    return blocks


# ── Основная логика ────────────────────────────────────────────────────────────

def extract_title(md):
    for line in md.split("\n"):
        if re.match(r"^# [^#]", line):
            return line[2:].strip()
    return None


def load_section_pages(token, section_id):
    """Вернуть {title_lower: page_id} для дочерних страниц секции."""
    pages = {}
    for block in get_children(token, section_id):
        if block.get("type") == "child_page":
            t = block["child_page"]["title"]
            pages[t.lower()] = block["id"]
    return pages


def sync_file(token, md_path, parent_id, existing, dry_run, force):
    md    = md_path.read_text(encoding="utf-8")
    title = extract_title(md)
    if not title:
        print(f"  SKIP {md_path.name} — нет заголовка")
        return

    exists = title.lower() in existing

    if exists and not force:
        print(f"  EXISTS  {title}")
        return

    blocks = md_to_blocks(md)
    action = "UPDATE" if exists else "CREATE"

    if dry_run:
        print(f"  [{action}] {title}  ({len(blocks)} блоков)")
        return

    print(f"  {action}  {title}...", end="", flush=True)
    try:
        if exists:
            page_id = existing[title.lower()]
            delete_all_children(token, page_id)
            if blocks:
                append_blocks(token, page_id, blocks)
        else:
            result  = create_page(token, parent_id, title, blocks)
            page_id = result["id"]
            if len(blocks) > 100:
                append_blocks(token, page_id, blocks[100:])
            time.sleep(RATE_DELAY)
        print(" ✓")
    except RuntimeError as e:
        print(f" ОШИБКА: {e}")


def main():
    ap = argparse.ArgumentParser(description="Синхронизация корпуса в Notion")
    ap.add_argument("--dry-run", action="store_true", help="Только показать, без изменений")
    ap.add_argument("--force",   action="store_true", help="Перезаписать существующие страницы")
    ap.add_argument("--file",    metavar="PATH",       help="Синхронизировать один файл")
    args = ap.parse_args()

    if not CONFIG_FILE.exists():
        print(f"Ошибка: {CONFIG_FILE} не найден.")
        print('Создайте файл: {"token": "secret_..."}')
        print("Подробнее: https://www.notion.so/my-integrations")
        sys.exit(1)

    with open(CONFIG_FILE, encoding="utf-8") as f:
        token = json.load(f)["token"]

    if args.file:
        md_path = Path(args.file).resolve()
        section = md_path.parent.name
        parent_id = SECTION_MAP.get(section)
        if not parent_id:
            print(f"Ошибка: секция «{section}» не в маппинге.")
            sys.exit(1)
        existing = load_section_pages(token, parent_id)
        sync_file(token, md_path, parent_id, existing, args.dry_run, args.force)
        return

    # Синхронизировать весь корпус
    # Один запрос load_section_pages на уникальный parent_id
    seen_parents = {}
    for section_dir, parent_id in SECTION_MAP.items():
        section_path = TEXTS_DIR / section_dir
        if not section_path.exists():
            continue
        md_files = sorted(section_path.glob("*.md"))
        if not md_files:
            continue

        print(f"\n{section_dir}/ ({len(md_files)} файлов)")
        if parent_id not in seen_parents:
            seen_parents[parent_id] = load_section_pages(token, parent_id)
            time.sleep(RATE_DELAY)
        existing = seen_parents[parent_id]

        for md_path in md_files:
            sync_file(token, md_path, parent_id, existing, args.dry_run, args.force)
            time.sleep(RATE_DELAY)

    print("\nГотово.")


if __name__ == "__main__":
    main()
