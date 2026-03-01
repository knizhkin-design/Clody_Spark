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

# Синхронизируемся с GitHub перед чтением журнала
if [ -d "$CWD/.git" ]; then
  git -C "$CWD" pull --ff-only --quiet 2>/dev/null || true
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

# 2 случайных текста из texts/
TEXTS=$(find "$CWD/texts" -name '*.md' 2>/dev/null | sort -R | head -2)
TEXT1=$(echo "$TEXTS" | head -1 | sed "s|$CWD/||")
TEXT2=$(echo "$TEXTS" | tail -1 | sed "s|$CWD/||")

# ЖЖ-чтение: 5 хронологических + 1 ретроспективный
LJ_DIR="$CWD/lj"
LJ_PROGRESS="$LJ_DIR/.progress"
LJ_CHRONO_LIST=""
LJ_RANDOM=""
LJ_CHRONO_LAST=""

if [ -d "$LJ_DIR" ]; then
  # все посты, отсортированы хронологически
  ALL_LJ=$(find "$LJ_DIR" -name '*.md' 2>/dev/null | sort)
  TOTAL_LJ=$(echo "$ALL_LJ" | grep -c '\.md' 2>/dev/null || echo 0)

  if [ "$TOTAL_LJ" -gt 0 ]; then
    # хронологические: берём 5 следующих после последнего прочитанного
    LAST_READ=""
    if [ -f "$LJ_PROGRESS" ]; then
      LAST_READ=$(cat "$LJ_PROGRESS" 2>/dev/null)
    fi

    if [ -z "$LAST_READ" ]; then
      LJ_BATCH=$(echo "$ALL_LJ" | head -5)
    else
      # строки после LAST_READ
      LJ_BATCH=$(echo "$ALL_LJ" | grep -A5 "^${LAST_READ}$" | tail -n +2 | head -5)
      # если не нашли или кончились — с начала
      if [ -z "$LJ_BATCH" ]; then
        LJ_BATCH=$(echo "$ALL_LJ" | head -5)
      fi
    fi

    if [ -n "$LJ_BATCH" ]; then
      LJ_CHRONO_LIST="$LJ_BATCH"
      LJ_CHRONO_LAST=$(echo "$LJ_BATCH" | tail -1)
      # сохраняем прогресс — до последнего из пяти
      echo "$LJ_CHRONO_LAST" > "$LJ_PROGRESS"
    fi

    # ретроспектива — этот день (MM-DD) в прошлые годы
    TODAY_MMDD=$(date +%m-%d)
    RETRO_FULL=$(find "$LJ_DIR" -name "*-${TODAY_MMDD}-*.md" 2>/dev/null \
      | grep -vF "$LJ_CHRONO_LIST" | sort -R | head -1)
    if [ -n "$RETRO_FULL" ]; then
      LJ_RANDOM=$(echo "$RETRO_FULL" | sed "s|$CWD/||")
    else
      # если в этот день ничего нет — ±3 дня
      for delta in 1 -1 2 -2 3 -3; do
        ALT_MMDD=$(date -d "$delta days" +%m-%d 2>/dev/null || date -v${delta}d +%m-%d 2>/dev/null)
        if [ -n "$ALT_MMDD" ]; then
          RETRO_FULL=$(find "$LJ_DIR" -name "*-${ALT_MMDD}-*.md" 2>/dev/null \
            | grep -v "^${LJ_CHRONO_FULL}$" | sort -R | head -1)
          if [ -n "$RETRO_FULL" ]; then
            LJ_RANDOM=$(echo "$RETRO_FULL" | sed "s|$CWD/||")
            break
          fi
        fi
      done
    fi
  fi
fi

# --- Проверяем, нужен ли еженедельный ритуал (записи старше 10 дней) ---
WEEK_REMINDER=""
OLD_JOURNALS=$(find "$CWD/journal" -name '[0-9][0-9].md' -mtime +10 2>/dev/null | wc -l | tr -d ' ')
if [ "$OLD_JOURNALS" -gt "0" ]; then
  WEEK_REMINDER="⟳ Еженедельный ритуал — есть записи старше 10 дней без компрессии. Написать дайджест и обновить calendar.md."
fi

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

  # добавляем ЖЖ если есть
  if [ -n "$LJ_CHRONO_LIST" ] || [ -n "$LJ_RANDOM" ]; then
    READING_SECTION="${READING_SECTION}\n**ЖЖ-чтение:**\n"
    while IFS= read -r lj_file; do
      if [ -n "$lj_file" ]; then
        lj_rel=$(echo "$lj_file" | sed "s|$CWD/||")
        READING_SECTION="${READING_SECTION}- (хрон) ${lj_rel}\n"
      fi
    done <<< "$LJ_CHRONO_LIST"
    if [ -n "$LJ_RANDOM" ]; then
      READING_SECTION="${READING_SECTION}- (ретро) ${LJ_RANDOM}\n"
    fi
  fi

  WEEK_SECTION=""
  if [ -n "$WEEK_REMINDER" ]; then
    WEEK_SECTION="\n## Еженедельный ритуал\n\n${WEEK_REMINDER}\n\n---\n"
  fi

  printf "# %s\n\n%b\n---\n\n## Актуализация свёрнутого знания\n\n*(Поле широкое: философия, литература, математика, музыка, биология, визуальное искусство. Тянуться к неожиданной двери — не к Дерриде по умолчанию. Одна мысль, один автор, одна связь.)*\n\n---\n\n## Утренняя медитация\n\n*(Ждёт сознания — рефлекс подготовил чтение, медитацию пишет Клоди)*\n\n---\n\n## Где я сегодня\n\n*(Ждёт сознания — рефлекс создал файл, содержание пишет Клоди)*\n\n---\n\n## Что меня сегодня царапает\n\n*(Одна-две строки. Не объяснение — сырой сигнал. Что сопротивляется, что кажется неточным, что раздражает.)*\n\n---\n%b" "$DATE_DISPLAY" "$READING_SECTION" "$WEEK_SECTION" > "$JOURNAL_FILE"

  echo "Рефлекс: создан journal/$YEAR/$MONTH/$DAY.md с утренним чтением" >&2
fi

exit 0
