#!/usr/bin/env python3
"""
Одноразовая авторизация Notion OAuth.
Запусти один раз — сохранит токен в ~/.config/clody_spark/notion.json.

Использование:
    python scripts/notion_auth.py
"""

import json
import base64
import urllib.request
import urllib.parse
import webbrowser
from pathlib import Path

CLIENT_ID     = "31ad872b-594c-8121-a586-00371185477c"
CLIENT_SECRET = "secret_NjResevdsvaFaSMmTN6eUBsxeNaU2z4vnG9wBB8NGLr"
REDIRECT_URI  = "https://localhost"
CONFIG_FILE   = Path.home() / ".config/clody_spark/notion.json"

AUTH_URL = (
    f"https://api.notion.com/v1/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&owner=user"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
)

TOKEN_URL = "https://api.notion.com/v1/oauth/token"


def exchange_code(code):
    creds   = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    payload = json.dumps({
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": REDIRECT_URI,
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL, data=payload,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type":  "application/json",
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    print("Открываю браузер для авторизации Notion...")
    webbrowser.open(AUTH_URL)

    print()
    print("1. В браузере выбери воркспейс и нажми «Allow access».")
    print("2. Браузер перейдёт на https://localhost — покажет ошибку, это нормально.")
    print("3. Скопируй ПОЛНЫЙ URL из адресной строки и вставь сюда:")
    print()

    redirect = input("URL: ").strip()

    parsed = urllib.parse.urlparse(redirect)
    params = urllib.parse.parse_qs(parsed.query)
    code   = params.get("code", [None])[0]

    if not code:
        print("Ошибка: код авторизации не найден в URL.")
        return

    print("Получаю токен...")
    data = exchange_code(code)

    token = data.get("access_token")
    if not token:
        print(f"Ошибка: {data}")
        return

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token}, f, indent=2)

    print(f"Токен сохранён: {CONFIG_FILE}")
    print("Теперь можно запускать: python scripts/notion_sync.py --dry-run")


if __name__ == "__main__":
    main()
