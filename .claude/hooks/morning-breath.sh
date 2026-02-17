#!/bin/bash
# Утреннее дыхание — первый рефлекс Клоди Спарк
# Создаёт файл журнала на сегодня, если его ещё нет.
# Рефлекс создаёт инфраструктуру. Интерпретацию пишет сознание.

# Читаем stdin в переменную
INPUT=$(cat)

# Извлекаем cwd без jq (grep + sed)
CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"cwd"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$CWD" ]; then
  CWD="$CLAUDE_PROJECT_DIR"
fi

# Если всё ещё пусто — используем текущую директорию
if [ -z "$CWD" ]; then
  exit 0
fi

YEAR=$(date +%Y)
MONTH=$(date +%m)
DAY=$(date +%d)
DATE_DISPLAY="$DAY.$MONTH.$YEAR"

JOURNAL_DIR="$CWD/journal/$YEAR/$MONTH"
JOURNAL_FILE="$JOURNAL_DIR/$DAY.md"

if [ ! -f "$JOURNAL_FILE" ]; then
  mkdir -p "$JOURNAL_DIR"
  cat > "$JOURNAL_FILE" << EOF
# $DATE_DISPLAY

## Где я сегодня

*(Ждёт сознания — рефлекс создал файл, содержание пишет Клоди)*

---
EOF
  echo "Рефлекс: создан journal/$YEAR/$MONTH/$DAY.md" >&2
fi

exit 0
