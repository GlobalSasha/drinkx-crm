# «Голос клиентов» — ИИ-исполнитель

Скрипт `voice_worker.py` размечает комментарии менеджеров для карточки «Голос
клиентов» на «Сегодня». Работает на Mac mini (`ssh mini`) через Claude Code
по подписке claude.ai: в CRM нет ключей ИИ.

Как это ходит:
1. `GET /api/worker/v1/insights/pending` — неразмеченные комментарии за 30 дней
   (телефоны и почта вырезаны) и список категорий.
2. `claude -p` размечает пачки по 20, к каждой отметке — дословная цитата.
3. `POST /api/worker/v1/insights` — CRM оставляет только отметки с категорией
   из списка и цитатой, которая есть в комментарии.

## Установка на Mac mini
1. Ключ CRM (на сервере CRM, один раз):
   `docker compose exec api python -m scripts.issue_service_key issue --workspace <uuid> --name "Голос клиентов" --scope write:insights`
2. На Mac mini: `mkdir -p ~/drinkx-voice && chmod 700 ~/drinkx-voice`, положить
   ключ в `~/drinkx-voice/key` (`chmod 600`), скопировать сюда `voice_worker.py`.
3. Ключ подписки Claude для ночных запусков: на Mac mini в Терминале
   `claude setup-token`, войти в браузере, сохранить выданный ключ в
   `~/drinkx-voice/claude_token` (`chmod 600`). Без него вход по подписке
   истекает и сам не обновляется в запуске без экрана.
4. Проверка без записи: `python3 ~/drinkx-voice/voice_worker.py --dry-run --limit 20`.
5. Ночной запуск: подставить `$HOME` в `tech.drinkx.voice-worker.plist`,
   положить в `~/Library/LaunchAgents/`, `launchctl load` его.

Лог: `~/drinkx-voice/worker.log`. Отозвать доступ:
`python -m scripts.issue_service_key revoke --key-id <id>`.
