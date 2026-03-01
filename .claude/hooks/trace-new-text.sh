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

  # Семантические ассоциации — ищем похожее в базе
  REPO_DIR=$(echo "$FILE_PATH" | sed 's|/texts/.*||')
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

exit 0
