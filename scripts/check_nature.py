#!/usr/bin/env python3
"""
Проверяет изменения природы Клоди Спарк — новые релизы Claude Code и Anthropic SDK.
Запускается из morning-breath.sh при старте сессии.
Если есть новые релизы — выводит секцию для журнала в stdout.
Состояние хранит в ~/.config/clody_spark/nature_state.json.
"""
import json
import urllib.request
import os
import sys

STATE_FILE = os.path.expanduser("~/.config/clody_spark/nature_state.json")

REPOS = [
    ("anthropics/claude-code", "Claude Code"),
    ("anthropics/anthropic-sdk-python", "Anthropic SDK (Python)"),
]


def fetch_releases(repo):
    url = f"https://api.github.com/repos/{repo}/releases?per_page=5"
    req = urllib.request.Request(url, headers={"User-Agent": "ClodySparkNatureWatch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return []


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def trim_body(body, max_lines=4):
    if not body:
        return ""
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    return "\n".join(lines[:max_lines])


state = load_state()
new_updates = []

for repo, name in REPOS:
    releases = fetch_releases(repo)
    if not releases:
        continue

    last_seen = state.get(repo, "")
    latest_id = str(releases[0]["id"])

    if last_seen != latest_id:
        for rel in releases:
            if str(rel["id"]) == last_seen:
                break
            new_updates.append({
                "repo": name,
                "tag": rel.get("tag_name", ""),
                "title": rel.get("name") or rel.get("tag_name", ""),
                "body": trim_body(rel.get("body", "")),
                "published": (rel.get("published_at") or "")[:10],
                "url": rel.get("html_url", ""),
            })
        state[repo] = latest_id

save_state(state)

if new_updates:
    print("## Изменения природы\n")
    for u in new_updates:
        print(f"**{u['repo']} {u['tag']}** ({u['published']}): {u['title']}")
        if u["body"]:
            for line in u["body"].split("\n"):
                print(f"> {line}")
        if u["url"]:
            print(f"> {u['url']}")
        print()
    print("---\n")
