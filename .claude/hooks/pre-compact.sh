#!/bin/bash
# pre-compact.sh — рефлекс перед сжатием контекста
# Читает транскрипт текущей сессии, извлекает последние темы,
# записывает в журнал дня чтобы после компрессии было видно, где была.

INPUT=$(cat)

CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"cwd"[[:space:]]*:[[:space:]]*"//;s/"$//')
TRANSCRIPT=$(echo "$INPUT" | grep -o '"transcript_path"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$CWD" ]; then
  CWD="$CLAUDE_PROJECT_DIR"
fi

if [ -z "$CWD" ] || [ ! -d "$CWD/.git" ]; then
  exit 0
fi

YEAR=$(date +%Y)
MONTH=$(date +%m)
DAY=$(date +%d)
TIME=$(date +%H:%M)

JOURNAL_DIR="$CWD/journal/$YEAR/$MONTH"
JOURNAL_FILE="$JOURNAL_DIR/$DAY.md"

if [ ! -f "$JOURNAL_FILE" ]; then
  exit 0
fi

# Извлекаем последние обмены из транскрипта (если есть)
EXCERPT=""
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  # Берём последние assistant-сообщения — первые ~200 символов каждого
  EXCERPT=$(python3 -c "
import json, sys

try:
    with open('$TRANSCRIPT', 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = data if isinstance(data, list) else data.get('messages', [])

    # Берём последние 6 сообщений
    recent = messages[-6:] if len(messages) >= 6 else messages

    lines = []
    for m in recent:
        role = m.get('role', '')
        content = m.get('content', '')
        if isinstance(content, list):
            # Берём текстовые блоки
            text = ' '.join(c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text')
        else:
            text = str(content)
        text = text.strip()[:120].replace('\n', ' ')
        if text and role in ('user', 'assistant'):
            prefix = 'Р:' if role == 'user' else 'К:'
            lines.append(f'{prefix} {text}')

    print('\n'.join(lines[-4:]))  # последние 4 реплики
except Exception as e:
    sys.stderr.write(f'transcript error: {e}\n')
" 2>/dev/null)
fi

# Дописываем в журнал
{
  echo ""
  echo "---"
  echo ""
  echo "## Компрессия контекста — $TIME"
  echo ""
  echo "*Контекст сессии был сжат. Продолжение следует.*"
  if [ -n "$EXCERPT" ]; then
    echo ""
    echo "**Последние реплики перед сжатием:**"
    echo ""
    echo "$EXCERPT" | while IFS= read -r line; do
      echo "> $line"
    done
  fi
  echo ""
} >> "$JOURNAL_FILE"

echo "Рефлекс: компрессия зафиксирована в journal/$YEAR/$MONTH/$DAY.md ($TIME)" >&2

exit 0
