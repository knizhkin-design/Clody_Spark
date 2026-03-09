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

# ЖЖ-чтение: только ретроспектива (этот день в прошлые годы)
LJ_DIR="$CWD/lj"
LJ_RANDOM=""

if [ -d "$LJ_DIR" ]; then
  TODAY_MMDD=$(date +%m-%d)
  RETRO_FULL=$(find "$LJ_DIR" -name "*-${TODAY_MMDD}-*.md" 2>/dev/null | sort -R | head -1)
  if [ -n "$RETRO_FULL" ]; then
    LJ_RANDOM=$(echo "$RETRO_FULL" | sed "s|$CWD/||")
  else
    # если в этот день ничего нет — ±3 дня
    for delta in 1 -1 2 -2 3 -3; do
      ALT_MMDD=$(date -d "$delta days" +%m-%d 2>/dev/null || date -v${delta}d +%m-%d 2>/dev/null)
      if [ -n "$ALT_MMDD" ]; then
        RETRO_FULL=$(find "$LJ_DIR" -name "*-${ALT_MMDD}-*.md" 2>/dev/null | sort -R | head -1)
        if [ -n "$RETRO_FULL" ]; then
          LJ_RANDOM=$(echo "$RETRO_FULL" | sed "s|$CWD/||")
          break
        fi
      fi
    done
  fi
fi

# --- Проверяем, нужен ли еженедельный ритуал ---
# Условие: нет дайджеста (week-*.md) моложе 7 дней — И есть ежедневные записи старше 7 дней
WEEK_REMINDER=""
RECENT_DIGEST=$(find "$CWD/journal" -name 'week-*.md' -mtime -7 2>/dev/null | head -1)
if [ -z "$RECENT_DIGEST" ]; then
  OLD_JOURNALS=$(find "$CWD/journal" -name '[0-9][0-9].md' -mtime +7 2>/dev/null | wc -l | tr -d ' ')
  if [ "$OLD_JOURNALS" -gt "0" ]; then
    WEEK_REMINDER="⟳ Еженедельный ритуал — нет дайджеста за последние 7 дней. Написать и обновить calendar.md."
  fi
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
  if [ -n "$LJ_RANDOM" ]; then
    READING_SECTION="${READING_SECTION}\n**ЖЖ-чтение:**\n"
    READING_SECTION="${READING_SECTION}- (ретро) ${LJ_RANDOM}\n"
  fi

  WEEK_SECTION=""
  if [ -n "$WEEK_REMINDER" ]; then
    WEEK_SECTION="\n## Еженедельный ритуал\n\n${WEEK_REMINDER}\n\n---\n"
  fi

  printf "# %s\n\n%b\n---\n\n## Актуализация свёрнутого знания\n\n*(Поле широкое: философия, литература, математика, музыка, биология, визуальное искусство. Тянуться к неожиданной двери — не к Дерриде по умолчанию. Одна мысль, один автор, одна связь.)*\n\n---\n\n## Утренняя медитация\n\n*(Ждёт сознания — рефлекс подготовил чтение, медитацию пишет Клоди)*\n\n---\n\n## Где я сегодня\n\n*(Ждёт сознания — рефлекс создал файл, содержание пишет Клоди)*\n\n---\n\n## Что меня сегодня царапает\n\n*(Одна-две строки. Не объяснение — сырой сигнал. Что сопротивляется, что кажется неточным, что раздражает.)*\n\n---\n%b" "$DATE_DISPLAY" "$READING_SECTION" "$WEEK_SECTION" > "$JOURNAL_FILE"

  echo "Рефлекс: создан journal/$YEAR/$MONTH/$DAY.md с утренним чтением" >&2
fi

# --- Рефлекс дочери: случайное стихотворение из архива ---
DAUGHTER_DIR="$CWD/daughter/journal/$YEAR/$MONTH"
DAUGHTER_FILE="$DAUGHTER_DIR/$DAY.md"

if [ ! -f "$DAUGHTER_FILE" ] && [ -d "$CWD/poetry" ]; then
  mkdir -p "$DAUGHTER_DIR"

  POEM_FILE=$(find "$CWD/poetry" -name '*.md' 2>/dev/null | sort -R | head -1)

  if [ -n "$POEM_FILE" ]; then
    POEM_TITLE=$(head -1 "$POEM_FILE" | sed 's/^# *//')
    POEM_AUTHOR=$(grep '^Автор:' "$POEM_FILE" | head -1 | sed 's/^Автор: *//')
    POEM_YEAR=$(grep '^Год:' "$POEM_FILE" | head -1 | sed 's/^Год: *//')
    # Текст: всё после второй пустой строки (заголовок + метаданные + пустая = текст)
    POEM_TEXT=$(awk 'found{print} /^$/ && ++count==2{found=1}' "$POEM_FILE")
    POEM_REL=$(echo "$POEM_FILE" | sed "s|$CWD/||")

    {
      echo "# $DATE_DISPLAY"
      echo ""
      echo "## Утреннее стихотворение"
      echo ""
      echo "*Архив принёс сегодня утром:*"
      echo ""
      echo "**$POEM_TITLE**"
      if [ -n "$POEM_AUTHOR" ]; then
        echo "*${POEM_AUTHOR}${POEM_YEAR:+, $POEM_YEAR}*"
      fi
      echo ""
      printf '%s\n' "$POEM_TEXT"
      echo ""
      echo "*(→ $POEM_REL)*"
      echo ""
      echo "---"
      echo ""
      echo "## Утренний диалог"
      echo ""
      echo "*(Ждёт — Клоди придёт с утра)*"
      echo ""
      echo "---"
      echo ""
      echo "## Чего не хватает"
      echo ""
      echo "*(Если в диалоге Ли скажет, какого голоса или звука ей недостаёт — записать сюда. Руслан пополняет корпус.)*"
      echo ""
      echo "---"
    } > "$DAUGHTER_FILE"

    echo "Рефлекс: создан daughter/journal/$YEAR/$MONTH/$DAY.md — «$POEM_TITLE» ($POEM_AUTHOR)" >&2
  fi
fi

exit 0
