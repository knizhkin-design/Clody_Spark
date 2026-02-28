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

# source: "ilibrary" (default) или "stihi-rus"
POETS = {
    "mandelstam": {"name": "Мандельштам", "full": "Осип Мандельштам",     "slug": "mandelstam",  "source": "ilibrary"},
    "tsvetaeva":  {"name": "Цветаева",    "full": "Марина Цветаева",      "slug": "tsvetaeva",   "source": "ilibrary"},
    "tarkovsky":  {"name": "Тарковский",  "full": "Арсений Тарковский",   "slug": "Tarkovsky",   "source": "stihi-rus"},
    "solovyov":   {"name": "Соловьёв",    "full": "Владимир Соловьёв",    "slug": "Solovev",     "source": "stihi-rus"},
    "blok":       {"name": "Блок",        "full": "Александр Блок",       "slug": "blok",        "source": "ilibrary"},
    "akhmatova":  {"name": "Ахматова",    "full": "Анна Ахматова",        "slug": "Ahmatova",    "source": "stihi-rus"},
    "annensky":   {"name": "Анненский",   "full": "Иннокентий Анненский", "slug": "Annenskiy",   "source": "stihi-rus"},
    "pasternak":  {"name": "Пастернак",   "full": "Борис Пастернак",      "slug": "Pasternak",   "source": "stihi-rus"},
    "tyutchev":   {"name": "Тютчев",      "full": "Фёдор Тютчев",         "slug": "tyutchev",    "source": "ilibrary"},
}

STIHI_RUS_BASE = "https://stihi-rus.ru"


# ── HTTP ───────────────────────────────────────────────────────────────────────

def fetch(url: str, encoding: str = "windows-1251") -> str:
    """Скачивает страницу, возвращает текст."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return raw.decode(encoding, errors="replace")


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


# ── stihi-rus.ru ─────────────────────────────────────────────────────────────

def get_stihi_rus_poems(slug: str, full_name: str) -> list[dict]:
    """
    Скачивает стихотворения с stihi-rus.ru.
    Структура: /1/{Slug}/N.htm, текст в <font size="5" face="Arial">.
    """
    base = f"{STIHI_RUS_BASE}/1/{slug}/"
    try:
        index = fetch(base)
    except Exception as e:
        return []

    # Числовые ссылки — это страницы стихотворений
    nums = re.findall(r'href="(\d+\.htm)"', index)
    nums = list(dict.fromkeys(nums))  # дедупликация с сохранением порядка

    poems = []
    for num in nums:
        url = base + num
        time.sleep(DELAY)
        try:
            page = fetch(url)
        except Exception:
            continue

        # Заголовок из <title>
        m = re.search(r"<title>([^<]+)</title>", page)
        raw_title = html.unescape(m.group(1)).strip() if m else ""
        # Убираем суффикс " - Автор, стихи"
        title = re.sub(r"\s*-\s*[А-ЯЁа-яёA-Za-z\s]+,?\s*стихи.*$", "", raw_title).strip()
        if not title:
            title = "* * *"

        # Текст в <font size="5" face="Arial">
        m = re.search(
            r'<font size="5" face="Arial">(.*?)</font>',
            page, re.DOTALL | re.IGNORECASE
        )
        if not m:
            continue
        raw_text = m.group(1)

        # Убираем заголовок <b>...</b> в начале (это номер или название)
        raw_text = re.sub(r"^<b>[^<]*</b>\s*<br>", "", raw_text.strip(), flags=re.DOTALL)
        # <br> → перенос строки
        raw_text = re.sub(r"<br\s*/?>", "\n", raw_text, flags=re.IGNORECASE)
        # убираем остатки тегов
        raw_text = re.sub(r"<[^>]+>", "", raw_text)
        raw_text = html.unescape(raw_text).strip()

        # Убираем сноски после стихотворения (начинаются с "* " в отдельной строке)
        raw_text = re.sub(r"\n\*[^\n]+$", "", raw_text, flags=re.MULTILINE).strip()

        if not raw_text or len(raw_text) > MAX_CHARS:
            continue

        poems.append({
            "id":    num.replace(".htm", ""),
            "title": title,
            "year":  "",
            "text":  raw_text,
        })

    return poems


# ── Файловая система ──────────────────────────────────────────────────────────

def slugify(title: str) -> str:
    """Безопасное имя файла (кириллица разрешена, спецсимволы — нет)."""
    s = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:80] or "poem"


# ── Основная логика ───────────────────────────────────────────────────────────

def scrape_author(key: str, poet: dict, dry_run: bool = False) -> dict:
    print(f"\n── {poet['full']} ({poet.get('source', 'ilibrary')}) ──")
    source = poet.get("source", "ilibrary")

    if source == "stihi-rus":
        poems_data = get_stihi_rus_poems(poet["slug"], poet["full"])
        if not poems_data:
            print("  [!] Не найдено на stihi-rus.ru")
            return {"saved": 0, "long": 0, "skip": 0, "error": 1}
        print(f"  Найдено стихотворений: {len(poems_data)}")
        out_dir = POETRY_DIR / key
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
        saved = already = 0
        for poem in poems_data:
            base_slug = slugify(poem["title"])
            is_untitled = not base_slug or base_slug.strip("_") == "" or base_slug == "poem"
            if is_untitled:
                base_slug = f"untitled_{poem['id']}"
            filename = base_slug + ".md"
            if not dry_run:
                out_path = out_dir / filename
                if out_path.exists():
                    already += 1
                    continue
            if dry_run:
                print(f"  [OK   {len(poem['text']):4d}] {poem['title']}")
                continue
            content = f"# {poem['title']}\n\nАвтор: {poet['full']}\n\n{poem['text']}\n"
            out_path.write_text(content, encoding="utf-8")
            saved += 1
        print(f"  Сохранено: {saved}  |  уже было: {already}")
        return {"saved": saved}

    # ilibrary.ru
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

        # Уникальное имя файла:
        # — для безымянных (***) используем ID с самого начала
        # — для именованных: если файл уже есть — пропускаем (already)
        base_slug = slugify(poem["title"])
        # slugify("* * *") → "poem" (все спецсимволы + пробелы → _)
        # считаем безымянным если только подчёркивания или "poem"
        is_untitled = not base_slug or base_slug.strip("_") == "" or base_slug == "poem"
        if is_untitled:
            base_slug = f"untitled_{poem_id}"
        filename = base_slug + ".md"
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
