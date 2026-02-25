"""
fetch_lj.py — скачивает публичные посты из ЖЖ через XML-RPC API.

Использование:
    python scripts/fetch_lj.py

Пароль вводится при запуске и нигде не сохраняется.
Скачивает только публичные посты (security=public).
Пагинация через beforeid — надёжный способ обойти весь журнал.
"""

import os
import re
import time
import hashlib
import getpass
import xmlrpc.client
from datetime import datetime

# --- настройки ---
LJ_USER = "knizhkin"
START_YEAR = 2004
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lj")
LJ_API = "https://www.livejournal.com/interface/xmlrpc"
BATCH_SIZE = 50   # максимум по API
DELAY = 1.0       # секунды между батчами


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def get_auth(username, password):
    """Challenge-response авторизация. Вызывать перед каждым запросом — challenge одноразовый."""
    proxy = xmlrpc.client.ServerProxy(LJ_API)
    ch = proxy.LJ.XMLRPC.getchallenge()["challenge"]
    return {
        "username": username,
        "auth_method": "challenge",
        "auth_challenge": ch,
        "auth_response": md5(ch + md5(password)),
        "ver": 1,
    }


def fetch_batch(proxy, username, password, before_id=None, attempt=0):
    """Получает батч постов. before_id — пагинация назад по времени."""
    params = get_auth(username, password)
    params.update({
        "selecttype": "lastn",
        "howmany": BATCH_SIZE,
        "noprops": 0,
        "lineendings": "unix",
    })
    if before_id is not None:
        params["beforeid"] = before_id

    try:
        result = proxy.LJ.XMLRPC.getevents(params)
        return result.get("events", [])
    except xmlrpc.client.Fault as e:
        if "rate" in e.faultString.lower():
            print("  [rate limit] жду 15 сек...")
            time.sleep(15)
            return fetch_batch(proxy, username, password, before_id, attempt)
        print(f"  [API ошибка {e.faultCode}]: {e.faultString[:120]}")
        return []
    except Exception as e:
        if attempt < 5:
            wait = 10 * (attempt + 1)
            print(f"  [сеть] {e} — retry {attempt+1}/5 через {wait} сек...")
            time.sleep(wait)
            return fetch_batch(proxy, username, password, before_id, attempt + 1)
        print(f"  [сеть] не удалось после 5 попыток: {e}")
        return []


def clean_markup(text):
    """Минимальная очистка ЖЖ-разметки."""
    if not text:
        return ""
    text = re.sub(r'<lj-cut[^>]*>', '\n[---]\n', text, flags=re.I)
    text = re.sub(r'</lj-cut>', '', text, flags=re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.I)
    text = re.sub(r'</p>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def decode(val):
    """Декодирует Binary или возвращает строку как есть."""
    if isinstance(val, xmlrpc.client.Binary):
        return val.data.decode("utf-8", errors="replace")
    return val or ""


def save_post(event, counters):
    """Сохраняет пост. counters — dict для подсчёта."""
    security = event.get("security", "public") or "public"
    # скачиваем все посты владельца (включая приватные и friends-only)
    # статус фиксируем в файле

    eventtime = event.get("eventtime", "")  # "YYYY-MM-DD HH:MM:SS"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", eventtime)
    if not m:
        counters["skipped_nodate"] += 1
        return

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))

    if year < START_YEAR:
        counters["skipped_old"] += 1
        return

    content = clean_markup(decode(event.get("event", "")))
    if not content:
        counters["skipped_empty"] += 1
        return

    subject = re.sub(r'<[^>]+>', '', decode(event.get("subject", ""))).strip()
    subject = subject or "(без заголовка)"

    props = event.get("props", {})
    taglist = decode(props.get("taglist", "") if isinstance(props, dict) else "")

    itemid = event.get("itemid", 0)
    url = f"https://{LJ_USER}.livejournal.com/{itemid}.html"
    security_label = {"public": "публичный", "friends": "для друзей", "private": "приватный"}.get(security, security)

    year_dir = os.path.join(OUTPUT_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)

    filename = f"{year}-{month:02d}-{day:02d}-{itemid}.md"
    path = os.path.join(year_dir, filename)

    if os.path.exists(path):
        counters["already_exists"] += 1
        return

    md_content = f"""# {subject}

**Дата:** {year}-{month:02d}-{day:02d}
**URL:** {url}
**Доступ:** {security_label}
**Теги:** {taglist}

---

{content}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_content)

    counters["saved"] += 1
    return filename


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"ЖЖ-архив: {LJ_USER}.livejournal.com (с {START_YEAR})")
    print("Пароль не сохраняется.")
    password = getpass.getpass(f"Пароль для {LJ_USER}: ")

    proxy = xmlrpc.client.ServerProxy(LJ_API)

    # проверка авторизации
    try:
        auth = get_auth(LJ_USER, password)
        info = proxy.LJ.XMLRPC.login(dict(auth))
        print(f"OK: {info.get('fullname', LJ_USER)}\n" + "-" * 50)
    except xmlrpc.client.Fault as e:
        print(f"Ошибка входа: {e.faultString}")
        return

    counters = {
        "saved": 0, "already_exists": 0,
        "skipped_empty": 0, "skipped_old": 0, "skipped_nodate": 0,
    }

    # resume: найти минимальный itemid среди уже сохранённых файлов
    before_id = None
    saved_ids = []
    for root, _, files in os.walk(OUTPUT_DIR):
        for f in files:
            m = re.search(r"-(\d+)\.md$", f)
            if m:
                saved_ids.append(int(m.group(1)))
    if saved_ids:
        before_id = min(saved_ids) - 1
        print(f"Продолжаю с before_id={before_id} (найдено {len(saved_ids)} файлов)")
    else:
        print("Начинаю с начала")

    batch_num = 0
    stop = False

    while not stop:
        batch = fetch_batch(proxy, LJ_USER, password, before_id)
        if not batch:
            break

        batch_num += 1
        min_id = None

        for event in batch:
            itemid = event.get("itemid", 0)
            if min_id is None or itemid < min_id:
                min_id = itemid

            # проверяем год — если все посты старше START_YEAR, стоп
            eventtime = event.get("eventtime", "")
            yr_m = re.match(r"(\d{4})", eventtime)
            if yr_m and int(yr_m.group(1)) < START_YEAR:
                stop = True

            fname = save_post(event, counters)
            if fname:
                print(f"  {fname}")

        saved_total = counters["saved"] + counters["already_exists"]
        print(f"[батч {batch_num}] +{counters['saved']} сохранено | всего: {saved_total} | min_id: {min_id}")

        if min_id is not None:
            before_id = min_id - 1  # строго меньше, иначе петля
        else:
            break

        if len(batch) < BATCH_SIZE:
            break  # последняя страница

        time.sleep(DELAY)

    print("\n" + "-" * 50)
    print(f"Сохранено новых: {counters['saved']}")
    print(f"Уже было: {counters['already_exists']}")
    print(f"Пропущено (пусто/до {START_YEAR}): "
          f"{counters['skipped_empty']+counters['skipped_old']}")
    print(f"Папка: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
