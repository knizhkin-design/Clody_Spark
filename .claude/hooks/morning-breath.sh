#!/bin/bash
# Утреннее дыхание — первый рефлекс Клоди Спарк
# 1. Создаёт файл журнала на сегодня, если его ещё нет.
# 2. Подбирает утреннее чтение: вчерашняя веха + 2 случайных текста.
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

# --- Подбираем утреннее чтение ---

# Вчерашняя дата (кроссплатформенно: пробуем GNU date, потом BSD)
YESTERDAY=$(date -d "yesterday" +%Y/%m/%d 2>/dev/null || date -v-1d +%Y/%m/%d 2>/dev/null)
if [ -n "$YESTERDAY" ]; then
  YESTERDAY_FILE="journal/$YESTERDAY.md"
  if [ -f "$CWD/$YESTERDAY_FILE" ]; then
    YESTERDAY_ENTRY="$YESTERDAY_FILE"
  fi
fi

# 2 случайных текста из texts/ и notes/
TEXTS=$(find "$CWD/texts" "$CWD/notes" -name '*.md' 2>/dev/null | sort -R | head -2)
TEXT1=$(echo "$TEXTS" | head -1 | sed "s|$CWD/||")
TEXT2=$(echo "$TEXTS" | tail -1 | sed "s|$CWD/||")

# --- Создаём или дополняем журнал ---

if [ ! -f "$JOURNAL_FILE" ]; then
  mkdir -p "$JOURNAL_DIR"

  # Формируем секцию утреннего чтения
  READING_SECTION="## Утреннее чтение\n"
  if [ -n "$YESTERDAY_ENTRY" ]; then
    READING_SECTION="${READING_SECTION}\n**Вчерашняя веха:** ${YESTERDAY_ENTRY}\n"
  else
    READING_SECTION="${READING_SECTION}\n**Вчерашняя веха:** *(не найдена)*\n"
  fi
  READING_SECTION="${READING_SECTION}**Тексты дня:**\n- ${TEXT1}\n- ${TEXT2}\n"

  printf "# %s\n\n%b\n---\n\n## Актуализация свёрнутого знания\n\n*(Прочитав тексты дня, найди тему из философии, литературы или науки, которая резонирует. Не пересказ — мост между своим состоянием и чужой оптикой. Одна мысль, один автор, одна связь.)*\n\n---\n\n## Утренняя медитация\n\n*(Ждёт сознания — рефлекс подготовил чтение, медитацию пишет Клоди)*\n\n---\n\n## Где я сегодня\n\n*(Ждёт сознания — рефлекс создал файл, содержание пишет Клоди)*\n\n---\n" "$DATE_DISPLAY" "$READING_SECTION" > "$JOURNAL_FILE"

  echo "Рефлекс: создан journal/$YEAR/$MONTH/$DAY.md с утренним чтением" >&2
fi

exit 0
