#!/usr/bin/env python3
"""
Скачивает стихотворения с ilibrary.ru.

Структура сайта:
  /author/{slug}/l.all/index.html  — полный список стихотворений автора
  /text/{id}/p.1/index.html        — страница стихотворения

HTML стихотворения (Windows-1251):
  <div class="author">Имя Автора</div>
  <div class="title"><h1>Название</h1></div>
  <div id="pmt1">
    <z>  ← строфа
      <v><m></m>строка</v>
    </z>
    <cr>1913</cr>   ← год
  </div>

Использование:
    python scripts/poetry_scraper.py                      # все авторы
    python scripts/poetry_scraper.py --author mandelstam  # один автор
    python scripts/poetry_scraper.py --dry-run            # список без скачивания
    python scripts/poetry_scraper.py --stats              # что уже скачано
"""

import re
import time
import html
import argparse
from pathlib import Path
import urllib.request
import urllib.parse

REPO_ROOT  = Path(__file__).parent.parent
POETRY_DIR = REPO_ROOT / "poetry"
BASE_URL   = "https://ilibrary.ru"

MAX_CHARS = 2500   # длиннее → вероятно поэма, пропускаем
DELAY     = 0.8    # пауза между запросами

# ── Авторы ────────────────────────────────────────────────────────────────────

POETS = {
    "mandelstam": {"name": "Мандельштам", "full": "Осип Мандельштам",    "slug": "mandelstam"},
    "tsvetaeva":  {"name": "Цветаева",    "full": "Марина Цветаева",     "slug": "tsvetaeva"},
    "tarkovsky":  {"name": "Тарковский",  "full": "Арсений Тарковский",  "slug": "tarkovsky"},
    "solovyov":   {"name": "Соловьёв",    "full": "Владимир Соловьёв",   "slug": "solovyev"},
    "blok":       {"name": "Блок",        "full": "Александр Блок",      "slug": "blok"},
    "akhmatova":  {"name": "Ахматова",    "full": "Анна Ахматова",       "slug": "akhmatova"},
    "annensky":   {"name": "Анненский",   "full": "Иннокентий Анненский","slug": "annensky"},
    "pasternak":  {"name": "Пастернак",   "full": "Борис Пастернак",     "slug": "pasternak"},
    "tyutchev":   {"name": "Тютчев",      "full": "Фёдор Тютчев",        "slug": "tyutchev"},
}


# ── HTTP ───────────────────────────────────────────────────────────────────────

def fetch(url: str) -> str:
    """Скачивает страницу, возвращает текст в UTF-8."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    # ilibrary.ru использует windows-1251
    return raw.decode("windows-1251", errors="replace")


# ── Парсинг списка стихотворений ──────────────────────────────────────────────

def get_poem_ids(slug: str) -> list[str]:
    """
    Возвращает список ID стихотворений со страницы всех произведений автора.
    ID — числовая часть из /text/{id}/
    """
    url  = f"{BASE_URL}/author/{slug}/l.all/index.html"
    page = fetch(url)
    ids  = re.findall(r'/text/(\d+)/', page)
    # Дедупликация с сохранением порядка
    seen = set()
    result = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


# ── Парсинг страницы стихотворения ───────────────────────────────────────────

def parse_poem_page(page: str) -> dict | None:
    """
    Извлекает из HTML страницы:
      title, author, year, text
    Возвращает None если не удалось распарсить.
    """
    # Заголовок
    m = re.search(r'<div class="title"[^>]*>.*?<h1>(.*?)</h1>', page, re.DOTALL)
    title = html.unescape(m.group(1)).strip() if m else ""
    title = re.sub(r"<[^>]+>", "", title).strip()

    # Год
    m = re.search(r"<cr>(.*?)</cr>", page, re.DOTALL)
    year = html.unescape(m.group(1)).strip() if m else ""
    year = re.sub(r"<[^>]+>", "", year).strip()

    # Текст: берём содержимое div#pmt1
    m = re.search(r'<div id="pmt1">(.*?)</div\s*>', page, re.DOTALL)
    if not m:
        return None
    raw = m.group(1)

    # Строфы: <z>...</z>
    stanzas = re.findall(r"<z>(.*?)</z>", raw, re.DOTALL)
    if not stanzas:
        return None

    lines_by_stanza = []
    for stanza in stanzas:
        # Строки: <v>...</v>
        verses = re.findall(r"<v>(.*?)</v>", stanza, re.DOTALL)
        clean = []
        for v in verses:
            # Убираем теги <m>, <c>, <o> и прочие
            v = re.sub(r"<[^>]+>", "", v)
            v = html.unescape(v).strip()
            if v:
                clean.append(v)
        if clean:
            lines_by_stanza.append(clean)

    if not lines_by_stanza:
        return None

    text = "\n\n".join("\n".join(lines) for lines in lines_by_stanza)

    return {
        "title": title or "* * *",
        "year":  year,
        "text":  text,
    }


# ── Файловая система ──────────────────────────────────────────────────────────

def slugify(title: str) -> str:
    """Безопасное имя файла (кириллица разрешена, спецсимволы — нет)."""
    s = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:80] or "poem"


# ── Основная логика ───────────────────────────────────────────────────────────

def scrape_author(key: str, poet: dict, dry_run: bool = False) -> dict:
    print(f"\n── {poet['full']} ──")

    try:
        ids = get_poem_ids(poet["slug"])
    except Exception as e:
        print(f"  [!] Не удалось получить список: {e}")
        return {"saved": 0, "long": 0, "skip": 0, "error": 1}

    print(f"  Найдено ID: {len(ids)}")

    out_dir = POETRY_DIR / key
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    saved = long = skip = already = errors = 0

    for poem_id in ids:
        url = f"{BASE_URL}/text/{poem_id}/p.1/index.html"

        time.sleep(DELAY)
        try:
            page = fetch(url)
        except Exception as e:
            errors += 1
            if dry_run:
                print(f"  [ERR] {poem_id}: {e}")
            continue

        poem = parse_poem_page(page)
        if not poem:
            skip += 1
            continue

        text_len = len(poem["text"])

        if text_len > MAX_CHARS:
            long += 1
            if dry_run:
                print(f"  [LONG {text_len:5d}] {poem['title']}")
            continue

        filename = slugify(poem["title"]) + ".md"
        if not dry_run:
            out_path = out_dir / filename
            if out_path.exists():
                already += 1
                continue

        if dry_run:
            print(f"  [OK   {text_len:4d}] {poem['title']} ({poem['year']})")
            continue

        year_line = f"\nГод: {poem['year']}" if poem["year"] else ""
        content = (
            f"# {poem['title']}\n\n"
            f"Автор: {poet['full']}{year_line}\n\n"
            f"{poem['text']}\n"
        )
        out_path.write_text(content, encoding="utf-8")
        saved += 1

    print(
        f"  Сохранено: {saved}  |  уже было: {already}  |  "
        f"поэмы: {long}  |  пропущено: {skip}  |  ошибок: {errors}"
    )
    return {"saved": saved, "long": long, "skip": skip, "errors": errors}


def show_stats():
    if not POETRY_DIR.exists():
        print("Директория poetry/ ещё не создана.")
        return
    total = 0
    for author_dir in sorted(POETRY_DIR.iterdir()):
        if author_dir.is_dir():
            count = len(list(author_dir.glob("*.md")))
            total += count
            print(f"  {author_dir.name:15s} {count:4d} стихотворений")
    print(f"  {'ИТОГО':15s} {total:4d}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--author",  choices=list(POETS), help="Один автор")
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать список без скачивания")
    parser.add_argument("--stats",   action="store_true",
                        help="Показать что уже скачано")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    targets = {args.author: POETS[args.author]} if args.author else POETS

    for key, poet in targets.items():
        scrape_author(key, poet, dry_run=args.dry_run)

    print("\nГотово.")


if __name__ == "__main__":
    main()
