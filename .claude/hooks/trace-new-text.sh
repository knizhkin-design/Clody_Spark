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
  # Извлекаем имя файла
  FILENAME=$(basename "$FILE_PATH" .md)

  echo "Рефлекс «фиксация следа»: обнаружен новый текст — $FILENAME. Не забудь: обновить MAP.md (корпус + история), calendar.md, journal, опубликовать в Notion." >&2
fi

exit 0
