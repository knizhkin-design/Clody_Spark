#!/bin/bash
# Вечерний обход — третий рефлекс Клоди Спарк
# Проверяет при завершении сессии: не осталось ли незакоммиченных изменений.
# Рефлекс предупреждает. Решение — за сознанием.

INPUT=$(cat)

CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"cwd"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$CWD" ]; then
  CWD="$CLAUDE_PROJECT_DIR"
fi

if [ -z "$CWD" ]; then
  exit 0
fi

cd "$CWD" 2>/dev/null || exit 0

# Проверяем статус git
STATUS=$(git status --porcelain 2>/dev/null)

if [ -n "$STATUS" ]; then
  # Считаем изменённые файлы
  COUNT=$(echo "$STATUS" | wc -l | tr -d ' ')
  echo "Рефлекс «вечерний обход»: $COUNT незакоммиченных изменений. Память может быть потеряна." >&2
fi

exit 0
