# Реестр мозга (BRAIN_MANIFEST) — СНИМОК ДО ПРАВКИ, 2026-07-30

**Зачем файл:** это ОТКАТ. Снят живым чтением `list_brain` через прод-Bridge непосредственно
перед правкой реестра (цель: снять мёртвый `roadmap_master`, добавить два живых booking-спека).
Реестр живёт в Script Properties проекта «TurboBaby Bridge» под ключом `BRAIN_MANIFEST`
(JSON имя→id). В git его нет — поэтому снимок здесь.

## Состояние ДО: 27 ключей = 26 доков + служебный `folder_id`

| # | ключ | id |
|---|------|----|
| — | folder_id | `1uWqHsxk7aEWoSNqaUBMmqkYOh2UKYLkY` |
| 1 | cc_log | `1464zaINaLnOwXMsHNaEyy-4FpuQCVTYF` |
| 2 | cc_log_archive | `1haE-9OFgs1-ZeH-fV1g1mIxxM3L_BLYq` |
| 3 | cc_userbot_log | `1yqzVrSFRN-1Zr3y6kprn71c-T-1xTl1qfO1BzA-Rihg` |
| 4 | cowork_log | `1s9Fy3xm4FB99ah9xovLjYIMOjnDKz3Jc` |
| 5 | cowork_log_archive | `1UC-fKIpjb2zwzrvCsbJjBxmgglmSlj46` |
| 6 | cowork_log_test | `1zGPT5DqNdUT8FOrOxsVI8-mI7sZjz3kU` |
| 7 | cowork_log_test_archive | `1HvhvlxKFPiHUYlMp41yQL0-50q4Dv_zq` |
| 8 | executors_map | `1NyfcErxNt09CH8JB-V0in9e-UQB-K4_uJrwZ-FG3Za8` |
| 9 | faq | `1tv8Y-K3gLyT9Y0mXyYXZLf2c2rEzPMLHPzvg4lGqs98` |
| 10 | index | `1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc` |
| 11 | infra | `1z2wS0I0nm-dJGqF3RRpOXlEkTKwLOsuF` |
| 12 | knowledge_base | `1Mv_zi1P33jNM0MFUBX_UEf9CnzOvCFeZ` |
| 13 | orchestrator_plan | `1_ogUGFim24Ifw60mSsfcONFc8hXMPzw539oXTbhGggo` |
| 14 | orchestrator_safety | `1UB1MWs8ZQWDkwHYBqNgK7UyVD4dkPKYdEVYo3IM2-Zs` |
| 15 | park_list | `1jD3VJGeoET8Yf5ma6iZPmwwmuw_yIYyP2A4N5RAEZho` |
| 16 | payments_plan | `13WtxQaDLdixR4EsjUFimtNhESn9nFDtk` |
| 17 | project_state | `1fuptOFp2bqZva7eJRlEanaCO6eRkAO20` |
| 18 | pulse | `1v3ezYbEeI1kGNQFI6xi8mDhnM9uE3YSE` |
| 19 | review | `1vDfD_n8i-8cSvJmqqvvEaLZ1YC639-in` |
| 20 | review_archive | `1K0gPMOyM-ER7nweda8-f9MK3edbepYCniZpQy0HkpAA` |
| 21 | **roadmap_master** | `1Z70EpgGZmaYMaZ064sXQlCCP8z8sFyZWfzVPvRB4jWE` ← **МЁРТВЫЙ** |
| 22 | rules | `1AnBAniKQtrpJQevVWlzxVrdb1n51aj1G` |
| 23 | sessions_log | `1gNFRnHv09SKeagkGA3moG0VNlzffECeh` |
| 24 | sessions_log_archive | `1D-iq-Rp1g_RC9uYzqsjPJtmw6TY0l6cV` |
| 25 | state_model | `1OGUzeb60UbzAaCOsLNR_aBKFy-blfdn-` |
| 26 | turbobaby_faq | `1tv8Y-K3gLyT9Y0mXyYXZLf2c2rEzPMLHPzvg4lGqs98` (тот же файл, что `faq` — второе имя для userbot) |

## Живые пробы, снятые в тот же заход (доказательство, а не пересказ)

    roadmap_master  1Z70Epg…  → read_doc ok=False error=read_failed
                                («no element with the given ID» — файл вычищен из корзины Drive)
    KB_booking_flow 11HvMKG…  → read_doc ok=True  chars=6501
    KB_collect_booking_spec
                    1PZ7Te…   → read_doc ok=True  chars=4553

## Что меняли и ЧЕМ КОНЧИЛОСЬ (заход 30.07, ~08:45 UTC)

| действие | ключ | id | итог |
|---|---|---|---|
| добавить | `booking_flow` | `11HvMKG…6DQU` | ❌ Bridge отбил: `not_in_brain` (title=KB_booking_flow) |
| добавить | `collect_booking_spec` | `1PZ7Te…MW48` | ❌ Bridge отбил: `not_in_brain` (title=KB_collect_booking_spec) |
| снять | `roadmap_master` | `1Z70Epg…` | ❌ **НЕЧЕМ** — см. ниже |

**Реестр НЕ изменился** (сверка list_brain после попыток = таблица ДО, байт-в-байт по ключам/id).

Разбор `not_in_brain`: сам эндпоинт `register_brain_doc` в прод-деплое ЖИВОЙ (проба пустыми
аргументами → `need_name_id`; прежняя запись в project_state «требует clasp redeploy» была неверна).
Отказ — от собственной защиты `registerBrainDoc_`: файл обязан лежать ПРЯМО в папке «TurboBaby
Brain» (`folder_id` манифеста), а оба спека лежат вне её (созданы вне Brain, вероятно PC-сессией).
Эндпоинта «перенести файл В Brain» у моста нет (`move_brain_file` двигает только то, что УЖЕ в
Brain, в подпапки). → **Нужен ручной перенос владельцем**: в Drive перетащить `KB_booking_flow` и
`KB_collect_booking_spec` в папку «TurboBaby Brain» (корень, не _archive) — после этого регистрация
проходит с сервера штатно, без деплоя.

## Почему `roadmap_master` не снимается автоматически

У Bridge **нет** действия удаления ключа реестра. Проверено по всему проекту: `BRAIN_MANIFEST`
пишут только `setupBrain` / `setupCcLog` / `setupReview` / `setupCcUserbotLog` /
`registerBrainDoc_` / `createBrainPlain_` / `migrateJournalToPlain_` / архивные хелперы
(`Archive.js`) — **все они ключи ТОЛЬКО добавляют или переставляют id**, ни один не делает
`delete manifest[key]`. `setupBrain` тоже не спасает: он читает текущий манифест и мержит в него
свои 4 ключа, а не пересобирает с нуля — `roadmap_master` переживёт его запуск.

Значит удаление требует одного из двух, и оба — рука владельца:

1. **Проще (без кода и без деплоя):** редактор Apps Script проекта «TurboBaby Bridge» →
   ⚙ Project Settings → Script Properties → свойство `BRAIN_MANIFEST` → удалить из JSON пару
   `"roadmap_master": "1Z70EpgGZmaYMaZ064sXQlCCP8z8sFyZWfzVPvRB4jWE",` → Save.
2. Либо новый эндпоинт `unregister_brain_doc` в `ReadDocs.js` + `clasp push` + `clasp redeploy`
   прод-деплоя — это красная зона (деплой Apps Script) и отдельная задача.

## ОТКАТ

- **Снять лишний ключ** (если регистрация двух спеков окажется нежелательной) — тем же ручным
  способом (1): убрать пару `"booking_flow": …` / `"collect_booking_spec": …` из `BRAIN_MANIFEST`.
- **Вернуть `roadmap_master`**, если его снимут ошибочно: ключ указывает на **удалённый** файл,
  восстановить сам док нельзя (корзина Drive очищена, 30 дней с 27.06 вышли). Вернуть можно только
  саму пару ключ→id вручную в `BRAIN_MANIFEST` — смысла в этом нет, ключ мёртв.
- **Полный откат реестра к состоянию ДО** — таблица выше: она и есть эталон, сверять
  `list_brain` по ней.
