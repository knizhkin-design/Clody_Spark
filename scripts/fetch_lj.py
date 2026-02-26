"""
fetch_lj.py — скачивает все посты из ЖЖ через XML-RPC API.

Алгоритм:
  1. syncitems — получаем список всех ID записей журнала
  2. Для каждого ID — getevents(selecttype=one) — скачиваем пост

Использование:
    python scripts/fetch_lj.py

Пароль читается из ~/.config/clody_spark/lj.json.
Если файл не найден или пароль пуст — запрашивается вводом.
"""

import os
import re
import time
import json
import hashlib
import getpass
import xmlrpc.client
from datetime import datetime

# --- настройки ---
LJ_USER = "knizhkin"
START_YEAR = 2004
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lj")
LJ_API = "https://www.livejournal.com/interface/xmlrpc"
DELAY = 0.5  # секунды между запросами
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "clody_spark", "lj.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class BrowserTransport(xmlrpc.client.SafeTransport):
    """XML-RPC транспорт с браузерным User-Agent."""
    def send_user_agent(self, connection):
        connection.putheader("User-Agent", USER_AGENT)


def make_proxy():
    return xmlrpc.client.ServerProxy(LJ_API, transport=BrowserTransport())


def load_credentials():
    """Читает логин/пароль из конфига. Fallback на getpass."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        username = cfg.get("username") or LJ_USER
        password = cfg.get("password") or ""
        if password:
            return username, password
    return LJ_USER, getpass.getpass(f"Пароль для {LJ_USER}: ")


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def get_auth(username, password):
    proxy = make_proxy()
    ch = proxy.LJ.XMLRPC.getchallenge()["challenge"]
    return {
        "username": username,
        "auth_method": "challenge",
        "auth_challenge": ch,
        "auth_response": md5(ch + md5(password)),
        "ver": 1,
    }


def api_call(proxy, method, params, password, attempt=0):
    """Вызов API с retry на сетевые ошибки."""
    try:
        return getattr(proxy.LJ.XMLRPC, method)(params)
    except xmlrpc.client.Fault as e:
        if "rate" in e.faultString.lower() or "limit" in e.faultString.lower() or e.faultCode == 404:
            wait = 65
            print(f"  [лимит] жду {wait} сек...")
            time.sleep(wait)
            params.update(get_auth(params["username"], password))
            return api_call(proxy, method, params, password, attempt)
        raise
    except Exception as e:
        if attempt < 5:
            wait = 10 * (attempt + 1)
            print(f"  [сеть] retry {attempt+1}/5 через {wait} сек: {e}")
            time.sleep(wait)
            return api_call(proxy, method, params, password, attempt + 1)
        raise


def get_all_item_ids(proxy, username, password):
    """Получает список всех jitemid через syncitems."""
    all_ids = {}  # jitemid -> time
    lastsync = ""

    while True:
        params = get_auth(username, password)
        params["lastsync"] = lastsync

        result = api_call(proxy, "syncitems", params, password)
        items = result.get("syncitems", [])
        total = result.get("total", 0)

        for item in items:
            name = str(item.get("item", ""))
            if name.startswith("L-"):
                jitemid = int(name[2:])
                all_ids[jitemid] = item.get("time", "")

        print(f"  syncitems: получено {len(all_ids)}/{total}...", end="\r")

        if not items or len(all_ids) >= total:
            break

        # lastsync = максимальное время из полученных
        times = [item.get("time", "") for item in items if item.get("time")]
        if times:
            lastsync = max(times)
        else:
            break

        time.sleep(0.3)

    print(f"\n  Всего записей в журнале: {len(all_ids)}")
    return all_ids


def fetch_one(proxy, username, password, jitemid):
    """Скачивает один пост по jitemid."""
    params = get_auth(username, password)
    params.update({
        "selecttype": "one",
        "itemid": jitemid,
        "noprops": 0,
        "lineendings": "unix",
    })
    result = api_call(proxy, "getevents", params, password)
    events = result.get("events", [])
    return events[0] if events else None


def decode(val):
    if isinstance(val, xmlrpc.client.Binary):
        return val.data.decode("utf-8", errors="replace")
    if isinstance(val, (int, float)):
        return ""
    return val or ""


def clean_markup(text):
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


def save_post(event, jitemid):
    """Сохраняет пост. Возвращает путь или None если пропущен."""
    eventtime = decode(event.get("eventtime", ""))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", eventtime)
    if not m:
        return None

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < START_YEAR:
        return None

    content = clean_markup(decode(event.get("event", "")))
    if not content:
        return None

    subject = re.sub(r'<[^>]+>', '', decode(event.get("subject", ""))).strip()
    subject = subject or "(без заголовка)"

    security = decode(event.get("security", "")) or "public"
    security_label = {"public": "публичный", "friends": "для друзей",
                      "private": "приватный"}.get(security, security)

    props = event.get("props", {})
    taglist = decode(props.get("taglist", "") if isinstance(props, dict) else "")

    url = f"https://{LJ_USER}.livejournal.com/{event.get('itemid', jitemid)}.html"

    year_dir = os.path.join(OUTPUT_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)

    filename = f"{year}-{month:02d}-{day:02d}-{jitemid}.md"
    path = os.path.join(year_dir, filename)

    if os.path.exists(path):
        return "exists"

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

    return path


def load_progress():
    """Загружает список уже скачанных jitemid из файлов."""
    done = set()
    for root, _, files in os.walk(OUTPUT_DIR):
        for f in files:
            m = re.search(r"-(\d+)\.md$", f)
            if m:
                done.add(int(m.group(1)))
    return done


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"ЖЖ-архив: {LJ_USER}.livejournal.com (с {START_YEAR})")
    username, password = load_credentials()

    proxy = make_proxy()

    try:
        auth = get_auth(username, password)
        info = proxy.LJ.XMLRPC.login(dict(auth))
        print(f"OK: {decode(info.get('fullname', username))}\n" + "-" * 50)
    except xmlrpc.client.Fault as e:
        print(f"Ошибка входа: {e.faultString}")
        return

    # шаг 1: получаем все ID
    print("Шаг 1: получаю список всех записей через syncitems...")
    all_ids = get_all_item_ids(proxy, username, password)

    # шаг 2: определяем что уже есть
    done = load_progress()
    todo = sorted(k for k in all_ids.keys() if k not in done)
    print(f"Уже скачано: {len(done)} | Осталось: {len(todo)}\n" + "-" * 50)

    if not todo:
        print("Всё уже скачано.")
        return

    saved = 0
    skipped = 0

    for i, jitemid in enumerate(todo, 1):
        time.sleep(DELAY)
        try:
            event = fetch_one(proxy, username, password, jitemid)
        except Exception as e:
            print(f"  [{i}/{len(todo)}] ID {jitemid}: ошибка — {e}")
            continue

        if not event:
            skipped += 1
            continue

        result = save_post(event, jitemid)
        if result and result != "exists":
            subject = re.sub(r'<[^>]+>', '', decode(event.get("subject", "")) or "")[:45]
            eventtime = decode(event.get("eventtime", ""))[:10]
            print(f"  [{i}/{len(todo)}] {eventtime} {os.path.basename(result)}: {subject}")
            saved += 1
        elif result == "exists":
            skipped += 1
        else:
            skipped += 1

        if i % 100 == 0:
            print(f"  --- прогресс: {i}/{len(todo)}, сохранено {saved} ---")

    print("\n" + "-" * 50)
    print(f"Сохранено: {saved} | Пропущено: {skipped}")
    print(f"Папка: {os.path.abspath(OUTPUT_DIR)}")


def fill_gaps(from_id, to_id):
    """Перебирает диапазон ID и скачивает пропущенные посты."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"ЖЖ-архив: заполнение пропусков ID {from_id}–{to_id}")
    username, password = load_credentials()
    proxy = make_proxy()

    try:
        auth = get_auth(username, password)
        info = proxy.LJ.XMLRPC.login(dict(auth))
        print(f"OK: {decode(info.get('fullname', username))}\n" + "-" * 50)
    except xmlrpc.client.Fault as e:
        print(f"Ошибка входа: {e.faultString}")
        return

    done = load_progress()
    todo = [i for i in range(from_id, to_id + 1) if i not in done]
    print(f"Пропущенных ID: {len(todo)}\n" + "-" * 50)

    saved = skipped = 0
    for i, jitemid in enumerate(todo, 1):
        time.sleep(DELAY)
        try:
            event = fetch_one(proxy, username, password, jitemid)
        except Exception as e:
            print(f"  [{i}/{len(todo)}] ID {jitemid}: ошибка — {e}")
            continue

        if not event:
            skipped += 1
            continue

        result = save_post(event, jitemid)
        if result and result != "exists":
            subject = re.sub(r'<[^>]+>', '', decode(event.get("subject", "")) or "")[:45]
            eventtime = decode(event.get("eventtime", ""))[:10]
            print(f"  [{i}/{len(todo)}] {eventtime} {os.path.basename(result)}: {subject}")
            saved += 1
        else:
            skipped += 1

        if i % 100 == 0:
            print(f"  --- прогресс: {i}/{len(todo)}, сохранено {saved} ---")

    print("\n" + "-" * 50)
    print(f"Сохранено: {saved} | Пропущено/пустые: {skipped}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--fill-gaps":
        from_id, to_id = int(sys.argv[2].split("-")[0]), int(sys.argv[2].split("-")[1])
        fill_gaps(from_id, to_id)
    else:
        main()
