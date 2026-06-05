# TurboBaby — контекст для Claude Code

## Что это
Splinter — Telegram-бот учёта для аренды мотобайков (TurboBaby, Пхукет, владелец Филипп, 38 байков). Работает на этом сервере 24/7 как systemd-сервис `splinter`.

## Главные правила работы с этим проектом
- Перед любой правкой кода — показывай дифф и жди моего подтверждения.
- НИКОГДА не коммить и не пушить секреты: .env, memory.db, *.session. Они в .gitignore.
- После правки кода: предложи закоммитить в git, и напомни перезапустить сервис: `systemctl restart splinter`.
- Логи бота: /root/turbobaby-manager-bot/splinter.log
- Проверить статус: `systemctl status splinter`

## Бизнес-правила (НЕ нарушать в коде)
- Никаких массовых рассылок клиентам.
- Изменения в Google Sheets — только через approve-флоу.
- HONDA CLICK 125 не сдаём.
- Депозит = либо деньги, либо паспорт (не оба).
- Доставка только по Пхукету.
- Тайская команда (Пым) с клиентами не общается.

## Архитектура
- bot.py — точка входа, роутер, планировщики.
- splinter.py — супервайзер групп, vision.
- claude_client.py — «мозг», эскалация, инструменты.
- bridge_client.py — HTTP-клиент к Apps Script Bridge (Google Sheets).
- auditor.py — надзор (факты + язык RU/TH).
- memory.py — SQLite memory.db (правила/история).
- prompts.py — системные промпты.

## Apps Script Bridge — какой проект «правильный»
Bridge — это Google Apps Script. Проектов несколько, легко перепутать. Признаки ВЕРНОГО:
- проект называется **«TurboBaby Bridge»**;
- его deployment обслуживает **BRIDGE_URL** (из .env); надёжнее всего — сверить deployment ID из BRIDGE_URL с Deploy→Manage deployments;
- его `ReadDocs.gs` содержит **И `setupCcLog`, И `setupReview`** (+ `setupBrain`, `handleReadDoc_`, `handleListBrain_`);
- файлы проекта: `Config/Bridge/BotData/ReadFleet/ReadClients/ReadFinance/ReadDocs/Booking.gs`.
Локальные `bridge_client.py` / `ReadDocs.gs` в репо — зеркало именно этого проекта.
Setup-функции (`setupBrain`/`setupCcLog`/`setupReview`) запускаются ВРУЧНУЮ из редактора —
строго в этом проекте, иначе ключ уйдёт в манифест чужого проекта (Script Properties у каждого свои).
Проверка после запуска: `list_brain` через Bridge должен показать новый ключ рядом с `cc_log`.

## Каналы «мозга» (Brain на Drive)
- `cc_log` (KB_claude_code_log) — журнал задач Claude Code: PLAN/DONE/NOTE, новые записи СВЕРХУ.
- `review` (KB_claude_review) — канал ревью Claude Code ↔ Claude на сайте (см. memory: review-policy).
