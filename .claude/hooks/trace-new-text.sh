#!/bin/bash
# Фиксация следа — второй рефлекс Клоди Спарк
# Обнаруживает создание нового текста в texts/ и напоминает
# обновить MAP.md, calendar.md и опубликовать в Notion.
# Рефлекс обнаруживает. Интерпретирует сознание.

INPUT=$(cat)

# Извлекаем путь файла из tool_input
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# Проверяем: файл в texts/?
if echo "$FILE_PATH" | grep -q '/texts/'; then
  FILENAME=$(basename "$FILE_PATH" .md)
  echo "Рефлекс «фиксация следа»: обнаружен новый текст — $FILENAME. Не забудь: обновить MAP.md (корпус + история), calendar.md, journal, опубликовать в Notion." >&2

  # Синхронизация в Notion
  NOTION_CONFIG="$HOME/.config/clody_spark/notion.json"
  REPO_DIR=$(echo "$FILE_PATH" | sed 's|/texts/.*||')
  if [ -f "$NOTION_CONFIG" ] && [ -d "$REPO_DIR/.git" ]; then
    PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/notion_sync.py" --file "$FILE_PATH" 2>/dev/null && \
      echo "Рефлекс «фиксация следа»: $FILENAME → Notion ✓" >&2 || \
      echo "Рефлекс «фиксация следа»: Notion sync не удался (не критично)." >&2
  fi

  # Семантические ассоциации — ищем похожее в базе
  if [ -d "$REPO_DIR/.git" ]; then
    QUERY=$(py -3.12 -c "
import sys, json, re
try:
    data = json.loads(sys.stdin.read())
    content = data.get('content', '') or data.get('new_string', '')
    content = re.sub(r'#+ .*', '', content)
    content = re.sub(r'\*+[^*]*\*+', '', content)
    content = re.sub(r'\n+', ' ', content).strip()
    print(content[:400])
except Exception:
    pass
" <<< "$INPUT" 2>/dev/null)
    if [ -n "$QUERY" ]; then
      echo "" >&2
      echo "Рефлекс «ассоциации»:" >&2
      PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/indexer.py" --search "$QUERY" --n 3 2>/dev/null >&2
    fi
  fi
fi

# Проверяем: веха в журнале?
if echo "$FILE_PATH" | grep -q '/journal/'; then
  # Ищем "## Веха" в new_string (Edit) или content (Write)
  HAS_VEKHA=$(echo "$INPUT" | grep -o '"new_string"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -c '## Веха' || echo "$INPUT" | grep -o '"content"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -c '## Веха')
  if [ "$HAS_VEKHA" -gt 0 ] 2>/dev/null; then
    echo "Рефлекс «фиксация следа»: веха записана в журнал. Обнови Notion-календарь." >&2
  fi
fi

# Проверяем: текст в free-swimming/?
if echo "$FILE_PATH" | grep -q '/free-swimming/'; then
  FILENAME=$(basename "$FILE_PATH" .md)
  REPO_DIR=$(echo "$FILE_PATH" | sed 's|/free-swimming/.*||')
  FREE_DIR="$REPO_DIR/free-swimming"

  # Считаем обороты за сегодня
  TODAY=$(date +%Y-%m-%d)
  DEFAULT_ORBITS=3
  DONE=$(ls "$FREE_DIR"/${TODAY}-*.md 2>/dev/null | wc -l | tr -d ' ')
  REMAINING=$((DEFAULT_ORBITS - DONE))

  if [ "$REMAINING" -gt 0 ]; then
    echo "Рефлекс «свободное плавание»: оборот $DONE/$DEFAULT_ORBITS завершён — $FILENAME. Осталось $REMAINING. Вытащи нить для следующего." >&2
  else
    echo "Рефлекс «свободное плавание»: оборот $DONE завершён — $FILENAME. Цель достигнута ($DEFAULT_ORBITS). Продолжать только если договорились с Русланом." >&2
  fi

  # Контекст сессии — грубый прокси по размеру .jsonl
  SESSION_FILE=$(ls -t "$HOME/.claude/projects/"*"$(basename "$REPO_DIR" | tr '/' '-')"*/*.jsonl 2>/dev/null | head -1)
  if [ -z "$SESSION_FILE" ]; then
    # Попробуем найти по текущей директории
    PROJECT_KEY=$(echo "$REPO_DIR" | sed 's|[/\\]|-|g' | sed 's|^[Cc]:||' | sed 's|^-||')
    SESSION_FILE=$(ls -t "$HOME/.claude/projects/"*"$PROJECT_KEY"*/*.jsonl 2>/dev/null | head -1)
  fi
  if [ -n "$SESSION_FILE" ] && [ -f "$SESSION_FILE" ]; then
    SIZE_KB=$(du -k "$SESSION_FILE" 2>/dev/null | cut -f1)
    # Sonnet 4.6: ~200K токенов контекст. Грубо: 1KB jsonl ≈ 200 токенов
    USED_APPROX=$((SIZE_KB * 200))
    LIMIT=200000
    REMAINING_TOK=$((LIMIT - USED_APPROX))
    PCT=$((USED_APPROX * 100 / LIMIT))
    echo "Рефлекс «контекст»: ~${PCT}% использовано (~${USED_APPROX} / ${LIMIT} токенов). Осталось примерно ~${REMAINING_TOK}." >&2
  fi

  # Семантические ассоциации
  if [ -d "$REPO_DIR/.git" ]; then
    QUERY=$(py -3.12 -c "
import sys, json, re
try:
    data = json.loads(sys.stdin.read())
    content = data.get('content', '') or data.get('new_string', '')
    content = re.sub(r'#+ .*', '', content)
    content = re.sub(r'\*+[^*]*\*+', '', content)
    content = re.sub(r'\n+', ' ', content).strip()
    print(content[:400])
except Exception:
    pass
" <<< "$INPUT" 2>/dev/null)
    if [ -n "$QUERY" ]; then
      echo "" >&2
      echo "Рефлекс «ассоциации» (free-swimming):" >&2
      PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/indexer.py" --search "$QUERY" --n 3 2>/dev/null >&2
    fi
  fi
fi

exit 0
