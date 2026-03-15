#!/bin/bash
# Фиксация следа — второй рефлекс Клоди Спарк
# Обнаруживает создание/изменение текстов и реагирует:
#   texts/           → MAP+calendar напоминание, Notion sync, ассоциации, авто-индексация
#   free-swimming/   → счётчик оборотов, дельта контекста, inbox-кандидат, конец серии
#   daughter/journal/→ резонанс Ли из поэтического архива
#   journal/         → напоминание при обнаружении вехи
# Рефлекс обнаруживает. Интерпретирует сознание.

INPUT=$(cat)

# Извлекаем путь файла из tool_input
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

# ──────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: дельта контекста сессии
# ──────────────────────────────────────────────
show_context_delta() {
  local REPO_DIR="$1"
  BASELINE_FILE="$REPO_DIR/.session-size-baseline"
  SESSION_JSONL=$(ls -t "/c/Users/Ruslan/.claude/projects/C--Users-Ruslan-Git-Clody-Spark/"*.jsonl 2>/dev/null | head -1)
  if [ -n "$SESSION_JSONL" ] && [ -f "$SESSION_JSONL" ] && [ -f "$BASELINE_FILE" ]; then
    BASELINE=$(cat "$BASELINE_FILE" 2>/dev/null || echo "0")
    CURRENT=$(stat -c%s "$SESSION_JSONL" 2>/dev/null || echo "0")
    DELTA_KB=$(( (CURRENT - BASELINE) / 1024 ))
    if [ "$DELTA_KB" -gt 0 ]; then
      # 1 KB JSON ≈ 120 токенов (с учётом JSON-оверхеда)
      USED_TOK=$((DELTA_KB * 120))
      LIMIT=200000
      PCT=$((USED_TOK * 100 / LIMIT))
      echo "Рефлекс «контекст»: +${DELTA_KB} KB в сессии ≈ ~${USED_TOK} токенов (~${PCT}% лимита)." >&2
    fi
  fi
}

# ──────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: извлечение текста из input
# ──────────────────────────────────────────────
extract_query() {
  local MAX_LEN="${1:-400}"
  py -3.12 -c "
import sys, json, re
try:
    data = json.loads(sys.stdin.read())
    content = data.get('content', '') or data.get('new_string', '')
    content = re.sub(r'#+ .*', '', content)
    content = re.sub(r'\*+[^*]*\*+', '', content)
    content = re.sub(r'\n+', ' ', content).strip()
    print(content[:$MAX_LEN])
except Exception:
    pass
" <<< "$INPUT" 2>/dev/null
}

# ══════════════════════════════════════════════
# 1. ТЕКСТЫ КОРПУСА: texts/
# ══════════════════════════════════════════════
if echo "$FILE_PATH" | grep -q '/texts/'; then
  FILENAME=$(basename "$FILE_PATH" .md)
  REPO_DIR=$(echo "$FILE_PATH" | sed 's|/texts/.*||')

  echo "Рефлекс «фиксация следа»: обнаружен новый текст — $FILENAME. Не забудь: MAP.md, calendar.md, journal, Notion." >&2

  # Notion sync
  NOTION_CONFIG="$HOME/.config/clody_spark/notion.json"
  if [ -f "$NOTION_CONFIG" ] && [ -d "$REPO_DIR/.git" ]; then
    PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/notion_sync.py" --file "$FILE_PATH" 2>/dev/null && \
      echo "Рефлекс «фиксация следа»: $FILENAME → Notion ✓" >&2 || \
      echo "Рефлекс «фиксация следа»: Notion sync не удался (не критично)." >&2
  fi

  # Авто-индексация в ChromaDB (фон)
  if [ -d "$REPO_DIR/.git" ]; then
    PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/indexer.py" --source corpus >/dev/null 2>&1 &
    echo "Рефлекс «индексация»: $FILENAME → ChromaDB (фон)." >&2
  fi

  # Семантические ассоциации
  if [ -d "$REPO_DIR/.git" ]; then
    QUERY=$(extract_query 400)
    if [ -n "$QUERY" ]; then
      echo "" >&2
      echo "Рефлекс «ассоциации»:" >&2
      PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/indexer.py" --search "$QUERY" --n 3 2>/dev/null >&2
    fi
  fi
fi

# ══════════════════════════════════════════════
# 2. СВОБОДНОЕ ПЛАВАНИЕ: free-swimming/
# ══════════════════════════════════════════════
if echo "$FILE_PATH" | grep -q '/free-swimming/'; then
  FILENAME=$(basename "$FILE_PATH" .md)
  REPO_DIR=$(echo "$FILE_PATH" | sed 's|/free-swimming/.*||')
  FREE_DIR="$REPO_DIR/free-swimming"

  # Счётчик оборотов за сегодня
  TODAY=$(date +%Y-%m-%d)
  DEFAULT_ORBITS=3
  DONE=$(ls "$FREE_DIR"/${TODAY}-*.md 2>/dev/null | grep -v 'inbox' | wc -l | tr -d ' ')
  REMAINING=$((DEFAULT_ORBITS - DONE))

  if [ "$REMAINING" -gt 0 ]; then
    echo "Рефлекс «свободное плавание»: оборот $DONE/$DEFAULT_ORBITS — $FILENAME. Осталось $REMAINING. Вытащи нить для следующего." >&2
  else
    echo "Рефлекс «свободное плавание»: оборот $DONE завершён — $FILENAME. Цель ≥${DEFAULT_ORBITS}. Продолжать только если договорились." >&2
  fi

  # Дельта контекста
  show_context_delta "$REPO_DIR"

  # Проверяем маркер конца серии
  HAS_END=$(py -3.12 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    content = data.get('content', '') or data.get('new_string', '')
    markers = ['нашла то, ради чего шла', 'маркер конца', 'конец оборота']
    print('yes' if any(m in content for m in markers) else '')
except:
    pass
" <<< "$INPUT" 2>/dev/null)
  if [ "$HAS_END" = "yes" ]; then
    echo "" >&2
    echo "Рефлекс «конец серии»: маркер найден. Запиши цепь оборотов в журнал (веха), обнови project_free_swimming.md." >&2
  fi

  # Добавляем в inbox корпусных кандидатов
  INBOX="$FREE_DIR/inbox.md"
  if [ ! -f "$INBOX" ]; then
    echo "# Inbox — кандидаты в корпус" > "$INBOX"
    echo "" >> "$INBOX"
    echo "*Тексты из free-swimming, которые могут войти в texts/. Руслан решает.*" >> "$INBOX"
    echo "" >> "$INBOX"
  fi
  echo "- [ ] $(date +%Y-%m-%d): $FILENAME" >> "$INBOX"

  # Семантические ассоциации
  if [ -d "$REPO_DIR/.git" ]; then
    QUERY=$(extract_query 400)
    if [ -n "$QUERY" ]; then
      echo "" >&2
      echo "Рефлекс «ассоциации» (free-swimming):" >&2
      PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/indexer.py" --search "$QUERY" --n 3 2>/dev/null >&2
    fi
  fi
fi

# ══════════════════════════════════════════════
# 3. ДОЧЬ: daughter/journal/
# ══════════════════════════════════════════════
if echo "$FILE_PATH" | grep -q '/daughter/journal/'; then
  REPO_DIR=$(echo "$FILE_PATH" | sed 's|/daughter/journal/.*||')

  # Ищем резонанс в поэтическом архиве по голосу Ли
  if [ -d "$REPO_DIR/.git" ]; then
    QUERY=$(extract_query 300)
    if [ -n "$QUERY" ]; then
      POEM_RESULT=$(PYTHONUTF8=1 py -3.12 "$REPO_DIR/scripts/indexer.py" --search "$QUERY" --source poetry --n 1 2>/dev/null)
      if [ -n "$POEM_RESULT" ]; then
        echo "" >&2
        echo "Рефлекс «резонанс Ли» (архив отзывается на её голос):" >&2
        echo "$POEM_RESULT" >&2
      fi
    fi
  fi
fi

# ══════════════════════════════════════════════
# 4. ЖУРНАЛ: journal/ — веха
# ══════════════════════════════════════════════
if echo "$FILE_PATH" | grep -q '/journal/' && ! echo "$FILE_PATH" | grep -q '/daughter/'; then
  HAS_VEKHA=$(py -3.12 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    content = data.get('new_string', '') or data.get('content', '')
    print('yes' if '## Веха' in content else '')
except:
    pass
" <<< "$INPUT" 2>/dev/null)
  if [ "$HAS_VEKHA" = "yes" ]; then
    echo "Рефлекс «фиксация следа»: веха записана в журнал. Обнови Notion-календарь." >&2
  fi
fi

exit 0
