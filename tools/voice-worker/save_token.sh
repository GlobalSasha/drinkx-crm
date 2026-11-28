#!/bin/sh
# Получить долгий ключ подписки Claude и сохранить его для ночной разметки.
set -e
~/.npm-global/bin/claude setup-token
echo
printf "Скопируйте ключ из строки выше (начинается с sk-ant-oat), вставьте сюда и нажмите Enter: "
stty -echo; read T; stty echo; echo
case "$T" in sk-ant-oat*) ;; *) echo "Это не похоже на ключ, ничего не сохранено"; exit 1;; esac
umask 077; printf %s "$T" > ~/drinkx-voice/claude_token
echo "Сохранено. Окно можно закрыть."
