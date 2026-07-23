# Аудит стыка devbot→Bridge-очередь (Стык 1)

> Шаг 1/7, родитель 216. Read-only, код не правился. Дата: 2026-07-19.

---

## Стык 1

### 1. Чем ДОКАЗАНА постановка задачи

**Нормальный путь (нет сбоя):**
Единственный источник доказательства — ответ Bridge `{ok:True, id:…}` на POST `enqueue_task`.
Verify-GET в этой ветке не вызывается вообще (`devbot.py:398`).

**Оборонительный путь сбоя (`_enqueue_reliable`, `devbot.py:388`—410):**

| Шаг | Что происходит | Доказательство |
|-----|----------------|----------------|
| 1 | POST `enqueue_task` → `{ok:True}` | id из ответа Bridge |
| 2 | POST → не-ok → `_find_enqueued`: GET `get_pending(status="new", lane="all")`, ищет item `from==frm AND task_text==text` (NFC, строка 381) | id из verify-GET |
| 3 | Verify нашёл → возвращает `{ok:True, id:qid}` (строка 404) | id из verify |
| 4 | Verify не нашёл → второй POST | id из второго ответа Bridge |
| 5 | Оба POST упали | `{ok:False}` → карточка «Не удалось» пользователю |

**Вывод:** постановка считается доказанной ответом Bridge. Verify-GET — страховка только для
потерянного ответа (ответ не дошёл, но запрос Bridge исполнил). Пользователю возвращается
id и карточка «✅ Задача N поставлена» — это функциональное подтверждение наличия записи в очереди.

---

### 2. Уязвимости verify-логики

**Уязвимость V1: race-verify-dup (вероятность: крайне низкая).**
Сценарий: первый enqueue дошёл до Bridge и записан; ответ потерялся; verify-GET выбрасывает
exception (сеть упала между первым POST и verify). `_find_enqueued` ловит `except Exception: return None`
(строка 383) и возвращает None → идёт второй retry POST → **дубль в очереди** (две задачи с одним from+text).
Демон возьмёт их по очереди (claim → in_progress по одному), обе выполнятся.

**Уязвимость V2: verify возвращает чужой id (вероятность: теоретическая).**
Если два сообщения с идентичным `from` + `task_text` оба одновременно сбоят на первом POST
и оба вызывают verify: оба видят запись друг друга в `new`. Разные from-метки (`QUEUE_FROM`,
`QUEUE_FROM_DEV` и т.д.) исключают это для разных типов задач, но два «задача: <одинаковый текст>»
теоретически могли бы перепутать id-шники. В практике Филипп — единственный отправитель,
тексты уникальны.

**Уязвимость V3: задача взята демоном между первым POST и verify.**
Verify читает только `status=new`. Если демон успел сделать `claim_task` до verify-GET
(новый цикл демона ~60с — маловероятно, но возможно при очень быстром цикле),
verify вернёт None → retry → дубль: одна задача уже `in_progress`, вторая новая в `new`.
Не покрывается текущей логикой.

---

### 3. Сценарий: обрыв сети / kill ровно на enqueue

Стек защиты (слои в порядке применения):

```
[1] echo-retry (_fetch_redirect_target, bridge_client.py:168)
    POST к /exec исполняется ОДНОКРАТНО.
    GET на Location (echo-слой googleusercontent) ретраится до retry_attempts (дефолт=3)
    на 404/5xx/timeout. БЕЗОПАСНО: Apps Script уже исполнил действие, GET только забирает ответ.

[2] auth-resend (_durable_request, bridge_client.py:268)
    Ответ = unauthorized → ровно 1 повтор (токен потерялся на редиректе?).
    ПОТЕНЦИАЛЬНО ОПАСНО для enqueue: если Bridge исполнил запрос ДО проверки токена
    (архитектура обещает token-first, но клиент это не верифицирует) → дубль enqueue.
    На практике нет инцидентов.

[3] _enqueue_reliable verify+retry (devbot.py:388)
    Один retry после verify. Описан выше.
```

**Конкретные сценарии:**

| Событие | Исход |
|---------|-------|
| Kill ДО POST достиг Bridge | Verify: пусто → retry → задача создана ✅ |
| Kill ПОСЛЕ исполнения POST, ДО ответа (echo-404) | Echo-ретрай (до 3×). Все упали → `_enqueue_reliable` → verify находит задачу → `{ok:True, id}` ✅ |
| Kill ровно на verify-GET (exception) | Verify → None → retry POST → **дубль** если первый дошёл ⚠️ |
| Kill процесса devbot в `_enqueue_reliable` (SIGKILL) | Все состояния потеряны. Telegram не получил ответ. При рестарте бот не помнит «мы были в enqueue». Если Telegram повторно доставит сообщение (timeout отправителя) → вторая постановка задачи — возможный дубль ⚠️ |
| Оба POST упали | Честная ошибка пользователю, задача не в очереди. ❌ (но честно) |

**Итог по enqueue:** архитектура устойчива к типичному «ответ потерялся» (инцидент 138).
Дыра — exception именно при verify-GET с успешным первым POST (три последовательных сбоя:
enqueue-ответ потерян + verify-GET упал + retry POST выполнился) → редкий дубль.

---

### 4. Сценарий: обрыв / kill ровно на report_results

`report_results` (`devbot.py:912`) — async-корутина, JobQueue каждые ~45с.
Все дедуп-сеты (`_reported`, `_asked`, `_inprogress_seen`, `_stalled`, `_report_seeded`) —
**in-memory, теряются при любом рестарте**.

**Seed-on-start** (строки 933—937): первый вызов после старта помечает ВСЕ текущие done/failed
как уже отрапортованные (не присылая карточки) — защита от спама историей при рестарте.

| Момент kill | Исход |
|-------------|-------|
| Kill ДО `_reported.add(qid)` (строка 946) | Restart → seed → задача попадает в seed → карточка в 328 **не отправлена** (тихая потеря уведомления) |
| Kill ПОСЛЕ `_reported.add(qid)`, ДО `send_message` | Та же картина: restart → seed → тихая потеря |
| `send_message` бросает exception (строка 965, catch) **без kill** | `qid` уже в `_reported`; exception поймана, retry нет; на следующем тике — skip. **Тихая потеря карточки** без рестарта |
| Kill после успешного `send_message` | Нет потери: 328 уже получил карточку ✅ |
| Kill во время seed-on-start (перед `_report_seeded = True`) | Restart → seed повторяется → задача снова в seed → потеря |

**Ключевой вывод по report_results:**

`_reported.add(qid)` (строка 946) стоит ПЕРЕД `send_message` (строка 961).
Это значит: после добавления в `_reported` любой сбой Telegram (transient network error, exception)
**не имеет retry-механизма** — карточка теряется. Данные задачи в Bridge целы (задача не удаляется),
но уведомление в Telegram 328 не доставлено и не будет повторено ни в текущем запуске (qid в set),
ни после рестарта (seed).

Seed-on-start — намеренный компромисс («не спамить историей»), но его следствие:
любая задача, завершившаяся пока devbot был недоступен, молча пропадает из 328.
Данные в Bridge сохранены; видимость потери — только в Telegram-теме.

---

### 5. Прочие наблюдения

**Нет таймаута на `_find_enqueued`:** вызов `bridge.get_pending("new", lane="all")`
через `_call()` (GET, `retry_full=True`, timeout 60с × 3 попытки = до 180с).
В синхронном контексте через `asyncio.to_thread(_try_enqueue, ...)` thread может зависнуть на ~3 мин.
Event loop не встанет (to_thread), но пользователь будет ждать ответа на сообщение.

**`_find_enqueued` читает lane="all":** корректно для verify pc-задач.

**`enqueue_task` → `_post()` → `retry_full=False`:** write-POST идёт один раз (echo-ретрай
внутри `_exchange` остаётся). Архитектурно правильно.

**FIXTURE_TASK_RE в `enqueue_task`** (`bridge_client.py:462`—469): тест-фикстуры блокируются
ДО сети — fail-safe, не зависит от состояния Bridge.

---

### 6. Итоговая таблица рисков

| # | Риск | Вектор | Серьёзность | Существующая защита |
|---|------|--------|-------------|---------------------|
| R1 | Дубль задачи при verify-exception | Три последовательных сбоя сети | Низкая (редко) | Нет |
| R2 | Дубль при SIGKILL в enqueue + Telegram retry | Kill + повторная доставка TG-сообщения | Низкая | NFC dedup текста при verify |
| R3 | Тихая потеря карточки 328 при Telegram exception | Transient Telegram error в `send_message` | **Средняя** (регулярна при Telegram нестабильности) | Нет (нет retry после add) |
| R4 | Потеря карточки при рестарте devbot | Любой kill/crash devbot | **Средняя** (seed-on-start намеренно) | Данные в Bridge целы; видимость потери только в TG |
| R5 | auth-resend дубль enqueue | Bridge исполняет ДО token-check | Теоретическая | Не проверяется |

Все данные задач в Bridge сохраняются вне зависимости от сценариев R3/R4 — потери данных нет,
потеря только Telegram-уведомления.

---

## Стык 2 — Очередь → Демон (orchestrator_daemon.py)

> Шаг 2/7, родитель 216. Read-only, код не правился. Дата: 2026-07-19.

---

### 1. Переход new→in_progress: чем доказан

**Нормальный путь:**
`_claim_task_verified(tid)` → `bc.claim_task(tid)` → Bridge возвращает `{ok:True, task:{…}}`.
Bridge заявляет атомарность (new→in_progress), клиент принимает ответ на веру. Повторного
read-back после успешного claim **нет**.

**Оборонительный путь (фикс инцидента 146, 08.07.2026):**
Claim вернул ошибку, но не семантическую (not_found/wrong_lane/no_id) → немедленный
verify-GET `get_pending("in_progress")`: задача там → claim долетел, демон считает её своей
и исполняет штатно (`{"ok": True, "verified": True}`). Логика доказательства владения:
«полоса vps однопоточна, claim делает только этот демон, значит in_progress-задача — наша».

| Исход claim | Доказательство |
|-------------|----------------|
| `{ok:True}` | Ответ Bridge (атомарный контракт) |
| Сбой + verify нашёл tid в in_progress | Verify-GET (одно-воркерная полоса) |
| Сбой + verify не нашёл / verify сбоит | Пропуск цикла, следующий poll попробует заново |
| Семантический отказ (not_found / wrong_lane) | Честный пропуск, claim не наш |

---

### 2. Переход in_progress→done/failed: чем доказан

`bc.complete_task(tid, status, result)` — **одна попытка** (`retry_full=False`, т.к. `"complete_task"` не в
`_IDEMPOTENT_POST_ACTIONS`). Внутри _post: echo-ретрай (до GET на redirect), auth-resend — но
только на транспортном уровне, без re-POST самого complete.

```python
cm = bc.complete_task(tid, status, result)
log.info("COMPLETE id=%s status=%s bridge_ok=%s", tid, status, cm.get("ok"))
```

Демон логирует `bridge_ok`, но **не ретраит при `ok:False`** и **не проверяет state post-factum**.
Если Bridge вернул ошибку:
- задача остаётся in_progress
- heartbeat мёртв (run_task уже вернулся)
- через ORPHAN_TTL (600с) реапер `process_orphans()` закрывает её как `failed` с ⏱-диагнозом

**Вывод:** завершение задачи доказано ответом Bridge «постфактум» — не live-фактом. Провал complete →
~10 мин задержки до честного failed через реапер.

---

### 3. Heartbeat: механика и гарантии

`_heartbeat_loop(task_id, stop_event)` — daemon-поток, стартует ДО `proc = _POPEN(...)`, останавливается в `finally` после `communicate()`. Бьёт `bc.task_heartbeat(task_id)` каждые `HEARTBEAT_SEC=45с`. Ошибки heartbeat молча **глушатся** (`.warning()` + continue) — он не валит задачу.

`process_orphans()` считает возраст задачи как `now - updated` по полю из Bridge. Пока heartbeat жив, `updated` обновляется каждые 45с → age < ORPHAN_TTL (600с) → реапер задачу не трогает.

**Симметрия порогов:** `TASK_TIMEOUT` = 600с = `ORPHAN_TTL`. Задача таймаутится не позднее 600с → через 600с после смерти heartbeat реапер её закрывает. Живая задача (выполняется в рамках TASK_TIMEOUT) всегда моложе ORPHAN_TTL → реапер никогда не убьёт живую.

---

### 4. Сценарии OOM / kill: что происходит

#### Сценарий A: OOM убивает только claude -p (демон выживает)

1. OOM killer выбирает жертву с наибольшим RSS — claude -p (гигабайтный LLM-процесс).
2. claude -p умирает SIGKILL (rc=-9 / 137).
3. `communicate()` возвращает немедленно с rc=-9.
4. `_planned_restart_verdict(-9, ...)`: rc not in `_SIGTERM_RCS=(143, -15)` → `None`.
5. `run_task` возвращает `("failed", _fail_card(out, err, -9))`.
6. Демон вызывает `complete_task(tid, "failed", ...)` → задача закрыта.

✅ **Не зависает, не врёт.** Задача получает честный failed с информацией об аварийной гибели.

#### Сценарий B: OOM убивает весь cgroup (демон + claude -p), SIGKILL

1. Демон получает SIGKILL — обработчик `_stop()` не вызывается, `_running` остаётся True.
2. Демон умирает прямо в `communicate()` — `complete_task` **не вызывается**.
3. Задача остаётся в in_progress, heartbeat мёртв.
4. systemd рестартит демон (Restart=on-failure в юните).
5. Первый цикл нового демона: `process_orphans()` → задача в in_progress, age=0 → ждёт.
6. Через ORPHAN_TTL (600с) от последнего heartbeat → честный failed с ⏱-диагнозом.

⚠️ **Задержка** до cleanup: ORPHAN_TTL + время старта демона = ~10–11 мин. Данных не теряется.

#### Сценарий C: SIGTERM (systemctl stop) во время выполнения

1. SIGTERM → `_stop()` → `_running = False`.
2. systemd одновременно отправляет SIGTERM всему cgroup → claude -p умирает exit=143.
3. `communicate()` возвращает с rc=143.
4. `_planned_restart_verdict(143, task_text, t0_mono)`:
   - `_running = False` (2-й признак выполнен)
   - Ищет systemd-run transient unit рестарта демона:
     - `systemctl stop` без systemd-run → unit не виден → None → честный failed
     - `systemd-run --on-active=Ns restart` → unit виден → время: unit старше claude-старта = "foreign" (requeue), иначе = "own" (done+🔁)
5. Демон вызывает `complete_task` (main loop ещё жив после `communicate()`).
6. Цикл `while _running` видит `False` → выходит; systemd ждёт не дольше KillTimeout.

✅ **complete_task успевает** если systemd не ставит SIGKILL немедленно. При KillTimeout=0 — сценарий как B (сирота до реапера).

#### Сценарий D: kill демона точечным SIGKILL (ручной kill -9)

Идентичен Сценарию B — `_running` не меняется, complete_task не вызывается, задача → сирота → реапер.

---

### 5. OOM-история и частота сирот (journalctl)

| Дата | Событие | Пик RSS |
|------|---------|---------|
| Jul 15 06:33 | OOM kill | 846 MB |
| Jul 16 04:58 | OOM kill | 1.4 GB |
| Jul 16 07:06 | SIGKILL (ручной?) | 380 MB |
| Jul 16 19:32 | OOM kill | 1.6 GB + 1.7 GB swap |
| Jul 16 21:49 | OOM kill | 1.6 GB + 1.7 GB swap |
| Jul 17 00:09 | OOM kill | 1.6 GB + 1.7 GB swap |
| Jul 18 18:42 | Чистый старт (текущий) | 460 MB (peak ~сутки) |

Итого: **5 OOM-kill за 7 дней** (Jul 12–19), все до/во время ввода гейтов памяти (16–17.07).
С вводом `MEM_MIN_MB=700`, `CLAUDE_RSS_TOTAL_MB=1200`, `MAX_CLAUDE_PROCS=2` (16–17.07) картина
стабилизировалась: последние ~30 часов демон работает без OOM (пик 460 MB).

**Оценка частоты сирот:** каждый OOM cgroup = потенциально 1 сирота (задача была in_progress в момент kill). 5 OOM → ≤5 сирот за 7 дней. Реапер закрывал каждую за ≤10 мин. В периоды без OOM — 0 сирот (нет данных о сиротах от сетевых сбоев за этот период).

---

### 6. Итоговая таблица рисков

| # | Риск | Вектор | Серьёзность | Существующая защита |
|---|------|--------|-------------|---------------------|
| R6 | in_progress-сирота при OOM всего cgroup | OOM kill демона в момент run_task | **Средняя** (5×/неделю до гейтов) | Реапер ORPHAN_TTL=600с → честный failed; гейты MEM/RSS/PROC снижают OOM-вероятность |
| R7 | complete_task без retry при сетевом сбое | Bridge недоступен ровно на complete | Низкая (echo-ретрай покрывает типичные) | Реапер через ORPHAN_TTL = fail-safe |
| R8 | Orphan при ручном SIGKILL | kill -9 демона | Низкая (ручная операция) | Реапер |
| R9 | Горячие gating-переменные (_mem_wait_until, _proc_deny_count) — in-memory | Рестарт демона сбрасывает cooldown | Ничтожная | Первый цикл после рестарта делает свежую проверку /proc/meminfo |
| R10 | complete_task не проверяется post-factum | Bridge вернул {ok:False} | Низкая | Реапер ORPHAN_TTL |

**Ключевое наблюдение:** все переходы состояния (claim, complete, needs_approval) — **оптимистичные**:
клиент принимает ответ Bridge на веру, без read-back. Страховка — реапер + ORPHAN_TTL.
Пока Bridge доступен и gRPC надёжен — система корректна. Транзиентный сбой complete →
задержка (10 мин) без потери данных. Данные в Bridge всегда целы; потеря только в задержке видимости.

---

## Стык 3 — Headless→Гейт→Push→Restart: решение done и точки лжи

> Шаг 3/7, родитель 216. Read-only, код не правился. Дата: 2026-07-19.

---

### 1. Как демон решает done: exit code против live-фактов

**Главный принцип:** `run_task` решает статус по `proc.returncode` после `communicate()`.

| Ветка | Критерий done | Live-факт проверяется? |
|-------|---------------|------------------------|
| Штатное исполнение (`exit=0`) | `returncode == 0` | **НЕТ** — только exit code |
| Таймаут | — всегда `failed` | Не применимо |
| `NEEDS_APPROVAL` | маркер в stdout | Нет (парс текста) |
| Guard-block | маркер-файл CC_TASK_ID | Нет (файловый маркер) |
| Плановый рестарт (`own`) | 5 признаков SIGTERM+юнит+время | `systemctl show` (live) |
| Чужой рестарт (`foreign`) | ранний monotonic-timestamp | `systemctl show` (live) |
| `op=git_push` | `git push` exit code | **ДА** — реальный git |
| `op=restart_splinter` | `systemctl is-active` == `"active"` | **ДА** — реальный systemctl |

**Вывод:** в штатной ветке (`exit=0`) демон проверяет исключительно exit code `claude -p`.
Выполнил ли `gate.py`, сделан ли `git commit/push`, жив ли `splinter` — всё это
**проверяет САМА задача (headless claude)** и сообщает в тексте ответа. Демон принимает
этот текст на веру и пишет его в `result`. Верификации содержимого нет.

Исключение — `AUTO_OPS` (`git_push`, `restart_splinter`): это хардкод-исполнители
approved-красных заявок, они вызывают реальные команды и проверяют live-факты.
Но они не имеют отношения к headless-задачам через `run_task`.

---

### 2. Gate, push, restart в headless-задачах: кто проверяет что

```
claude -p (headless, exit=0)
  └── сама выполняет:
       ├── venv/bin/python3 gate.py   → exit 0/1 (задача видит, может зааборить)
       ├── git commit / git push      → pre-push hook зовёт gate.py --final
       └── systemctl restart splinter → systemctl is-active (задача проверяет сама)
            ↓
  Пишет результат в stdout (первая строка ≤400 — сводка для 328)
            ↓
демон: stdout → result, exit=0 → done
```

**Контроль гейта внутри headless-задачи:**
- `child_env["GATE_ALERT_FINAL_ONLY"] = "1"` — промежуточные красные прогоны тихие.
- `child_env["GATE_STEP_SELECTIVE"] = "1"` — на промежуточных шагах цепи: только затронутые модули.
- pre-push hook (`deploy/hooks/pre-push`) вызывает `gate.py --final` — **реальный барьер**: gate.py при
  красных тестах роняет push → задача не может запушить при красных. Deny на `--no-verify` в
  settings.json блокирует обход.

**Что демон видит:** только то, что задача написала в stdout. Факт «gate зелёный» демон
**не верифицирует** — если задача написала «гейт зелёный, push выполнен», но не написала
commit hash, демон не знает, был ли push реально.

---

### 3. Ветка планового рестарта (done+🔁)

**Признаки (все 5 обязательны):**

| # | Признак | Проверка |
|---|---------|---------|
| 1 | `rc ∈ (143, -15)` (SIGTERM) | `_SIGTERM_RCS` |
| 2 | `_running == False` | глобальный флаг: SIGTERM → `_stop()` → `_running=False` |
| 3 | Самомод-текст в ТЗ | `_SELFMOD_RE` (regexp на «orchestrator_daemon» / «самомодификация») |
| 4 | Transient-юнит виден | `_restart_probe()` → `systemctl show run-*.service run-*.timer` |
| 5 | `earliest ≥ t0_mono` | monotonic-метка юнита **после** старта claude задачи |

**Результат:** `complete_task(tid, "done", "🔁 Завершено плановым рестартом... итоги в cc_log")`.

**Ключевое допущение:** демон говорит «работа сделана» — но это **допущение, не проверка**.
Обоснование: доктрина CLAUDE.md велит задаче записать в `cc_log` ДО рестарта. Если задача
это не сделала (отложенный рестарт сработал раньше 10с), `result` будет говорить «сделано»,
а в `cc_log` пусто. Commit hash демон не читает.

**Fail-safe:** любое сомнение → `None` → честный `failed`. SIGKILL/OOM не попадают в `_SIGTERM_RCS`.

---

### 4. Ветка чужого рестарта (done+🔄 → requeue)

**Критерий:** `earliest < t0_mono` — юнит создан **до** старта claude задачи.

**Логика:**
1. `run_task` возвращает `("requeue", ...)`.
2. `process_new` → `_requeue_foreign_restart(tid, frm, text, note)`:
   - Клон задачи в new (`frm` та же, текст дословно + `REPEAT_MARK [повтор задачи N]` в конце).
   - Исходная: `complete_task(tid, "done", "🔄 Задача взята в окно ЧУЖОГО планового рестарта...")`.
3. **Нет лжи о работе:** done тут = «возвращена в очередь»; работа не выполнялась — прямо указано.

**Fail-safe клона:** клон не встал в очередь → исходная → честный `failed` (не тихая потеря).

**Защитный слой 1 (process_new):** `_restart_pending()` — если единица ЖИВА (`active/activating`),
новые задачи НЕ берём. Клон клона невозможен: `REPEAT_MARK` в тексте → `_requeue_foreign_restart`
не дублирует маркер (guard `if REPEAT_MARK in text`).

---

### 5. Самопочинка: семантика «done исходной» ≠ «работа сделана»

**_maybe_task_selfheal (одиночная задача) и _maybe_selfheal (шаг декомпозера):**

```
задача failed (исполнительски)
    ↓
думатель (ORCH_MODEL, --max-turns 1) → retry | halt
    ↓
retry: enqueue_task(перерождение)       halt: complete_task(failed, диагноз)
       complete_task(tid, "done", "🩹…")
```

**«done» исходной задачи при retry = «перерождение инициировано»**, НЕ «работа сделана».
- В 328 приходит done-рапорт с «🩹 задача упала → думатель: retry, правка: X».
- Пользователь видит done, читает текст — всё понятно. Но автоматический парсинг result'а
  (если бы был) перепутал бы «done» с успехом.

**Терминальный halt:**
- Исходная: `complete_task(tid, "failed", "🛑 самопочинка не помогла...")` — честный failed.

**Второй провал (перерождение упало):**
- Детект: `_HEAL_RE`/`_HEAL_TASK_RE` в тексте задачи → `complete_task(failed, "🛑...")` → петля невозможна.

---

### 6. Точки лжи «done по отчёту, не по эффекту»

| # | Вектор | Вероятность | Защита |
|---|--------|-------------|--------|
| V1 | `claude -p exit=0` при тихом провале (задача написала «ок», но ничего не сделала) | Крайне низкая (честный LLM) | Нет технической проверки содержимого |
| V2 | Плановый рестарт (done+🔁): `cc_log` не успел записаться до рестарта | Редкая (10с обычно хватает) | Нет; зависит от дисциплины задачи |
| V3 | Плановый рестарт: `git push` не случился, но задача успела рестартовать до push | Редкая | pre-push hook; но задача могла ещё не дойти до push |
| V4 | Самопочинка retry: исходная `done`, но работа не сделана (есть в тексте «🩹») | Штатная, специально задизайнена | Текст явный; нет автопарсинга result'а в системе |
| V5 | Чужой рестарт → done+🔄: «работа не делалась» написано в result, но статус done | Штатная, специально задизайнена | Маркер «🔄» + «Возвращена в очередь»; клон в new |
| V6 | Gate bypass: задача пропустила `gate.py` — демон не знает | Низкая (deny `--no-verify`; pre-push гейт живой) | deny в settings блокирует `--no-verify`; pre-push hook обязателен |

**Практический риск:** V1, V6 — технически необнаруживаемы демоном. V2, V3 — зависят от
соблюдения задачей доктрины «отчёт до рестарта». V4, V5 — намеренная архитектура (семантика
done≠результат задокументирована в тексте result'а).

---

### 7. Что покрывают тесты и что нет

**test_planned_restart.py (6 блоков):**

| Сценарий | Покрыт? |
|---------|---------|
| Все 5 признаков → done+🔁 | ✅ |
| Каждый из 4-х первых признаков пропущен → failed (fail-safe) | ✅ |
| SIGKILL/OOM → failed | ✅ |
| Штатные пути не сломаны (exit=0, NEEDS_APPROVAL) | ✅ |
| e2e через process_new | ✅ |
| cc_log действительно обновлён до рестарта | ❌ НЕ покрыт |

**test_foreign_restart.py (8 блоков):**

| Сценарий | Покрыт? |
|---------|---------|
| `_restart_probe`: all states (live/dead/legacy/empty/exc) | ✅ |
| Чужой → requeue (обычная + самомод-ТЗ) | ✅ |
| Свой → done+🔁; обычное ТЗ без самомод → failed | ✅ |
| Времени нет → прежний путь (самомод→done+🔁, нет→failed) | ✅ |
| e2e: клон в new + исполнение после рестарта | ✅ |
| Пауза приёма: живой юнит → задача ждёт в new | ✅ |
| Мёртвый остов → приём НЕ заморожен | ✅ |
| Дек-шаг: клон сохраняет маркер [шаг i/N] | ✅ |
| Клон не встал → честный failed | ✅ |

**Непокрытые сценарии (оба read-only аудит, не баги):**
- Самопочинка в условиях чужого рестарта (думатель зовётся для перерождённой задачи, которую снова убивает чужой рестарт) — теоретически `_HEAL_RE` детектирует маркер и даёт терминальный halt.
- V1: `exit=0` с ложным отчётом — не тестируется по определению (верим claude).
- V2/V3: «done+🔁 без реального cc_log/push» — нет теста.

---

### 8. Итоговая таблица рисков

| # | Риск | Вектор | Серьёзность | Существующая защита |
|---|------|--------|-------------|---------------------|
| R11 | done без реального эффекта (exit=0, ложный отчёт) | Ненадёжный исполнитель | Ничтожная (честный LLM) | Нет технической |
| R12 | done+🔁 без cc_log/push (отчёт не успел) | Плановый рестарт раньше 10с | Редкая | Доктрина «отчёт до рестарта»; нет автовери |
| R13 | Gate bypass в headless (задача не вызвала gate.py) | Нарушение дисциплины исполнителя | Низкая | deny `--no-verify`; pre-push hook обязателен при push |
| R14 | Семантически misleading done при самопочинке | retry-путь | Дизайн-артефакт | Явный текст «🩹»; нет авто-потребителей result |
| R15 | Клон чужого рестарта взят в другой чужой рестарт (race) | Серия быстрых рестартов демона | Ничтожная | Пауза приёма (слой 1) + REPEAT_MARK guard |

---

## Мозг — Пути записи в cc_log и pulse

> Шаг 4/7, родитель 216. Read-only, код не правился. Дата: 2026-07-19.

---

### 1. Канонический путь — cclog.py (с length-guard)

Единственный модуль с guard'ом — `cclog.py`. Два входа:

#### A. `write_cclog()` — программный API (cclog.py:142)

```
read_doc(name="cc_log")
  → _insert_under_vrezka(old, entry)
  → len(new) < len(old) → _alert_shrink + return False  ← GUARD
  → write_doc(text=new, name="cc_log")
  → [если pulse] write_doc(text=pulse_str, name="pulse")  ← прямой, без guard (правильно: перезапись)
```

Защита: при read FAIL → пишем НЕ. При shrink → блок + алерт. Возвращает `bool`.

**Где вызывается:** только в `tests/test_cclog_guard.py` (тест-сьют). Продакшн-код прямо `write_cclog()` **не импортирует** (grep: единственный `from cclog import write_cclog` — только в тестах).

#### B. `main()` — CLI-путь (cclog.py:175)

```
venv/bin/python3 cclog.py [KIND] "текст" [--pulse "строка"]
  → read_doc(name="cc_log")
  → _insert_under_vrezka
  → len(new) < len(old) → _alert_shrink + exit 1  ← GUARD
  → write_doc(text=new, name="cc_log")
  → [--pulse] write_doc(text=pulse, name="pulse")  ← прямой
```

**Где вызывается:**
- Headless-задачи (через `APPROVAL_PREAMBLE`, `orchestrator_daemon.py:566–568`): `venv/bin/python3 cclog.py PLAN/DONE/BLOCKED «текст» [--pulse …]`
- Живые Termux-сессии: алиас `cclog` / `logdone`

Это **главный рабочий путь** — покрывает весь headless и весь интерактив.

---

### 2. Активный продакшн-код — в cc_log/pulse НЕ пишет напрямую

| Файл | write_doc(name="cc_log") | write_doc(name="pulse") |
|------|--------------------------|-------------------------|
| `devbot.py` | — | — (только read_doc:1505) |
| `orchestrator_daemon.py` | — | — |
| `splinter.py` | — | — |
| `bot.py` | — | — |
| `health.py` | — | — |
| `_pcport185/pc_agent.py` | — (пишет в `cowork_log`:714) | — |
| `_pcport185/cowork_log_append.py` | — (пишет в `cowork_log`:62) | — |

**Вывод:** ни один файл ядра бота не пишет в cc_log или pulse мимо cclog.py. Риска затирки из продакшн-кода нет.

---

### 3. Scratchpad `_*.py` — мимо guard'а (⚠️)

~80+ исторических скриптов в корне репо прямо вызывают `bridge.write_doc(text=new, name="cc_log")` без length-guard. Все обнаруженные:

| Скрипт | Паттерн | Риск |
|--------|---------|------|
| `_cclog_step5_restart.py:36` | прямой write_doc | shrink при пустом read |
| `_capssync_check_cclog.py:45` | прямой write_doc | shrink при пустом read |
| `_caps45_cclog_plan.py:44` | прямой write_doc | shrink при пустом read |
| `_s4_cclog_done.py:41` | прямой write_doc | shrink при пустом read |
| `_dec_cclog_done.py:51` | прямой write_doc | shrink при пустом read |
| `_pcdev829_prune_cclog.py:60` | прямой write_doc | **НАМЕРЕННЫЙ** ukrót (prune-скрипт) |
| `_s4_cclog_trim.py:66` | прямой write_doc | **НАМЕРЕННЫЙ** ukrót (trim-скрипт) |
| … ещё ~70 аналогичных | прямой write_doc | shrink при пустом read |

**Типичный unsafe-паттерн:**
```python
r = c._call("read_doc", name="cc_log")
old = r.get("text", "")  # при read fail → "" → new < old → затирка
new = header + entry + old
w = c.write_doc(text=new, name="cc_log")  # ← без guard
```

**Ключевые наблюдения:**
- Все `_*.py` — одноразовые scratchpad-скрипты; **автоматически не вызываются** (нет ни одного `import _*` в продакшн-коде, нет cron).
- Два из них — намеренные trim/prune (`_pcdev829_prune_cclog.py`, `_s4_cclog_trim.py`) — shrink закономерен.
- Инцидент 17.07.2026 (`_log_test1.py`, `_test1_cclog.py`, `_write_cclog_checkx.py`) вызвал именно этот класс бага — guard был введён в cclog.py ПОСЛЕ.
- После guard'а (инцидент 17.07): scratchpad-скрипты не обновлялись, остались unsafe.

---

### 4. Pulse — guard не нужен (правильно)

`KB_PULSE` — **перезапись одной строки** (не накопление). Shrink ожидаем и штатен. Guard был бы ложным срабатыванием. Pulse всегда пишется прямым `write_doc(name="pulse")` — это корректная архитектура.

Отдельного log-уровня для pulse нет: write_doc — `{ok:True/False}`, ошибка логируется в stdout cclog.py и игнорируется (не блокирует cc_log-запись).

---

### 5. Итоговая карта путей

```
Headless claude -p (APPROVAL_PREAMBLE)
    └─► venv/bin/python3 cclog.py  ──► write_cclog/main() [GUARD ✅]
Живой Termux / cclog-алиас
    └─► venv/bin/python3 cclog.py  ──► main() [GUARD ✅]
Продакшн-бот (devbot/splinter/orchestrator)
    └─► НЕ пишет в cc_log напрямую [нет риска ✅]
_*.py scratchpad (одноразовые)
    └─► прямой write_doc(name="cc_log") [БЕЗ GUARD ⚠️]
          ├── trim/prune скрипты: shrink намеренный
          └── остальные ~78: shrink возможен при пустом read
```

---

### 6. Итоговая таблица рисков

| # | Риск | Вектор | Серьёзность | Существующая защита |
|---|------|--------|-------------|---------------------|
| R16 | Затирка cc_log scratchpad-скриптом при пустом read | Ручной запуск `_*.py` в репо | Низкая (скрипты не авто; инцидент уже был 17.07) | cclog.py guard НЕ покрывает `_*.py`; нет технического барьера |
| R17 | Потеря записи при shrink-block (guard сработал, cc_log не обновлён) | Аномалия _insert_under_vrezka (баг в логике препенда) | Ничтожная | _alert_shrink шлёт алерт в 328; запись блокируется, не теряется |
| R18 | Потеря пульса при write FAIL | Bridge недоступен ровно на write_doc(name="pulse") | Низкая (транзиентно) | Следующий cclog-вызов перезапишет пульс; пульс не критичен |
| R19 | write_cclog_and_pulse несуществующая функция | `_cclog_2478_recon.py:3` импортирует её из cclog | Ничтожная (scratchpad не вызывается) | Импорт упадёт NameError при запуске; файл inactive |
