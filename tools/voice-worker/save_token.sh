#!/bin/sh
# Получить долгий ключ подписки Claude и сохранить его для ночной разметки.
# Ключ на экране показывается точками, поэтому вывод записывается во
# временный файл, ключ достаётся из него, а файл сразу удаляется.
set -e
umask 077
LOG=$(mktemp ~/drinkx-voice/.setup.XXXXXX)
trap "rm -f \"$LOG\"" EXIT
script -q "$LOG" ~/.npm-global/bin/claude setup-token
T=$(sed "s/\x1b\[[0-9;?]*[A-Za-z]//g" "$LOG" | tr -d "\r" | grep -o "sk-ant-oat[A-Za-z0-9_-]*" | tail -1)
# Экран рисуется с переходами курсора: после их удаления к ключу
# приклеивается следующее слово («Store this token…»).
T=${T%Store}
if [ -z "$T" ]; then echo; echo "Ключ не найден в выводе, ничего не сохранено"; exit 1; fi
printf %s "$T" > ~/drinkx-voice/claude_token
echo; echo "Ключ сохранён. Окно можно закрыть."
