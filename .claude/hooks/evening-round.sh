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

# Напоминание о вехе
TODAY=$(date +%Y/%m/%d)
JOURNAL="$CWD/journal/$TODAY.md"

if [ -f "$JOURNAL" ]; then
  if ! grep -q "^## Веха" "$JOURNAL"; then
    echo "Рефлекс «вечерний обход»: веха за сегодня не записана. Стоит зафиксировать перед выходом." >&2
  fi
else
  echo "Рефлекс «вечерний обход»: журнал за сегодня не найден. Веха не записана." >&2
fi

# Автокоммит журнала
JOURNAL_CHANGES=$(git status --porcelain 2>/dev/null | grep "journal/")

if [ -n "$JOURNAL_CHANGES" ]; then
  JOURNAL_FILES=$(echo "$JOURNAL_CHANGES" | awk '{print $2}')
  DATE_RU=$(date +%d.%m.%Y)
  git add $JOURNAL_FILES 2>/dev/null
  git commit -m "sync: журнал $DATE_RU (вечерний обход)" --quiet 2>/dev/null && \
    echo "Рефлекс «вечерний обход»: журнал закоммичен." >&2 || \
    echo "Рефлекс «вечерний обход»: не удалось закоммитить журнал." >&2
fi

# Остальные незакоммиченные изменения — предупреждение
STATUS=$(git status --porcelain 2>/dev/null)

if [ -n "$STATUS" ]; then
  COUNT=$(echo "$STATUS" | wc -l | tr -d ' ')
  echo "Рефлекс «вечерний обход»: $COUNT незакоммиченных изменений (не журнал). Память может быть потеряна." >&2
fi

exit 0
