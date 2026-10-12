# -*- coding: utf-8 -*-
"""«Отправить» с подписанным PDF договора — две части, у каждой свой исход (WAPARTSEND0410, Т4б-1).
Флаг WA_AGENT_ATTACH, по умолчанию выкл: служба собирает прежний `wa_agent.Core`, поведение 24ad256 байт-в-байт.

ЧТО ЭТО. Подготовка в отдельной копии; встроит интегратор. Ядро (`wa_agent.py`) и инструменты Т4а (`wa_agent_tools.py`)
не правятся: `AttachCore` — наследник `Core`, каждое его переопределение при выключенном флаге отдаёт управление
родителю, а своих таблиц не заводит.

ОТКУДА ВЛОЖЕНИЕ. Только из сверки Т4а этого же черновика (`ModelAdapter.last["tools"]`): `attach_of` берёт PDF, если
сверка ОДНОЗНАЧНО приняла подписанный договор ЭТОЙ аренды — ровно один подписанный договор (`contract` = fact), PDF
этого договора сверен клиентом моста (`contract_pdf` = fact, id = pdf_id договора, sha256 и размер есть) и аренда из
листа (`rental` = fact) на тот же байк — либо, когда модель `rental` не звала, аренда, к которой договор привязал сам код
(K3-FIX шаг 3q, `attach_of`). Иначе вложения нет, и черновик хранит ПРИЧИНУ словами. В базе — только
метаданные (id, имя, размер, sha256, строка реестра); байты PDF берутся из `contract_pdf` в момент отправки.

ОСНОВАНИЕ — ОПОРА СУДЬИ (T4B3BASIS0510, Т4б-3). Факты берутся не из сырых `results`, а после `wa_agent_tools.sift` с
`since` = последнее входящее клиента (`ModelAdapter.last["info"]["last_in"]`) — та же опора, на которой стоит judge:
поздний отказ того же запроса и чтение раньше последнего входящего основание снимают. В `attach` — версия договора
(`signed_at`, без неё вложения нет) и ключ перечитывания: номер обращения и срок аренды.

ПЕРЕЧИТЫВАНИЕ ПЕРЕД ОТПРАВКОЙ. Дверь `contract_find` — параметром, как `pdf_fetch`. «Отправить» черновика с PDF
перечитывает реестр ДО текстовой части, «Дослать PDF» — ДО PDF. Пропуск (`recheck_of`) — только `one`, пустой `unread`,
`undated_signed` = 0, подписанный `pick` и совпавшие row, doc_id, pdf_id и signed_at. Иначе (отзыв, новая версия,
второй подписанный, неполный ответ, дверь упала или ответ не разобран): «Отправить» — черновик stale с причиной,
ничего не отправлено, пересборка со сверкой (как W_NO_CHECK); «Дослать» — отказ с причиной, PDF не уходит.

ДВЕ ЧАСТИ. Текст — прежний черновик (`drafts.state`). PDF — строка `pdf_parts`: wait (ждёт текста) → claimed (захват,
байты сверяются) → sending (ДО двери) → sent · not_sent · unsure. PDF зовётся ТОЛЬКО после sent текста; текст не ушёл
или неизвестен — дверь PDF не звали, файл без текста не уходит. sha256 байтов при отправке не равен sha256 сверки —
PDF not_sent с причиной. Повтора нет: unsure двери и рестарт посреди части — «неизвестно».

«ДОСЛАТЬ PDF». Текст sent, PDF not_sent — захват сравнением-и-записью с ОЖИДАЕМЫМ номером попытки (кнопка несёт
его; устаревший номер и второе нажатие — «уже решено»). PDF «неизвестно» — сначала статусы провайдера.

ПРАВДА О ДОСТАВКЕ (WAPARTFIX0410). Подтверждает PDF только статус с wamid ЭТОЙ попытки (`delivery_check`): delivered
или read — доставлен; sent — «принято WhatsApp», это ещё не доставка; у попытки нет wamid — исход остаётся
«неизвестно», чужим статусом он не подтверждается никогда. Статус неизвестного нам сообщения после попытки
(`_foreign_after`) — не подтверждение, а улика возможного дубля: PDF «неизвестно», дослать кнопкой нельзя. Чужих
статусов нет — дослать только отдельным явным разрешением повтора, со словами о риске дубля; статусы не прочитаны —
дослать нельзя. ПРЕДЕЛ: попытка «неизвестно» wamid не получает никогда (дверь не назвала id сообщения) — без wamid
подтверждения нет, доставленной система её не назовёт; решает человек.

«ПЕРЕСОБРАТЬ СО СВЕРКОЙ». Ждущий черновик superseded тем же захватом (state+ver), новый проход Т4а даёт новый черновик
со своей карточкой. При флаге вкл. черновик без сверки (нет строки `attach`) не уходит: «Отправить» снимает его stale.

ПОЯСНЕНИЕ ПРИ СВЕРКЕ (Д2 INTEG0710, «PDF выключает обучение»; выключатель пояснений — WA_AGENT_HINTS ядра). До Д2 (A15)
пояснение при флаге отклонялось словами, и обучение при PDF было выключено. Теперь версия по пояснению проходит ТУ ЖЕ сверку,
что версия модели, и в такте, а не в обработчике нажатия: такт ядра (`make_hint_versions`) зовёт `redraft`, обёртка `_Probe`
ведёт его путём сверки Т4а (`ModelAdapter.redraft_checked` → `_draft_tools` с блоком пояснения) и запоминает итог по ключу
версии; до карточки версии (`_card_new`) итог ложится строкой `attach` с номером этой версии (`attach.ver`) — тем же
`attach_of` и той же проверкой двойника, что у версии 1. Карточка версии по пояснению всегда называет итог ЕЁ сверки
(`card_pdf`): PDF уйдёт вторым сообщением · PDF не приложен и почему · сверки нет. «Отправить» на версии, чья сверка записана,
— путь ядра Б2 (владелец по id — правило, сотрудник — кандидат) и две части; сверки этой версии нет — тот же замок «без
сверки» (stale, правила нет). Модель сверку не умеет (`_Probe.hint_check`: нет дверей `tools` или пути `redraft_checked`) или
пояснения выключены — пояснение не принимается словами сразу, модель не зовётся (как до Д2).

ЖУРНАЛ. `part_log` и строки `self.log`: кто, когда, часть, попытка, исход, wamid, sha256 — без текстов и номеров.

В СЛУЖБЕ (NIGHT0710-B3v). Собирает `wa_agent_svc.build` — только при флаге (правило `flag_on` службы, одно на всех) И
сверке Т4а (двери `contract_pdf`/`contract` берутся из `model.tools`, второго клиента моста нет). Руки Telegram: кнопки
«Дослать PDF» / «— риск дубля» приходят из `card_buttons` на исход карточки, нажатия идут в `press`.
АТОМАРНОСТЬ. Исход части, строка outbox и строка журнала части пишутся ОДНОЙ транзакцией (`BEGIN IMMEDIATE`) после
ответа двери: обрыв посреди — не легло ничего, часть осталась sending → старт скажет «неизвестно», повтора нет.
РЕСТАРТ МЕЖДУ ЧАСТЯМИ. Старт кладёт исход обеих частей на карточку (правка — первым тактом, очередь `card_out`) с кнопкой
«Дослать PDF»: PDF не теряется и без человека не уходит.
ПОЗДНИЕ СТАТУСЫ. `part_status` хранит каждый статус (sent · delivered · read · failed) по ТОЧНОМУ wamid части — текста или
попытки PDF — из очереди и из таблицы квитанций вебхука `wa_status` (там на wamid живут все статусы, в `wa_inbox` — только
первый). Чужой wamid части не подтверждает никогда.
"""

import base64
import hashlib
import re
import zlib

import wa_agent as A
import wa_agent_tools as T

F_ATTACH = "WA_AGENT_ATTACH"

ACT_REBUILD = "rebuild"           # «Пересобрать со сверкой»
ACT_PDF = "pdf"                   # «Дослать PDF»
ACT_PDF_RISK = "pdf_risk"         # «Дослать PDF — риск дубля»: отдельное явное разрешение повтора при «неизвестно»

P_WAIT, P_CLAIMED = "wait", "claimed"
PDF_MIME = "application/pdf"
STATUS_DELIVERED = ("delivered", "read")       # доставка — только эти статусы
STATUS_ACCEPTED = "sent"                       # «принято WhatsApp» — у WhatsApp, но клиенту ещё не доставлено
STATUS_ANY = (STATUS_ACCEPTED,) + STATUS_DELIVERED
STATUS_SKEW = 120                              # часы провайдера и наши: статус раньше попытки на столько — ещё её
STATUS_FAILED = "failed"                       # провайдер не доставил — хранится, доставкой не считается
STATUS_KEEP = STATUS_ANY + (STATUS_FAILED,)    # что `part_status` хранит по точной части
STATUS_EVERY = 60                              # такт сбора статусов частей — не чаще, с
STATUS_DAYS = 7                                # статусы собираются для частей не старше, суток
D_DELIVERED, D_ACCEPTED, D_UNKNOWN = "delivered", "accepted", "unknown"
D_FAILED = "failed"
TRUE_WORDS = ("1", "true", "yes", "on")        # то же правило, что `wa_agent_tg.flag_on` у всех выключателей службы
W_DOOR_OFF = "отправка выключена (WA_SEND) — PDF не ушёл, кнопка жива"
W_RESTART = "рестарт службы"
# второй круг (NIGHT0710-B3v): поломки красной команды R03, R10d, R17 и замечание R01/R02
W_TWIN = "этот договор (тот же PDF, sha256 %s…) этому клиенту уже уходил — черновик %d, PDF: %s; второй копии не шлём"
W_PAUSED = ("дослать нельзя: клиент на паузе — беседу ведёт человек с телефона; PDF не ушёл, кнопка жива "
            "(снимите паузу или отправьте файл сами)")
W_FAILED = "провайдер не доставил PDF (статус failed по wamid попытки %d) — можно дослать кнопкой"
W_PROVIDER = "статус провайдера"
W_NO_ATTACH_QUIET = ("сверки не было", "договор не сверялся")   # причины без договора — карточку ими не шумим

W_NO_CHECK = ("устарело: черновик без сверки — при WA_AGENT_ATTACH не уходит; ничего не отправлено, "
              "черновик пересобирается")
W_HINT_NO_CHECK = ("не принято: при сверке вложений (WA_AGENT_ATTACH) версия по пояснению сверку не проходит — "
                   "поправьте полным текстом реплаем на карточку")
# Д2 (INTEG0710): версия по пояснению — со сверкой Т4а, итог ЕЁ сверки на карточке
HINT_SEEN = "hint"                # ключ итога сверки версии по пояснению в `_seen`: (HINT_SEEN, номер, upto)
W_HINT_CHECK = "🔎 сверка Т4а версии %d по пояснению — та же, что у версии модели: %s"
W_HINT_CHECK_PDF = "«Отправить» шлёт ВТОРЫМ сообщением подписанный PDF договора: %s · %s · строка реестра %s"
W_HINT_CHECK_NOPDF = "PDF не приложен — %s; уйдёт только текст"
W_HINT_CHECK_NONE = ("⚠️ у версии %d по пояснению сверки Т4а нет — «Отправить» её не отправит и правила не даст: черновик "
                     "снимется и пересоберётся; полный текст — реплаем на карточку")
W_TEXT_NOT = "текст не ушёл — дверь PDF не звали"
W_TEXT_UNSURE = "текст: неизвестно — PDF не шлём, файл без текста не уходит"
W_RISK = ("доставка PDF статусами провайдера не подтверждена — повтор может дать клиенту ВТОРОЙ такой же PDF; "
          "дослать можно только отдельной кнопкой «Дослать PDF — риск дубля»")
W_FOREIGN = ("после попытки есть статус сообщения, которого мы не знаем (%d) — возможно, это PDF; доставкой его не "
             "считаем: PDF — неизвестно; дослать кнопкой нельзя, повтор может дать дубль — проверьте переписку")
W_BASIS = "устарело: основание PDF не подтверждено реестром при нажатии — %s; ничего не отправлено, черновик пересобирается"
W_BASIS_PDF = "дослать нельзя: основание PDF не подтверждено реестром — %s; PDF не ушёл"
BASIS_COLS = (("signed_at", "TEXT"), ("number", "TEXT"), ("date_from", "TEXT"), ("date_to", "TEXT"),
              ("ver", "INTEGER"),         # ver — Д2: версия по пояснению, чья сверка записана (NULL — версия 1)
              ("opora", "TEXT"))          # opora — K3-FIX F1: опора черновика словами для карточки (NULL — записана до F1)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attach (
    draft_id    INTEGER PRIMARY KEY,              -- черновик, прошедший сверку Т4а при WA_AGENT_ATTACH
    file_id     TEXT,                             -- NULL — вложения нет, причина в reason
    name        TEXT,
    size        INTEGER,
    sha256      TEXT,
    row         INTEGER,                          -- строка реестра подписей
    doc_id      TEXT,
    reason      TEXT,
    ts          REAL    NOT NULL,
    signed_at   TEXT,                             -- версия договора при сверке (T4B3BASIS0510)
    number      TEXT,                             -- ключ перечитывания: номер обращения …
    date_from   TEXT,                             -- … и срок аренды (ISO, пусто — неизвестен)
    date_to     TEXT,
    ver         INTEGER,                          -- Д2: версия по пояснению, чья сверка записана; NULL — версия 1
    opora       TEXT                              -- K3-FIX F1: опора черновика (источник · время чтения · версия)
);
CREATE TABLE IF NOT EXISTS pdf_parts (
    draft_id    INTEGER PRIMARY KEY,
    state       TEXT    NOT NULL,                 -- wait → claimed → sending → sent | not_sent | unsure
    attempt     INTEGER NOT NULL DEFAULT 1,
    who         TEXT,
    at          REAL,
    sending_at  REAL,
    wamid       TEXT,
    sha256      TEXT,
    reason      TEXT,
    permit      INTEGER NOT NULL DEFAULT 0        -- попытка по явному разрешению повтора при «неизвестно»
);
CREATE INDEX IF NOT EXISTS pdf_parts_wamid ON pdf_parts(wamid);
CREATE TABLE IF NOT EXISTS part_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id    INTEGER NOT NULL,
    part        TEXT    NOT NULL,                 -- text | pdf
    attempt     INTEGER NOT NULL,
    who         TEXT,
    at          REAL    NOT NULL,
    outcome     TEXT    NOT NULL,
    wamid       TEXT,
    sha256      TEXT,
    reason      TEXT
);
CREATE TABLE IF NOT EXISTS part_status (
    wamid       TEXT    NOT NULL,                 -- ТОЧНЫЙ wamid части (текста или попытки PDF)
    status      TEXT    NOT NULL,                 -- sent | delivered | read | failed
    part        TEXT    NOT NULL,                 -- text | pdf
    draft_id    INTEGER NOT NULL,
    attempt     INTEGER NOT NULL,
    ts          REAL,                             -- время статуса у провайдера (если названо)
    seen        REAL    NOT NULL,                 -- когда агент его сохранил
    src         TEXT,                             -- wa_inbox | wa_status
    PRIMARY KEY (wamid, status)
);
"""

_SHA = re.compile(r"^[0-9a-f]{64}$")


def enabled(env):
    """WA_AGENT_ATTACH — ТО ЖЕ правило, что у всех выключателей службы (`wa_agent_tg.flag_on`): 1/true/yes/on включает,
    всё прочее — выкл (NIGHT0710-B3v: до этого здесь включала только «1», и «true» служба читала вкл, а ядро — выкл)."""
    return str((env or {}).get(F_ATTACH) or "").strip().lower() in TRUE_WORDS


def _bike(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _day(v):
    d = T.B.day_of(v) if v not in (None, "") else None
    return d.isoformat() if d is not None else ""


def _term(res, c, rent):
    """Срок аренды для перечитывания: окно привязки договора кодом (`bind_contract`, ISO «a…b») — иначе дни аренды."""
    key = T.fact_key(c)
    for r in reversed(res):
        if r.get("tool") == "contract" and r.get("outcome") == T.FACT and \
                any(isinstance(f, dict) and T.fact_key(f) == key for f in r.get("facts") or []):
            a, _, b = str(r.get("window") or "").partition("…")
            if _day(a) and _day(b):
                return _day(a), _day(b)
            break
    return _day(rent.get("date_start")), _day(rent.get("date_end"))


def attach_of(tools_out, since=None):
    """Итог сверки Т4а (`ModelAdapter.last["tools"]`) → (метаданные PDF | None, причина словами).
    Вложение — только при однозначно принятом подписанном договоре этой аренды В ОПОРЕ СУДЬИ (`sift` с `since` =
    последнее входящее клиента, T4B3BASIS0510); иначе — почему вложения нет."""
    if not isinstance(tools_out, dict):
        return None, "сверки не было"
    if tools_out.get("state") != "done":
        return None, "сверка не завершена (%s) — вложения нет" % tools_out.get("state")
    res = [r for r in tools_out.get("results") or [] if isinstance(r, dict)]
    try:
        facts, dropped = T.sift(res, since)
    except Exception as e:                                           # noqa: BLE001
        return None, "опора сверки не разобрана (%s) — вложения нет" % type(e).__name__

    def by(tool):
        return [r for r in res if r.get("tool") == tool]

    def kind(k):
        return [f for f in facts if isinstance(f, dict) and f.get("kind") == k]

    def snapped(tool, what):
        why = [d for d in dropped if d.startswith(tool + ":") or d.startswith(what + ":")]
        return "%s снят опорой судьи: %s — вложения нет" % (
            {"contract": "договор", "rental": "аренда", "contract_pdf": "PDF"}[tool], why[-1] if why else "не опора")

    con = by("contract")
    cfs = kind("contract")
    if not con:
        return None, "договор не сверялся (contract не звали)"
    if not cfs:
        if any(r.get("outcome") == T.FACT for r in con):
            return None, snapped("contract", "contract")
        last = con[-1]
        return None, "договор не принят сверкой: %s — %s" % (last.get("outcome"), last.get("reason") or "")
    if len({f.get("doc_id") for f in cfs}) != 1:
        return None, "сверка приняла разные договоры — выбрать нельзя"
    c = cfs[-1]
    rent = kind("rental")
    if not rent and not by("rental") and str(c.get("bound_by") or "").strip():
        # K3-FIX шаг 3q (B1 целевого real, решение интегратора 12.10): модель `rental` не звала (реальная модель зовёт
        # `contract {}` → `contract_pdf`: подсказка ей говорит «срок аренды код подставит сам»), а договор привязал КОД —
        # к аренде, которую прочитал сам (`T.bind_ctx` → `ctx["rental"]()` в `T._read`): номер по телефону или нику
        # (`bound_by`), байк по номеру, дата договора в сроке (`T.bind_contract`). Опора вложения — эта аренда, как её
        # записала привязка: окно ответа `contract` (дни аренды), `booking_id`, байк договора. Окна нет — опоры нет,
        # прежний отказ ниже. Модель позвала `rental` — прежний путь. В журнал результатов модели чтение кодом не идёт.
        a, b = _term(res, c, {})
        if a and b:
            rent = [{"kind": "rental", "booking_id": c.get("booking_id"), "bike": c.get("bike"),
                     "date_start": a, "date_end": b}]
    if not rent:
        if any(r.get("outcome") == T.FACT for r in by("rental")):
            return None, snapped("rental", "rental")
        why = (by("rental")[-1].get("reason") or by("rental")[-1].get("outcome")) if by("rental") else "rental не звали"
        return None, "аренда не подтверждена сверкой (%s) — договор не привязать" % why
    if len({_bike(f.get("bike")) for f in rent}) != 1 or not _bike(c.get("bike")) \
            or _bike(rent[-1].get("bike")) != _bike(c.get("bike")):
        return None, "байк аренды и договора расходится"
    pdf = [r for r in by("contract_pdf")]
    if not pdf:
        return None, "PDF договора не сверен (contract_pdf не звали)"
    pf = [f for f in kind("pdf") if str(f.get("id") or "") == str(c.get("pdf_id") or "") and c.get("pdf_id")]
    if not pf:
        if any(r.get("outcome") == T.FACT and any(str((f or {}).get("id") or "") == str(c.get("pdf_id") or "")
                                                  for f in r.get("facts") or []) for r in pdf) and c.get("pdf_id"):
            return None, snapped("contract_pdf", "pdf")
        bad = [r for r in pdf if r.get("outcome") != T.FACT]
        if bad:
            return None, "PDF не принят сверкой: %s — %s" % (bad[-1].get("outcome"), bad[-1].get("reason") or "")
        return None, "сверен PDF не этого договора"
    p = pf[-1]
    sha = str(p.get("sha256") or "").lower()
    size = p.get("size")
    if not _SHA.match(sha) or not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return None, "у PDF нет sha256 или размера — прикладывать нельзя"
    signed_at = str(c.get("signed_at") or "").strip()
    if not signed_at:
        return None, "у договора нет signed_at — версию перед отправкой не сверить, вложения нет"
    date_from, date_to = _term(res, c, rent[-1])
    return {"file_id": str(p.get("id")), "name": str(p.get("name") or "contract.pdf"), "size": size,
            "sha256": sha, "row": p.get("row") if p.get("row") is not None else c.get("row"),
            "doc_id": c.get("doc_id"), "signed_at": signed_at, "date_from": date_from, "date_to": date_to}, ""


# ── K3-FIX F1: опора черновика на карточке — источник, время ЧТЕНИЯ, версия ТОЛЬКО от источника ──────────────────
OPORA_HEAD = "🧾 опора черновика — факты сверки Т4а (инструмент · источник · время чтения · версия источника)%s:"
OPORA_NONE = "🧾 опора черновика: фактов сверки нет%s"
OPORA_UNREAD = "🧾 опора черновика не разобрана (%s) — источники фактов не названы"
OPORA_LEGACY = "🧾 опора черновика не записана: сверка записана до K3-FIX F1"
OPORA_OFF = "• прочитано фактом, но не в опоре судьи (тот же запрос прочитан позже, устарел или снят): %d"
OPORA_CUT = "• … не показано строк опоры: %d (предел карточки — %d строк, %d знаков)"
OPORA_ROWS, OPORA_CHARS = 6, 700
W_VER_UNKNOWN = "неизвестна"
_OPORA_STATE = {T.DONE: "", T.OVER: " (сверка не завершена: предел вызовов или времени)",
                T.ABORTED: " (сверка оборвана новым сообщением клиента)"}


def _opora_row(r, n):
    # K3-FIX3 (F2): время ДАННЫХ — `read_at` (у снимка аренды и правил — время СНИМКА; None — неизвестно, а не время
    # вызова); ответ, записанный до шага 3 (ключа нет), — прежнее `at`
    at = r.get("read_at") if "read_at" in r else r.get("at")
    when = ("прочитано %s" % A.hm_phuket(at) if isinstance(at, (int, float)) and not isinstance(at, bool) and at > 0
            else "время чтения неизвестно")
    ver = r.get("source_version")                    # только поле контракта «версия, выданная источником» (F2 §1.1)
    ver = str(ver).strip()[:40] if isinstance(ver, str) and ver.strip() else W_VER_UNKNOWN
    src = str(r.get("source") or "").strip() or "источник не назван"
    return "• %s · %s · %s · версия: %s%s" % (r.get("tool") or "?", src[:80], when, ver,
                                             " · фактов %d" % n if n > 1 else "")


def opora_of(tools_out, since=None, rows_max=OPORA_ROWS, chars_max=OPORA_CHARS):
    """Итог сверки Т4а (`ModelAdapter.last["tools"]`) → опора черновика словами для карточки (K3-FIX F1) | None (сверки
    нет). Строка — на КАЖДЫЙ ответ инструмента, чьи факты остались в опоре судьи (`sift` с тем же since, что у
    `attach_of`), по порядку чтения: инструмент · источник (`source` ответа: дверь, лист, узел) · время ЧТЕНИЯ ДАННЫХ
    (`read_at`, K3-FIX3: у прямых дверей — `at`, который `_read` ставит ДО вызова двери; у снимков — время снимка; по
    Пхукету, как все слова сотрудникам) · версия ТОЛЬКО если её отдал источник
    (`source_version` ответа, F2_CONTRACT §1.1; сегодня её не отдаёт ни одна дверь) — иначе «неизвестна». Поле `version`
    результата версией источника НЕ является (там `signed_at` договора и длина правил — F2_CONTRACT §0.3), служебное
    `stand_meta` подделки моста в результат не попадает вовсе. Новых обращений к мосту нет — только уже прочитанное.
    Длина — потолок строк и знаков; усечение названо числом, как и факты, снятые опорой судьи."""
    if not isinstance(tools_out, dict):
        return None
    res = [r for r in tools_out.get("results") or [] if isinstance(r, dict)]
    try:
        facts, _dropped = T.sift(res, since)
        order = T.read_order(res)
    except Exception as e:                                           # noqa: BLE001
        return OPORA_UNREAD % type(e).__name__
    keep = {id(f) for f in facts}
    rows, off = [], 0
    for i in order:
        r = res[i]
        if r.get("outcome") != T.FACT:
            continue
        n = sum(1 for f in r.get("facts") or [] if id(f) in keep)
        if n:
            rows.append(_opora_row(r, n))
        else:
            off += 1
    tail = _OPORA_STATE.get(tools_out.get("state"), " (исход сверки не разобран)")
    if not rows:
        return OPORA_NONE % tail + ("\n" + OPORA_OFF % off if off else "")
    out = [OPORA_HEAD % tail]
    shown = 0
    for line in rows:
        if shown >= rows_max or len("\n".join(out[1:] + [line])) > chars_max:
            break
        out.append(line)
        shown += 1
    if shown < len(rows):
        out.append(OPORA_CUT % (len(rows) - shown, rows_max, chars_max))
    if off:
        out.append(OPORA_OFF % off)
    return "\n".join(out)


def recheck_of(resp, basis):
    """Живое чтение реестра (`contract_find`) против основания черновика → (True, "") | (False, причина словами).
    Пропуск — только `one`, пустой `unread`, `undated_signed` = 0, подписанный `pick` и совпавшие row, doc_id, pdf_id и
    signed_at. Всё прочее — отказ: перечитать не удалось, ответ не разобран, отзыв, новая версия, второй подписанный."""
    if not isinstance(basis, dict) or not str(basis.get("signed_at") or "").strip():
        return False, "версия договора при сверке не записана — перечитать не с чем"
    if not isinstance(resp, dict):
        return False, "ответ реестра не разобран (не словарь)"
    if not resp.get("ok"):
        return False, "реестр не прочитан: %s" % (str(resp.get("error") or "ответ без ok")[:120])
    out = resp.get("outcome")
    checked = resp.get("checked") if isinstance(resp.get("checked"), dict) else None
    if out == "ambiguous":
        return False, "в реестре подписанных несколько — второй подписанный договор, выбрать нельзя"
    if out == "incomplete":
        return False, "ответ реестра неполон — подписанный без известного дня"
    if out == "none_signed":
        return False, "подписанного договора больше нет — договор отозван"
    if out == "none":
        return False, "договор в реестре не найден — договор отозван или убран"
    if out != "one":
        return False, "исход реестра не разобран: %s" % str(out)[:40]
    if checked is None:
        return False, "ответ реестра не разобран: нет checked"
    unread, undated = checked.get("unread"), checked.get("undated_signed")
    if not isinstance(unread, list) or not isinstance(undated, int) or isinstance(undated, bool):
        return False, "ответ реестра не разобран: нет полей полноты unread/undated_signed"
    if unread:
        return False, "реестр прочитан не целиком (не прочитано: %s)" % ", ".join(str(u) for u in unread)[:120]
    if undated != 0:
        return False, "подписанных без известного дня %d" % undated
    pick = resp.get("pick")
    if not isinstance(pick, dict):
        return False, "ответ реестра не разобран: нет pick"
    if pick.get("signed") is not True:
        return False, "договор не подписан — отозван"
    for key, have, want in (("row", pick.get("row"), basis.get("row")),
                            ("doc_id", pick.get("doc_id"), basis.get("doc_id")),
                            ("pdf_id", pick.get("pdf_id"), basis.get("file_id")),
                            ("signed_at", pick.get("signed_at"), basis.get("signed_at"))):
        if str(have if have is not None else "").strip() != str(want if want is not None else "").strip():
            return False, "договор сменился: %s при сверке %s, в реестре сейчас %s" % (
                key, str(want)[:40], str(have)[:40])
    return True, ""


W_UNKNOWN_NO_REPEAT = "исход неизвестен — не повторять, проверить переписку"
W_SENDING = "отправляется"
W_LATE = "ответ этого процесса опоздал: часть решил другой процесс, слова — по базе"
_DECIDING = (A.PENDING, A.CLAIMED, A.SENDING, A.SCHEDULED, P_WAIT, P_CLAIMED)
# K3-FIX N1: состояния, которые не являются исходом двери, — словами (A.CLAIMED и P_CLAIMED — одно слово «claimed»)
_STATE_WORDS = {A.PENDING: "ждёт нажатия", A.CLAIMED: "взят к отправке, двери ещё не было", A.SCHEDULED: "отложен ритмом",
                P_WAIT: "ждёт текста", A.DECLINED: "не нужно (решил человек)", A.STALE: "устарел, не отправлен",
                A.SUPERSEDED: "заменён, не отправлен"}


def wamid_tail(wamid):
    """wamid части — хвостом (8 знаков): опознать попытку в журнале и квитанциях, не загромождая карточку."""
    return "…" + str(wamid)[-8:]


def state_word(state, reason=None, wamid=None, pdf=False):
    """Состояние части → слово сотруднику (K3-FIX N1; одно на нажавшего, карточку, перечитанное N2 и старт K17):
    sending — «отправляется»; sent — «ушёл (wamid …)» (wamid — когда назван); unsure — «исход неизвестен — не повторять,
    проверить переписку»; not_sent — «не ушёл: причина» (у текста причина — ответ двери из `drafts.reason`; не передана —
    «не ушёл»). Внутреннего кода сотрудник не видит; незнакомое состояние названо как неразобранное."""
    if state == A.SENT:
        return "ушёл" + (" (wamid %s)" % wamid_tail(wamid) if wamid else "")
    if state == A.NOT_SENT:
        why = str(reason or "").strip()
        if pdf:
            return "не ушёл: %s" % (why or "причина не названа")[:200]
        return ("не ушёл: %s" % (why or "причина не названа")[:200]) if reason is not None else "не ушёл"
    if state == A.UNSURE:
        return W_UNKNOWN_NO_REPEAT
    if state == A.SENDING:
        return W_SENDING
    return _STATE_WORDS.get(state) or "состояние «%s» не разобрано" % (state or "?")


def parts_words(text_state, pdf_state=None, pdf_reason="", text_reason=None, text_wamid=None, pdf_wamid=None):
    """Исходы частей — рукам словами (K3-FIX N1, словарь `state_word`): «текст: ушёл · PDF: ушёл / не ушёл: причина /
    исход неизвестен — не повторять, проверить переписку». wamid называется, когда передан (карточка), нажавшему — нет."""
    out = "текст: %s" % state_word(text_state, text_reason, text_wamid)
    if pdf_state is None:
        return out
    return out + " · PDF: %s" % state_word(pdf_state, pdf_reason, pdf_wamid, pdf=True)


# ── K3-FIX N2: исход частей, когда ответ этого процесса опоздал (захват проигран второму экземпляру/конкуренту) ──
def reread_words(text_state, pdf_state=None, pdf_reason="", text_reason=None, text_wamid=None, pdf_wamid=None):
    """Исходы частей словами по ПЕРЕЧИТАННЫМ устойчивым состояниям (K3-FIX N2, словарь N1 `state_word`). «не ушёл» —
    только при not_sent в базе; unsure — «исход неизвестен — не повторять, проверить переписку»; часть посреди чужого
    захода — тоже неизвестен (состояние — словом)."""
    def one(state, reason, wamid, pdf):
        if state in _DECIDING:
            return "решается другим процессом (%s) — %s" % (state_word(state), W_UNKNOWN_NO_REPEAT)
        if state in (A.SENT, A.NOT_SENT, A.UNSURE):
            return state_word(state, reason, wamid, pdf)
        return "решён иначе (%s)" % state_word(state)
    out = "текст: %s" % one(text_state, text_reason, text_wamid, False)
    if pdf_state is not None:
        out += " · PDF: %s" % one(pdf_state, pdf_reason, pdf_wamid, True)
    return out


# ── K3-FIX F4: скелет PDF — проверка ТЕХ ЖЕ байтов, что уйдут двери, ДО двери ──
PDF_LEVEL = ("скелет PDF (K3-FIX F4): заголовок «%PDF-» в байте 0 · «startxref <смещение>» и «%%EOF» в последних 1024 "
             "байтах · смещение startxref указывает на таблицу ссылок «xref» (или поток ссылок /Type /XRef), и она "
             "разбирается вместе с цепочкой /Prev (и /XRefStm) · трейлер называет /Root · по таблице ссылок находится "
             "каталог /Type /Catalog со ссылкой /Pages · по таблице ссылок находится корень дерева страниц /Type /Pages "
             "с /Count ≥ 1 и непустым /Kids · каждый ребёнок корня находится по таблице ссылок и он /Page или /Pages. "
             "Сжатые объекты — только /FlateDecode (предиктор PNG). НЕ проверяется: содержимое и потоки страниц, "
             "шрифты, прочие объекты, подписи — это НЕ «PDF исправен», а «скелет PDF цел»")
W_PDF_SHAPE = "скелет PDF не сошёлся: %s — двери не было, повтора нет; откройте файл договора"
_PDF_TAIL = 1024
_PDF_MAX_SECTIONS = 64
_PDF_MAX_KIDS = 4096
_WSB = b" \t\r\n\f\x00"
_W = rb"[ \t\r\n\f\x00]"
_RX_OBJ = re.compile(_W + rb"*(\d+)" + _W + rb"+(\d+)" + _W + rb"+obj(?![A-Za-z0-9])")
_RX_XREF = re.compile(_W + rb"*xref(?![A-Za-z0-9])")
_RX_SUB = re.compile(_W + rb"*(\d+)[ \t]+(\d+)[ \t]*(?:\r\n|\r|\n)")
_RX_ENT = re.compile(rb"(\d{10})[ \t](\d{5})[ \t]([nf])[ \t]*(?:\r\n|\r|\n)")
_RX_TRAILER = re.compile(_W + rb"*trailer(?![A-Za-z0-9])")
_RX_STARTXREF = re.compile(rb"startxref" + _W + rb"+(\d+)" + _W + rb"+%%EOF")
_RX_STREAM = re.compile(_W + rb"*stream(?:\r\n|\n|\r)")


class _PdfBad(Exception):
    """Скелет PDF не сошёлся на заявленном уровне — причина словами."""


def _pdf_dict(buf, pos):
    """Словарь «<< … >>» с позиции pos → (верхний уровень, текст целиком, конец). Верхний уровень — тот же текст, где
    вложенные словари, строки и комментарии заменены пробелами той же длины: ключ вложенного словаря за ключ верхнего не
    сойдёт, а позиции совпадают с текстом целиком."""
    i, n = pos, len(buf)
    while i < n and buf[i] in _WSB:
        i += 1
    if buf[i:i + 2] != b"<<":
        raise _PdfBad("на месте словаря нет «<<» (байт %d)" % i)
    start, depth, top = i, 0, bytearray()
    while i < n:
        two = buf[i:i + 2]
        if two == b"<<":
            depth += 1
            top += two if depth == 1 else b"  "
            i += 2
            continue
        if two == b">>":
            depth -= 1
            top += two if depth == 0 else b"  "
            i += 2
            if depth == 0:
                return bytes(top), buf[start:i], i
            continue
        c = buf[i:i + 1]
        if c == b"(":                                   # строка: вложенные скобки и экраны
            j, lvl = i + 1, 1
            while j < n and lvl:
                ch = buf[j:j + 1]
                if ch == b"\\":
                    j += 2
                    continue
                lvl += 1 if ch == b"(" else -1 if ch == b")" else 0
                j += 1
            if lvl:
                raise _PdfBad("строка в словаре без конца")
            top += b" " * (j - i)
            i = j
            continue
        if c == b"<":                                   # шестнадцатеричная строка
            j = buf.find(b">", i + 1)
            if j < 0:
                raise _PdfBad("шестнадцатеричная строка в словаре без конца")
            top += b" " * (j + 1 - i)
            i = j + 1
            continue
        if c == b"%":                                   # комментарий до конца строки
            j = i
            while j < n and buf[j:j + 1] not in (b"\r", b"\n"):
                j += 1
            top += b" " * (j - i)
            i = j
            continue
        top += c if depth == 1 else b" "
        i += 1
    raise _PdfBad("словарь без конца «>>»")


def _pdf_name(top, key):
    m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])" + _W + rb"*/([A-Za-z0-9_.+-]+)", top)
    return m.group(1) if m else None


def _pdf_ref(top, key):
    m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])" + _W + rb"*(\d+)" + _W + rb"+(\d+)" + _W + rb"+R(?![A-Za-z0-9])", top)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _pdf_int(top, key):
    """Прямое целое ключа | None (ссылка «N G R» — не прямое целое)."""
    m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])" + _W + rb"*(-?\d+)(?![\d.])(?!" + _W + rb"+\d+" + _W + rb"+R)", top)
    return int(m.group(1)) if m else None


def _pdf_array(top, key):
    m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])" + _W + rb"*\[([^\]]*)\]", top)
    return m.group(1) if m else None


def _pdf_stream(buf, end, top):
    """Байты потока объекта, чей словарь кончился на end: по прямому /Length, если за ним «endstream», иначе до
    «endstream»."""
    m = _RX_STREAM.match(buf, end)
    if not m:
        raise _PdfBad("за словарём потока нет «stream»")
    s, length = m.end(), _pdf_int(top, b"Length")
    if length is not None and 0 <= length <= len(buf) - s and re.match(_W + rb"*endstream", buf[s + length:s + length + 40]):
        return buf[s:s + length]
    e = buf.find(b"endstream", s)
    if e < 0:
        raise _PdfBad("поток без «endstream»")
    return buf[s:e]


def _pdf_decode(data, top, whole):
    """Поток → байты: без фильтра или /FlateDecode (+ предиктор PNG, 1 байт на отсчёт). Иное — не этот уровень."""
    filt = re.findall(rb"/([A-Za-z0-9]+)", (re.search(rb"/Filter(?![A-Za-z0-9])" + _W + rb"*(\[[^\]]*\]|/[A-Za-z0-9]+)",
                                                        top) or [None, b""])[1]) if b"/Filter" in top else []
    if filt and filt != [b"FlateDecode"]:
        raise _PdfBad("фильтр потока %s этим уровнем не разбирается — не проверено" % b"/".join(filt).decode("latin-1"))
    if filt:
        try:
            d = zlib.decompressobj()
            data = d.decompress(data) + d.flush()
        except zlib.error:
            raise _PdfBad("поток /FlateDecode не распаковывается")
    k = top.find(b"/DecodeParms")
    if k < 0:
        return data
    ptop, _w, _e = _pdf_dict(whole, k + len(b"/DecodeParms"))
    pred = _pdf_int(ptop, b"Predictor") or 1
    if pred == 1:
        return data
    cols, colors, bpc = _pdf_int(ptop, b"Columns") or 1, _pdf_int(ptop, b"Colors") or 1, _pdf_int(ptop, b"BitsPerComponent") or 8
    if pred < 10 or colors != 1 or bpc != 8 or cols < 1:
        raise _PdfBad("предиктор %d (Colors %d, BitsPerComponent %d) этим уровнем не разбирается — не проверено"
                      % (pred, colors, bpc))
    row = cols + 1
    if len(data) % row:
        raise _PdfBad("поток с предиктором PNG не делится на строки")
    out, prev = bytearray(), bytearray(cols)
    for k in range(0, len(data), row):
        ft, line = data[k], bytearray(data[k + 1:k + row])
        for x in range(cols):
            a, b, c = (line[x - 1] if x else 0), prev[x], (prev[x - 1] if x else 0)
            if ft == 1:
                line[x] = (line[x] + a) & 255
            elif ft == 2:
                line[x] = (line[x] + b) & 255
            elif ft == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            elif ft != 0:
                raise _PdfBad("строка предиктора PNG с типом %d" % ft)
        out += line
        prev = line
    return bytes(out)


def _pdf_xref_table(buf, off):
    """Таблица ссылок «xref» по смещению → ({номер: запись}, верхний уровень трейлера) | None — там не «xref»."""
    m = _RX_XREF.match(buf, off)
    if not m:
        return None
    pos, entries, subs = m.end(), {}, 0
    while True:
        h = _RX_SUB.match(buf, pos)
        if not h:
            break
        first, count = int(h.group(1)), int(h.group(2))
        pos = h.end()
        if count > (len(buf) - pos) // 18 + 1:
            raise _PdfBad("подраздел таблицы ссылок (%d записей) длиннее файла" % count)
        for i in range(count):
            e = _RX_ENT.match(buf, pos)
            if not e:
                raise _PdfBad("запись %d таблицы ссылок не разобрана (байт %d)" % (first + i, pos))
            pos = e.end()
            entries.setdefault(first + i, ("n", int(e.group(1)), int(e.group(2))) if e.group(3) == b"n" else ("f",))
        subs += 1
    if not subs:
        raise _PdfBad("в таблице ссылок нет ни одного подраздела")
    t = _RX_TRAILER.match(buf, pos)
    if not t:
        raise _PdfBad("за таблицей ссылок нет «trailer» (байт %d)" % pos)
    return entries, _pdf_dict(buf, t.end())[0]


def _pdf_xref_stream(buf, off):
    """Поток ссылок по смещению → ({номер: запись}, верхний уровень его словаря) | None — там не объект."""
    m = _RX_OBJ.match(buf, off)
    if not m:
        return None
    top, whole, end = _pdf_dict(buf, m.end())
    if _pdf_name(top, b"Type") != b"XRef":
        raise _PdfBad("по смещению %d объект, но не поток ссылок /Type /XRef" % off)
    data = _pdf_decode(_pdf_stream(buf, end, top), top, whole)
    w = [int(x) for x in re.findall(rb"\d+", _pdf_array(top, b"W") or b"")]
    size = _pdf_int(top, b"Size")
    idx = [int(x) for x in re.findall(rb"\d+", _pdf_array(top, b"Index") or b"")] or [0, size or 0]
    if len(w) != 3 or size is None or len(idx) % 2 or not sum(w):
        raise _PdfBad("словарь потока ссылок без /W из трёх чисел или /Size")
    width, pos, entries = sum(w), 0, {}
    for start, count in zip(idx[0::2], idx[1::2]):
        for i in range(count):
            rec = data[pos:pos + width]
            if len(rec) < width:
                raise _PdfBad("поток ссылок короче, чем объявляют /W и /Index")
            pos += width
            f, p = [], 0
            for n_ in w:
                f.append(int.from_bytes(rec[p:p + n_], "big") if n_ else None)
                p += n_
            kind = f[0] if w[0] else 1
            if kind == 0:
                entries.setdefault(start + i, ("f",))
            elif kind == 1:
                entries.setdefault(start + i, ("n", f[1], f[2] or 0))
            elif kind == 2:
                entries.setdefault(start + i, ("c", f[1], f[2] or 0))
    return entries, top


def _pdf_sections(buf, off):
    """Цепочка таблиц ссылок от startxref: сама, её /XRefStm, затем /Prev → [(записи, трейлер)] от новой к старой."""
    out, seen, todo = [], set(), [off]
    while todo:
        o = todo.pop(0)
        if o in seen:
            continue
        if len(seen) >= _PDF_MAX_SECTIONS:
            raise _PdfBad("цепочка /Prev длиннее %d таблиц" % _PDF_MAX_SECTIONS)
        seen.add(o)
        if not 0 <= o < len(buf):
            raise _PdfBad("смещение таблицы ссылок %d вне файла (%d байт)" % (o, len(buf)))
        got = _pdf_xref_table(buf, o) or _pdf_xref_stream(buf, o)
        if got is None:
            raise _PdfBad("смещение %d указывает не на таблицу ссылок «xref» и не на поток ссылок" % o)
        out.append(got)
        xs = _pdf_int(got[1], b"XRefStm")
        if xs is not None:
            hyb = _pdf_xref_stream(buf, xs) if 0 <= xs < len(buf) else None
            if hyb is None:
                raise _PdfBad("/XRefStm %d не указывает на поток ссылок" % xs)
            out.append(hyb)
        prev = _pdf_int(got[1], b"Prev")
        if prev is not None:
            todo.append(prev)
    return out


def _pdf_at(buf, table, ref, stms):
    """Объект ref по таблице ссылок → верхний уровень его словаря. Сжатый в потоке объектов — из распакованного потока."""
    num = ref[0]
    ent = table.get(num)
    if ent is None:
        raise _PdfBad("объекта %d нет в таблице ссылок" % num)
    if ent[0] == "f":
        raise _PdfBad("объект %d в таблице ссылок помечен свободным" % num)
    if ent[0] == "n":
        if not 0 <= ent[1] < len(buf):
            raise _PdfBad("смещение объекта %d (%d) вне файла" % (num, ent[1]))
        m = _RX_OBJ.match(buf, ent[1])
        if not m or int(m.group(1)) != num:
            raise _PdfBad("по смещению объекта %d из таблицы ссылок (%d) нет «%d %d obj»" % (num, ent[1], num, ref[1]))
        return _pdf_dict(buf, m.end())[0]
    if ent[1] not in stms:
        sent = table.get(ent[1])
        if not sent or sent[0] != "n":
            raise _PdfBad("поток объектов %d для объекта %d не найден по таблице ссылок" % (ent[1], num))
        m = _RX_OBJ.match(buf, sent[1]) if 0 <= sent[1] < len(buf) else None
        if not m or int(m.group(1)) != ent[1]:
            raise _PdfBad("по смещению потока объектов %d нет «%d 0 obj»" % (ent[1], ent[1]))
        top, whole, end = _pdf_dict(buf, m.end())
        if _pdf_name(top, b"Type") != b"ObjStm":
            raise _PdfBad("объект %d — не поток объектов /Type /ObjStm" % ent[1])
        data, first, count = _pdf_decode(_pdf_stream(buf, end, top), top, whole), _pdf_int(top, b"First"), \
            _pdf_int(top, b"N")
        head = [int(x) for x in re.findall(rb"\d+", data[:first or 0])]
        if first is None or count is None or len(head) < 2 * count:
            raise _PdfBad("заголовок потока объектов %d не разобран" % ent[1])
        stms[ent[1]] = (data, first, dict(zip(head[0:2 * count:2], head[1:2 * count:2])))
    data, first, offs = stms[ent[1]]
    if num not in offs:
        raise _PdfBad("объекта %d нет в потоке объектов %d" % (num, ent[1]))
    return _pdf_dict(data, first + offs[num])[0]


def pdf_shape(raw):
    """Байты PDF → (True, "") | (False, причина словами). Уровень — ровно `PDF_LEVEL`, не шире (K3-FIX F4)."""
    try:
        return _pdf_shape(bytes(raw or b""))
    except _PdfBad as e:
        return False, str(e)
    except Exception as e:                                           # noqa: BLE001 — сбой разбора = не проверено = не шлём
        return False, "скелет PDF не разобран (%s)" % type(e).__name__


def _pdf_shape(buf):
    if not buf.startswith(b"%PDF-"):
        raise _PdfBad("нет заголовка «%PDF-» в начале файла")
    tail = max(0, len(buf) - _PDF_TAIL)
    eof = buf.rfind(b"%%EOF", tail)
    if eof < 0:
        raise _PdfBad("нет «%%EOF» в последних 1024 байтах — файл обрезан или повреждён")
    sx = buf.rfind(b"startxref", tail, eof)
    m = _RX_STARTXREF.match(buf, sx) if sx >= 0 else None
    if not m:
        raise _PdfBad("нет «startxref <смещение>» перед последним «%%EOF»")
    sections = _pdf_sections(buf, int(m.group(1)))
    table = {}
    for entries, _top in sections:
        for num, ent in entries.items():
            table.setdefault(num, ent)
    root = next((r for r in (_pdf_ref(top, b"Root") for _e, top in sections) if r), None)
    if root is None:
        raise _PdfBad("трейлер не называет /Root")
    stms = {}
    cat = _pdf_at(buf, table, root, stms)
    if _pdf_name(cat, b"Type") != b"Catalog":
        raise _PdfBad("/Root %d — не каталог /Type /Catalog" % root[0])
    pages = _pdf_ref(cat, b"Pages")
    if pages is None:
        raise _PdfBad("в каталоге нет ссылки /Pages")
    ptop = _pdf_at(buf, table, pages, stms)
    if _pdf_name(ptop, b"Type") != b"Pages":
        raise _PdfBad("корень дерева страниц %d — не /Type /Pages" % pages[0])
    count = _pdf_int(ptop, b"Count")
    if count is None:
        raise _PdfBad("у корня дерева страниц нет прямого целого /Count")
    if count < 1:
        raise _PdfBad("у корня дерева страниц /Count %d — страниц нет" % count)
    kids = [(int(a), int(b)) for a, b in re.findall(rb"(\d+)" + _W + rb"+(\d+)" + _W + rb"+R(?![A-Za-z0-9])",
                                                    _pdf_array(ptop, b"Kids") or b"")]
    if not kids:
        raise _PdfBad("у корня дерева страниц пустой /Kids")
    for kid in kids[:_PDF_MAX_KIDS]:
        if _pdf_name(_pdf_at(buf, table, kid, stms), b"Type") not in (b"Page", b"Pages"):
            raise _PdfBad("ребёнок %d корня дерева страниц — не /Page и не /Pages" % kid[0])
    return True, ""


class _Probe:
    """Модель-обёртка: после каждого черновика запоминает итог сверки Т4а по (номер, upto) — ядро о нём не знает.
    Версия по пояснению (Д2 INTEG0710) — тем же путём сверки, если модель его умеет; итог — по (HINT_SEEN, номер, upto)."""

    def __init__(self, inner, seen):
        self._inner, self._seen = inner, seen

    def draft(self, number, upto_id):
        got = self._inner.draft(number, upto_id)
        last = getattr(self._inner, "last", None)
        tools = last.get("tools") if isinstance(last, dict) else None
        info = last.get("info") if isinstance(last, dict) and isinstance(last.get("info"), dict) else {}
        # since — то же последнее входящее клиента, что судья получает в judge(since=info["last_in"]) (T4B3BASIS0510)
        self._seen[(number, upto_id)] = None if tools is None else (tools, info.get("last_in"))
        return got

    def hint_check(self):
        """Умеет ли модель версию по пояснению СО СВЕРКОЙ Т4а (Д2): двери сверки есть (`tools`) и путь `redraft_checked`
        есть. Нет — версия по пояснению сверку не пройдёт."""
        return getattr(self._inner, "tools", None) is not None and \
            callable(getattr(self._inner, "redraft_checked", None))

    def redraft(self, number, upto_id, prev_text, hint):
        """Версия по пояснению (Д2): модель умеет — путь сверки Т4а (`redraft_checked`), итог запоминается по ключу версии;
        не умеет — прежний `redraft`, итога нет («без сверки»). Итог берётся только из `last`, записанного ЭТИМ вызовом:
        прежний `last` (сверка версии 1) за сверку версии по пояснению не выдаётся."""
        checked = self.hint_check()
        before = getattr(self._inner, "last", None)
        if checked:
            got = self._inner.redraft_checked(number, upto_id, prev_text, hint)
        else:
            got = self._inner.redraft(number, upto_id, prev_text, hint)
        last = getattr(self._inner, "last", None) if checked else None
        tools = last.get("tools") if isinstance(last, dict) and last is not before else None
        info = last.get("info") if isinstance(last, dict) and isinstance(last.get("info"), dict) else {}
        self._seen[(HINT_SEEN, number, upto_id)] = None if tools is None else (tools, info.get("last_in"))
        return got

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _TxDoor:
    """Дверь на время текстовой части (NIGHT0710-B3v): ответ двери получен — открывается транзакция, и исход текста,
    строка outbox (пишет ядро) и строка журнала части (пишет `_text_part`) ложатся ОДНОЙ записью или не ложатся вовсе.
    sending ядро пишет ДО двери отдельно (автокоммит) — рестарт после него повтора не даёт. Смерть процесса посреди
    двери (не Exception) транзакции не открывает."""

    def __init__(self, inner, begin, log=None):
        self._inner, self._begin, self._log = inner, begin, log

    def send_text(self, to, text):
        try:
            res = self._inner.send_text(to, text)
        except Exception:                                            # noqa: BLE001 — ядро разберёт как «неизвестно»
            self._open()
            raise
        self._open()
        return res

    def _open(self):
        try:
            self._begin()
        except Exception as e:                                       # noqa: BLE001
            # транзакция не открылась — ответ двери важнее: исход ляжет без неё, как раньше; молча — нет (второй круг)
            if callable(self._log):
                self._log("транзакция текстовой части не открылась (%s) — запись без неё" % type(e).__name__)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class AttachCore(A.Core):
    """Ядро с PDF договора второй частью. attach=False — каждый метод отдаёт управление `Core` (голден 24ad256)."""

    def __init__(self, *args, attach=False, pdf_fetch=None, contract_find=None, **kw):
        self.attach = bool(attach)
        self.pdf_fetch = pdf_fetch                  # file_id → ответ `bridge_client.contract_pdf` (content_b64, verified)
        self.contract_find = contract_find          # (phone, date_from, date_to) → ответ `bridge_client.contract_find`
        self._seen = {}
        self._hold = None                           # черновик, чей исход на карточку пишем после обеих частей
        self._held = None                           # слова ядра о тексте, придержанные на время части
        self._held_tg = None                        # правка карточки ядром, отложенная до COMMIT части (INTEG0710)
        self._status_last = None                    # такт сбора статусов частей (STATUS_EVERY)
        super().__init__(*args, **kw)
        if self.attach:
            self.model = _Probe(self.model, self._seen)

    # ── база ──────────────────────────────────────────────────────────────────────────────

    def _startup(self):
        # K3-FIX K17: черновики посреди текстовой двери (sending) — до того, как ядро переведёт их в unsure: у текста без
        # части PDF исход старта тоже ложится на карточку (иначе на ней жила кнопка «Отправить»)
        mid_text = [r[0] for r in self.db.execute("SELECT id FROM drafts WHERE state=?", (A.SENDING,)).fetchall()] \
            if self.attach else []
        super()._startup()
        if not self.attach:
            return
        self.db.executescript(_SCHEMA)
        have = {r[1] for r in self.db.execute("PRAGMA table_info(attach)").fetchall()}
        for col, typ in BASIS_COLS:                 # база до T4B3BASIS0510: строки без версии — перечитать не с чем
            if col not in have:
                self.db.execute("ALTER TABLE attach ADD COLUMN %s %s" % (col, typ))
        moved = [r[0] for r in self.db.execute("SELECT draft_id FROM pdf_parts WHERE state IN (?,?)",
                                               (A.SENDING, P_CLAIMED)).fetchall()]
        n1 = self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE state=?",
                             (A.UNSURE, "рестарт посреди отправки PDF — могло уйти, не повторяем", A.SENDING)).rowcount
        n2 = self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE state=?",
                             (A.NOT_SENT, "рестарт до двери PDF — не отправлено", P_CLAIMED)).rowcount
        rows = self.db.execute("SELECT p.draft_id, d.state FROM pdf_parts p JOIN drafts d ON d.id=p.draft_id "
                               "WHERE p.state=?", (P_WAIT,)).fetchall()
        waited = 0
        for did, tstate in rows:
            if tstate in (A.SENDING, A.CLAIMED, A.PENDING, A.SCHEDULED):
                continue                            # текст ещё не решён — PDF ждёт его
            if tstate not in (A.SENT, A.UNSURE, A.NOT_SENT):
                # текст решён НЕ дверью (не нужно · устарел · заменён): исход человека/ядра уже на карточке — часть
                # закрывается, карточка НЕ перетирается (второй круг, R18)
                self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=?",
                                (A.NOT_SENT, "текст не отправлялся (%s) — PDF не звали" % tstate, did, P_WAIT))
                continue
            why =("рестарт между частями — PDF не звали" if tstate == A.SENT else
                   W_TEXT_UNSURE if tstate == A.UNSURE else W_TEXT_NOT)
            self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=?",
                            (A.NOT_SENT, why, did, P_WAIT))
            moved.append(did)
            waited += 1
        if n1 or n2 or rows:
            self.log("старт: PDF sending→unsure %d, claimed→not_sent %d, ждали текста %d" % (n1, n2, len(rows)))
        # исход обеих частей — на карточку (NIGHT0710-B3v): `_hold` погасил итог текста, а итог части процесс не дописал;
        # правка ляжет первым тактом (очередь `card_out`), с кнопкой «Дослать PDF» — без человека PDF не уходит
        now = self.clock()
        for did in sorted(set(moved)):
            self._card_settle(did, now)
        if moved:
            self.log("старт: исход частей на карточку — черновиков %d (рестарт между частями %d)" % (
                len(set(moved)), waited))
        # K3-FIX K17: текст без части PDF, прерванный рестартом посреди двери: ядро перевело его в unsure (могло уйти —
        # повтора нет); исход «неизвестен — не повторять, проверить» ложится на карточку вместо живой кнопки «Отправить».
        # Это НЕ дубль: двери второй раз не было и не будет — предотвращённый повтор дублем не называется
        alone = [did for did in mid_text if did not in set(moved) and self.db.execute(
            "SELECT 1 FROM drafts d WHERE d.id=? AND d.state=? AND NOT EXISTS (SELECT 1 FROM pdf_parts p "
            "WHERE p.draft_id=d.id)", (did, A.UNSURE)).fetchone()]
        settled = [did for did in alone if self._card_settle(did, now)]
        if alone:
            self.log("старт: текст без PDF посреди двери — исход «неизвестен, не повторять» на карточку: черновиков %d "
                     "(карточка в очереди правки у %d)" % (len(alone), len(settled)))

    def _card_settle(self, draft_id, now, why=W_RESTART):
        """Исход частей черновика → очередь правки карточки (`card_out`): решена, правка ждёт первого такта.
        Карточки в очереди нет (запись старше неё) — только строка журнала: править нечем.
        K3-FIX N1/K17: и черновик БЕЗ части PDF (только текст) — его исход тоже ложится на карточку; слова — словарём
        `state_word`, у ушедших частей — wamid."""
        row = self.db.execute("SELECT d.state, d.ver, p.state, p.reason, d.reason, d.wamid, p.wamid FROM drafts d "
                              "LEFT JOIN pdf_parts p ON p.draft_id=d.id WHERE d.id=?", (draft_id,)).fetchone()
        if not row:
            return False
        tstate, ver, pstate, preason, treason, tw, pw = row
        words = "%s — %s, %s" % (parts_words(tstate, pstate, preason, text_reason=treason or "", text_wamid=tw,
                                             pdf_wamid=pw), why, A.hm_phuket(now))
        n = self.db.execute("UPDATE card_out SET state=?, decided_at=COALESCE(decided_at, ?), words=?, "
                            "edit=CASE WHEN message_id IS NULL THEN NULL ELSE ? END, edit_tries=0, edit_unk=0, "
                            "next_at=0 WHERE draft_id=? AND ver=?",
                            (A.CARD_DECIDED, now, words, A.EDIT_WAIT, draft_id, int(ver))).rowcount
        return n == 1

    # ── атомарность записей части (NIGHT0710-B3v) ─────────────────────────────────────────────

    def _tx_begin(self):
        if not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")

    def _tx_end(self, ok=True):
        if self.db.in_transaction:
            self.db.execute("COMMIT" if ok else "ROLLBACK")

    def _our_wamid(self, wamid):
        """Эхо нашего — и PDF любой попытки (`pdf_parts`, `part_log`), не только черновик и outbox."""
        if super()._our_wamid(wamid):
            return True
        if not self.attach or not wamid:
            return False
        return (self.db.execute("SELECT 1 FROM pdf_parts WHERE wamid=?", (wamid,)).fetchone() is not None
                or self.db.execute("SELECT 1 FROM part_log WHERE wamid=?", (wamid,)).fetchone() is not None)

    def _attach(self, draft_id):
        return self.db.execute("SELECT file_id, name, size, sha256, row, reason FROM attach WHERE draft_id=?",
                               (draft_id,)).fetchone()

    def _basis(self, draft_id):
        """Основание PDF черновика: версия договора и ключ перечитывания (T4B3BASIS0510)."""
        row = self.db.execute("SELECT file_id, row, doc_id, signed_at, number, date_from, date_to FROM attach "
                              "WHERE draft_id=?", (draft_id,)).fetchone()
        if not row:
            return None
        return dict(zip(("file_id", "row", "doc_id", "signed_at", "number", "date_from", "date_to"), row))

    def _recheck(self, draft_id, number):
        """Живое чтение реестра перед отправкой → (True, "") | (False, причина). Дверь упала или её нет — отказ."""
        basis = self._basis(draft_id) or {}
        if not callable(self.contract_find):
            return False, "двери contract_find нет — реестр не перечитан"
        try:
            got = self.contract_find(phone=str(basis.get("number") or number or ""),
                                     date_from=str(basis.get("date_from") or ""), date_to=str(basis.get("date_to") or ""))
        except Exception as e:                                       # noqa: BLE001
            return False, "дверь contract_find упала: %s" % type(e).__name__
        try:
            return recheck_of(got, basis)
        except Exception as e:                                       # noqa: BLE001
            return False, "ответ реестра не разобран (%s)" % type(e).__name__

    def _part(self, draft_id):
        return self.db.execute("SELECT state, attempt, who, at, wamid, reason, sending_at FROM pdf_parts "
                               "WHERE draft_id=?", (draft_id,)).fetchone()

    def _plog(self, draft_id, part, attempt, who, now, outcome, wamid=None, sha=None, reason=""):
        self.db.execute("INSERT INTO part_log(draft_id, part, attempt, who, at, outcome, wamid, sha256, reason) "
                        "VALUES(?,?,?,?,?,?,?,?,?)", (draft_id, part, int(attempt), who, now, outcome, wamid, sha,
                                                      str(reason or "")[:300]))
        self.log("черновик %d: часть %s, попытка %d, %s → %s%s%s" % (
            draft_id, part, int(attempt), who, outcome, ", wamid есть" if wamid else "",
            ", sha256 %s…" % sha[:12] if sha else ""))

    # ── черновик: итог сверки → вложение или причина ───────────────────────────────────────

    def make_drafts(self, now):
        made = super().make_drafts(now)
        if not self.attach:
            return made
        for did in made:
            self._attach_decide(did, now)           # обычно уже решено до карточки (`_card_new`) — тогда не трогает
        self._seen.clear()
        return made

    def _card_new(self, draft_id, ver, now):
        """Вложение решается ДО первой карточки (второй круг, R01): карточка обязана назвать PDF, который уйдёт по её
        «Отправить», а ядро шлёт её изнутри `make_drafts`, раньше, чем там легла бы строка `attach`. Версия по пояснению
        (Д2) — так же: итог ЕЁ сверки ложится до её карточки (ядро шлёт её изнутри `make_hint_versions`)."""
        if self.attach and int(ver) == 1:
            self._attach_decide(draft_id, now)
        elif self.attach and self.hint_of(draft_id, int(ver)) is not None:
            self._attach_decide(draft_id, now, ver=int(ver))
        return super()._card_new(draft_id, ver, now)

    def _ver_checked(self, draft_id, ver):
        """Сверка ЭТОЙ версии по пояснению записана (Д2): строка `attach` черновика несёт её номер."""
        return self.db.execute("SELECT 1 FROM attach WHERE draft_id=? AND ver=?",
                               (draft_id, int(ver))).fetchone() is not None

    def _attach_decide(self, did, now, ver=None):
        """Итог сверки черновика → строка `attach` (вложение или причина). Строка уже есть или сверки не было — ничего.
        Тот же договор (sha256) этому номеру уже уходил или мог уйти — вложения нет, причина словами (R03).
        ver — версия по пояснению (Д2): итог ЕЁ сверки (ключ HINT_SEEN) заменяет строку черновика и метит её номером
        версии (`attach.ver`); сверки этой версии не было — строка не трогается, версия остаётся «без сверки»."""
        if ver is None and self._attach(did) is not None:
            return
        row = self.db.execute("SELECT number, upto_id FROM drafts WHERE id=?", (did,)).fetchone()
        if not row:
            return
        number, upto = row
        seen = self._seen.pop((number, upto) if ver is None else (HINT_SEEN, number, upto), None)
        if seen is None:
            if ver is not None:
                self.log("черновик %d: версия %d по пояснению без сверки Т4а — «Отправить» её снимет" % (did, ver))
            return                                  # сверки не было: строки нет — «без сверки»
        out, since = seen
        meta, why = attach_of(out, since)           # опора судьи: sift с since = последнее входящее (T4B3BASIS0510)
        if meta:
            twin = self._pdf_twin(number, meta["sha256"], did)
            if twin:
                meta, why = None, W_TWIN % (twin[2][:12], twin[0], twin[1])
        m = meta or {}
        opora = opora_of(out, since)                # K3-FIX F1: опора для карточки — из того же итога сверки, мост не зовётся
        self.db.execute("INSERT OR REPLACE INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, "
                        "reason, ts, signed_at, number, date_from, date_to, opora) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (did, m.get("file_id"), m.get("name"), m.get("size"), m.get("sha256"), m.get("row"),
                         m.get("doc_id"), why or None, now, m.get("signed_at"), number if meta else None,
                         m.get("date_from"), m.get("date_to"), opora))
        if ver is not None:                         # Д2: строка — итог сверки ЭТОЙ версии по пояснению
            self.db.execute("UPDATE attach SET ver=? WHERE draft_id=?", (int(ver), did))
        self.log("черновик %d: вложение %s%s" % (
            did, "PDF договора, sha256 %s…" % m["sha256"][:12] if meta else "нет — %s" % why,
            " (сверка версии %d по пояснению)" % ver if ver is not None else ""))

    def _pdf_twin(self, number, sha, draft_id):
        """Тот же PDF (sha256) этому номеру в ДРУГОМ черновике уже ушёл или мог уйти → (черновик, состояние, sha256) |
        None. «Мог уйти» (неизвестно, захват, посреди двери) — тоже: второй экземпляр вслепую не шлём (R03)."""
        if not sha:
            return None
        row = self.db.execute("SELECT p.draft_id, p.state, a.sha256 FROM pdf_parts p JOIN drafts d ON d.id=p.draft_id "
                              "JOIN attach a ON a.draft_id=p.draft_id WHERE d.number=? AND a.sha256=? "
                              "AND p.draft_id<>? AND p.state IN (?,?,?,?) ORDER BY p.draft_id DESC LIMIT 1",
                              (number, sha, int(draft_id), A.SENT, A.UNSURE, A.SENDING, P_CLAIMED)).fetchone()
        return tuple(row) if row else None

    def card_pdf(self, draft_id, ver):
        """Строка карточки о PDF (второй круг, R01/R02): «Отправить» шлёт договор — карточка обязана это сказать, на
        КАЖДОЙ версии (правка человека PDF не снимает). Вложения нет по делу (договор сверялся) — почему. Иначе None.
        Версия по пояснению (Д2) — строка итога ЕЁ сверки всегда (`_hint_card`)."""
        if not self.attach:
            return None
        meta = self._attach(draft_id)
        if self.hint_of(draft_id, int(ver)) is not None:
            return self._hint_card(draft_id, int(ver), meta)
        if not meta:
            return None
        file_id, name, size, _sha, row, why = meta
        if not file_id:
            why = str(why or "")
            if not why or why.startswith(W_NO_ATTACH_QUIET):
                return None
            return "📄 PDF не приложен: %s" % why[:180]
        line = "📄 «Отправить» шлёт ВТОРЫМ сообщением подписанный PDF договора: %s · %s · строка реестра %s" % (
            name, _size_words(size), row if row is not None else "—")
        if int(ver) > 1:
            line += " — текст правил человек, договор уйдёт всё равно; не нужен — «Не нужно» и ответ с телефона"
        return line

    def _hint_card(self, draft_id, ver, meta):
        """Строка карточки версии по пояснению (Д2): итог ЕЁ сверки Т4а — PDF уйдёт (имя · размер · строка реестра) ·
        PDF не приложен и почему · сверки нет («Отправить» снимет версию, правила не будет). Текст версии писал агент, а
        не человек, — оговорки «текст правил человек» здесь нет."""
        if not meta or not self._ver_checked(draft_id, ver):
            return W_HINT_CHECK_NONE % ver
        file_id, name, size, _sha, row, why = meta
        if file_id:
            said = W_HINT_CHECK_PDF % (name, _size_words(size), row if row is not None else "—")
        else:
            said = W_HINT_CHECK_NOPDF % str(why or "причина не названа")[:180]
        return W_HINT_CHECK % (ver, said)

    def card_basis(self, draft_id, ver):
        """Опора черновика на карточке (K3-FIX F1) → текст | None. Опора записана при сверке (`attach.opora`, итог
        `opora_of`): по каждому ответу инструмента в опоре судьи — источник, время чтения, версия от источника или
        «неизвестна». Флаг выкл или сверки не было (строки `attach` нет) — None: карточка прежняя. Версия по пояснению
        без своей сверки — None: карточка уже говорит «сверки нет», чужую опору ей не приписываем."""
        if not self.attach:
            return None
        if self.hint_of(draft_id, int(ver)) is not None and not self._ver_checked(draft_id, int(ver)):
            return None
        row = self.db.execute("SELECT opora FROM attach WHERE draft_id=?", (draft_id,)).fetchone()
        if not row:
            return None
        return row[0] if row[0] else OPORA_LEGACY

    # ── нажатие ───────────────────────────────────────────────────────────────────────────

    def press(self, draft_id, ver, action, who, now=None, who_id=None):
        # who_id — id нажавшего (NIGHT0710-B2): пробрасывается ядру, иначе руки уронили бы нажатие TypeError'ом молча
        if not self.attach:
            return super().press(draft_id, ver, action, who, now, who_id=who_id)
        now = self.clock() if now is None else now
        if action == ACT_REBUILD:
            return self.rebuild(draft_id, ver, who, now)
        if action in (ACT_PDF, ACT_PDF_RISK):
            return self.press_pdf(draft_id, ver, who, now, permit=action == ACT_PDF_RISK)
        # напоминание (WAFOLLOWUP0210) сверкой Т4а не строится никогда — замок «без сверки» его не касается
        # A15 (NIGHT0710-B2, круг 2) → Д2 (INTEG0710): строка attach ключуется черновиком; версия по пояснению «со
        # сверкой», только если записана сверка ЭТОЙ версии (`attach.ver`, такт до её карточки) — иначе она идёт под тот
        # же замок «без сверки», что и черновик без строки attach
        hint_ver = self.hint_of(draft_id, int(ver)) is not None
        unchecked = self._attach(draft_id) is None or (hint_ver and not self._ver_checked(draft_id, int(ver)))
        if action == A.ACT_SEND and unchecked and self.draft_kind(draft_id) != A.KIND_FOLLOW:
            n = self.db.execute("UPDATE drafts SET state=?, reason=?, closed_at=? WHERE id=? AND state=? AND ver=?",
                                (A.STALE, W_NO_CHECK, now, draft_id, A.PENDING, int(ver))).rowcount
            if n != 1:
                return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
            self.log("черновик %d → stale: без сверки при WA_AGENT_ATTACH" % draft_id)
            self._done(draft_id, W_NO_CHECK, now)
            return {"ok": False, "state": A.STALE, "words": W_NO_CHECK}
        return super().press(draft_id, ver, action, who, now, who_id=who_id)

    def hint(self, draft_id, ver, text, who, who_id=None, msg_id=None, now=None):
        """Д2 (INTEG0710; было A15 NIGHT0710-B2): при WA_AGENT_ATTACH пояснение принимается, когда версия по нему пройдёт
        ту же сверку Т4а, что версия модели (пояснения включены, модель сверку умеет — `_Probe.hint_check`): версию со
        сверкой сделает такт. Иначе — не принимается словами сразу, а не после вызова модели и устаревания на
        «Отправить» (как до Д2)."""
        if self.attach and not (self.hints and self._hint_checkable()):
            return {"ok": False, "words": W_HINT_NO_CHECK}
        return super().hint(draft_id, ver, text, who, who_id=who_id, msg_id=msg_id, now=now)

    def _hint_checkable(self):
        """Модель (обёртка `_Probe`) умеет версию по пояснению со сверкой Т4а. Пробы нет или она упала — не умеет."""
        probe = getattr(self.model, "hint_check", None)
        try:
            return bool(probe()) if callable(probe) else False
        except Exception:                                            # noqa: BLE001
            return False

    def make_hint_versions(self, now):
        """Версии по пояснениям — такт ядра (NIGHT0710-B2); при WA_AGENT_ATTACH каждая — со сверкой Т4а (`_Probe.redraft`),
        итог ложится до её карточки (`_card_new`). Итоги сверки версий, не дошедших до карточки (клиент написал ещё,
        черновик снят), такт не переживают (Д2)."""
        try:
            return super().make_hint_versions(now)
        finally:
            for key in [k for k in self._seen if len(k) == 3 and k[0] == HINT_SEEN]:
                self._seen.pop(key, None)

    def rebuild(self, draft_id, ver, who, now=None):
        """«Пересобрать со сверкой»: ждущий черновик superseded тем же захватом, новый проход Т4а → новый черновик."""
        now = self.clock() if now is None else now
        n = self.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=?, closed_at=?, reason=? "
                            "WHERE id=? AND state=? AND ver=?",
                            (A.SUPERSEDED, who, now, now, "пересобран со сверкой", draft_id, A.PENDING,
                             int(ver))).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        number = self.db.execute("SELECT number FROM drafts WHERE id=?", (draft_id,)).fetchone()[0]
        self.db.execute("UPDATE clients SET next_try=0 WHERE number=?", (number,))
        made = self.make_drafts(now)
        new = self.db.execute("SELECT id FROM drafts WHERE number=? AND state=? AND id>?",
                              (number, A.PENDING, draft_id)).fetchone()
        words = ("пересобран: новый черновик %d со сверкой" % new[0] if new else
                 "пересобирается: модель не дала черновика — новый придёт карточкой")
        self.log("черновик %d → superseded (пересобрать со сверкой, %s); новых черновиков %d" % (
            draft_id, who, len(made)))
        self._done(draft_id, "%s — %s, %s" % (words, who, A.hm_phuket(now)), now)
        return {"ok": True, "state": A.SUPERSEDED, "words": words, "new": new[0] if new else None}

    def _done(self, draft_id, words, now):
        if self._hold == draft_id:
            self._held = words                      # исход ляжет на карточку одной правкой — после записи части
            return
        super()._done(draft_id, words, now)

    def _tg(self, method, *args):
        # INTEG0710 (Б3в × Б3г): окно 24 ч закрылось у ворот двери ВНУТРИ текстовой части — ядро вернуло черновик в
        # pending и правит карточку «📨 Отправить шаблоном» (`Core._deliver` → `_send_closed`); правка ложится после
        # COMMIT части (`_text_part`), как итог `_done`: Telegram в транзакции не зовётся
        if self._hold is not None and method == "card_tpl":
            self._held_tg = (method, args)
            return None
        return super()._tg(method, *args)

    def _text_part(self, draft_id, number, upto, text, who, now, from_state):
        """Текстовая часть (дверь ядра) + строка журнала части — ОДНОЙ транзакцией после ответа двери (`_TxDoor`).
        Итог на карточку ядро не пишет (`_hold`): его слова — в `self._held`, Telegram в транзакции не зовётся;
        правка «📨» ядра (окно закрылось у ворот двери, INTEG0710) — в `self._held_tg`, ложится после COMMIT.
        Исключение после ответа двери — откат: часть осталась sending, старт скажет «неизвестно», повтора нет."""
        inner, self._hold, self._held, self._held_tg = self.door, draft_id, None, None
        self.door = _TxDoor(inner, self._tx_begin, self.log)
        try:
            res = super()._deliver(draft_id, number, upto, text, who, now, from_state)
            self._plog(draft_id, "text", 1, who, now, res.get("state") or "?", self._wamid(draft_id))
            self._tx_end()
        except Exception:                                            # noqa: BLE001
            self._tx_end(ok=False)
            raise
        finally:
            self.door, self._hold = inner, None
        # правка ядра, отложенная до COMMIT (INTEG0710, Б3в × Б3г); откат части (исключение выше) её не кладёт
        held, self._held_tg = self._held_tg, None
        if held:
            super()._tg(held[0], *held[1])
        return res

    def _deliver(self, draft_id, number, upto, text, who, now, from_state):
        if not self.attach:
            return super()._deliver(draft_id, number, upto, text, who, now, from_state)
        meta = self._attach(draft_id)
        ver0 = self.db.execute("SELECT ver FROM drafts WHERE id=?", (draft_id,)).fetchone()   # K3-FIX N2: версия нажатия
        ver0 = ver0[0] if ver0 else None
        if meta and meta[0]:
            twin = self._pdf_twin(number, meta[3], draft_id)    # тот же договор успел уйти другим черновиком (R03)
            if twin:
                self.db.execute("UPDATE attach SET file_id=NULL, reason=? WHERE draft_id=?",
                                (W_TWIN % (twin[2][:12], twin[0], twin[1]), draft_id))
                self.log("черновик %d: PDF снят при нажатии — тот же договор уже уходил (черновик %d, PDF: %s)" % (
                    draft_id, twin[0], twin[1]))
                meta = self._attach(draft_id)
        if not meta or not meta[0]:
            res = self._text_part(draft_id, number, upto, text, who, now, from_state)
            tstate = res.get("state")
            if tstate in (A.SENT, A.NOT_SENT, A.UNSURE):
                # K3-FIX N1: исход двери — словами (словарь `state_word`), а не кодом ядра «sent/unsure/not_sent»;
                # перечитан из базы, как у двух частей (N2): проигранный захват — слова по базе, карточку, уже решённую
                # другим процессом (старт второго экземпляра), поздний ответ не перекрывает
                words, card, fresh, tnow, _p = self._settled(draft_id, ver0, tstate, None, "", 1, keep_decided=True)
                if fresh:
                    super()._done(draft_id, "%s — %s, %s" % (card, who, A.hm_phuket(now)), now)
                return dict(res, words=words, parts={"text": tnow, "pdf": None})
            if self._held is not None:              # слова ядра — те же, что легли бы без транзакции
                super()._done(draft_id, self._held, now)
            return res
        ok, why = self._recheck(draft_id, number)   # реестр перечитан ДО текстовой части (T4B3BASIS0510)
        if not ok:
            words = W_BASIS % why
            if not self._close(draft_id, A.STALE, words, now, from_states=(from_state,)):
                return {"ok": False, "state": None, "words": self._decided(draft_id)}
            self.log("черновик %d → stale: основание PDF не подтверждено реестром при нажатии — ничего не отправлено"
                     % draft_id)
            return {"ok": False, "state": A.STALE, "words": words}
        self.db.execute("INSERT OR IGNORE INTO pdf_parts(draft_id, state, attempt) VALUES(?,?,1)", (draft_id, P_WAIT))
        res = self._text_part(draft_id, number, upto, text, who, now, from_state)
        tstate = res.get("state")
        if tstate is None:                          # захват sending проигран — решил другой; часть ждёт его исхода
            return res
        if tstate == A.PENDING:
            # INTEG0710 (Б3в × Б3г): окно 24 ч закрылось между пробой ядра и воротами двери — ядро вернуло черновик в
            # pending, на карточке «📨 Отправить шаблоном». Текст не решён: часть PDF ждёт его (wait, попытка 1 — как у
            # старта), исход обеих частей на карточку не пишется — иначе правка сняла бы кнопки ждущего черновика
            return res
        if tstate != A.SENT:
            why = W_TEXT_UNSURE if tstate == A.UNSURE else W_TEXT_NOT

            def write():
                self.db.execute("UPDATE pdf_parts SET state=?, reason=?, who=?, at=? WHERE draft_id=? AND state=?",
                                (A.NOT_SENT, why, who, now, draft_id, P_WAIT))
                self._plog(draft_id, "pdf", 1, who, now, A.NOT_SENT, reason=why)
            self._in_tx(write)
            pstate, preason = A.NOT_SENT, why
        else:
            pstate, preason = self._send_pdf(draft_id, number, who, now, 1, (P_WAIT,), meta, prev=1)
        words, card, fresh, tnow, pnow = self._settled(draft_id, ver0, tstate, pstate, preason, 1, keep_decided=True)
        if fresh:
            self._done(draft_id, "%s — %s, %s" % (card, who, A.hm_phuket(now)), now)
        return dict(res, words=words, parts={"text": tnow, "pdf": pnow})

    def _settled(self, draft_id, ver0, tstate, pstate, preason, attempt, keep_decided=False):
        """K3-FIX N2: исход частей ПЕРЕЧИТЫВАЕТСЯ из базы после двери → (слова нажавшему, слова карточки, править ли
        карточку, текст, PDF). База совпала с ответом этого процесса (версия черновика, состояния обеих частей и номер
        попытки) — слова по ответу (`parts_words`), карточка правится, как раньше.
        Не совпала — захват проигран (второй экземпляр службы, конкурент): слова по ПЕРЕЧИТАННОМУ (`reread_words`):
        «не ушёл» — только при not_sent в базе, unsure — «исход неизвестен — не повторять, проверить». Карточку поздний ответ
        правит, только если версия черновика та же и номер попытки PDF не вырос; keep_decided — карточка, уже решённая
        другим процессом (исход старта второго экземпляра), не перекрывается.
        K3-FIX N1: слова — словарём `state_word` (без внутренних кодов); у текста — причина двери (`drafts.reason`), на
        карточке у ушедших частей — их wamid из базы."""
        row = self.db.execute("SELECT d.state, d.ver, p.state, p.attempt, p.reason, d.reason, d.wamid, p.wamid FROM drafts d "
                              "LEFT JOIN pdf_parts p ON p.draft_id=d.id WHERE d.id=?", (draft_id,)).fetchone()
        if not row:
            words = parts_words(tstate, pstate, preason)
            return words, words, True, tstate, pstate
        t_db, ver_db, p_db, att_db, why_db, twhy_db, tw_db, pw_db = row
        twhy_db = twhy_db or ""
        if (ver_db == ver0 and t_db == tstate and p_db == pstate
                and (att_db is None or int(att_db) == int(attempt))):
            return (parts_words(tstate, pstate, preason, text_reason=twhy_db),
                    parts_words(tstate, pstate, preason, text_reason=twhy_db, text_wamid=tw_db, pdf_wamid=pw_db),
                    True, tstate, pstate)
        words = "%s (%s)" % (reread_words(t_db, p_db, why_db, text_reason=twhy_db), W_LATE)
        card = "%s (%s)" % (reread_words(t_db, p_db, why_db, text_reason=twhy_db, text_wamid=tw_db, pdf_wamid=pw_db),
                            W_LATE)
        fresh = ver_db == ver0 and (att_db is None or int(att_db) <= int(attempt))
        if fresh and keep_decided:
            got = self.db.execute("SELECT state FROM card_out WHERE draft_id=? AND ver=?",
                                  (draft_id, int(ver_db))).fetchone()
            fresh = not (got and got[0] == A.CARD_DECIDED)
        self.log("черновик %d: ответ попытки %d опоздал — база: текст %s, PDF %s (попытка %s); карточку %s" % (
            draft_id, int(attempt), t_db, p_db, att_db, "правлю по базе" if fresh else
            "не трогаю: её уже решил другой процесс, версия или попытка новее"))
        return words, card, fresh, t_db, p_db

    def _said(self, draft_id, wamids=False):
        """Исход черновика словами по БАЗЕ (K3-FIX N1): текст (и PDF, если часть есть) — `parts_words`; черновик, решённый
        не дверью (не нужно, устарел, заменён, ждёт), — словом его состояния. wamids — для карточки."""
        row = self.db.execute("SELECT d.state, d.reason, d.wamid, p.state, p.reason, p.wamid FROM drafts d LEFT JOIN "
                              "pdf_parts p ON p.draft_id=d.id WHERE d.id=?", (draft_id,)).fetchone()
        if not row:
            return "черновика нет"
        tstate, treason, tw, pstate, preason, pw = row
        if tstate not in (A.SENT, A.NOT_SENT, A.UNSURE, A.SENDING):
            return state_word(tstate)
        return parts_words(tstate, pstate, preason, text_reason=treason or "",
                           text_wamid=tw if wamids else None, pdf_wamid=pw if wamids else None)

    def _decided(self, draft_id, ver=None):
        """«Уже решено» проигравшему (K3-FIX N1): при WA_AGENT_ATTACH исход — словами (`_said`), а не кодом состояния;
        порядок проверок и вид фразы — `Core._decided` (по-прежнему начинается с «уже решено» / «устарело»). Флаг выкл —
        ядро без изменений."""
        if not self.attach:
            return super()._decided(draft_id, ver)
        row = self.db.execute("SELECT state, decided_by, decided_at, closed_at, ver FROM drafts WHERE id=?",
                              (draft_id,)).fetchone()
        if not row:
            return "черновика нет"
        state, by, at, closed, ver_now = row
        if ver is not None and int(ver) != ver_now:
            return "устарело: версия %d, действует версия %d — %s" % (
                int(ver), ver_now, "жмите кнопки новой карточки" if state == A.PENDING else self._decided(draft_id))
        if by:
            return "уже решено: %s, %s — %s" % (by, A.hm_phuket(at), self._said(draft_id))
        return "уже решено: снят, %s — %s (версия %d)" % (A.hm_phuket(closed), self._said(draft_id), ver_now)

    def _wamid(self, draft_id):
        row = self.db.execute("SELECT wamid FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    # ── часть PDF ─────────────────────────────────────────────────────────────────────────

    def _send_pdf(self, draft_id, number, who, now, attempt, from_states, meta, permit=False, prev=None):
        """Захват части → байты из contract_pdf и сверка sha256 → sending ДО двери → дверь → исход. → (state, reason).
        Захват — сравнение-и-запись: состояние из `from_states` И номер попытки равен ожидаемому `prev` (номер на кнопке).
        Номер уже сменился (другое нажатие решило раньше) — строк 0, «уже решено», двери нет."""
        file_id, name, size, sha, row, _why = meta
        q = "UPDATE pdf_parts SET state=?, attempt=?, who=?, at=?, permit=?, reason=NULL WHERE draft_id=? " \
            "AND attempt=? AND state IN (%s)" % ",".join("?" * len(from_states))
        if self.db.execute(q, (P_CLAIMED, int(attempt), who, now, int(bool(permit)), draft_id, int(prev))
                           + tuple(from_states)).rowcount != 1:
            return None, "уже решено"

        def fail(why, outcome=A.NOT_SENT):
            def write():
                self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=?",
                                (outcome, why, draft_id, P_CLAIMED))
                self._plog(draft_id, "pdf", attempt, who, now, outcome, sha=sha, reason=why)
            self._in_tx(write)
            return outcome, why

        try:
            got = self.pdf_fetch(file_id) if self.pdf_fetch else {"ok": False, "error": "двери contract_pdf нет"}
        except Exception as e:                                       # noqa: BLE001
            got = {"ok": False, "error": "дверь contract_pdf упала: %s" % type(e).__name__}
        if not (isinstance(got, dict) and got.get("ok") and got.get("verified") is True):
            err = got.get("error") if isinstance(got, dict) else "ответ не словарь"
            return fail("PDF не получен из contract_pdf: %s" % (err or "без verified"))
        try:
            raw = base64.b64decode(got.get("content_b64") or "", validate=True)
        except Exception as e:                                       # noqa: BLE001
            return fail("PDF не декодирован: %s" % type(e).__name__)
        now_sha = hashlib.sha256(raw).hexdigest()
        if now_sha != sha:
            return fail("sha256 PDF при отправке %s… не равен sha256 сверки %s… — файл изменился, не отправлено" % (
                now_sha[:12], sha[:12]))
        # второй замок того же договора (NIGHT0710-B3v): мост назвал строку реестра — она обязана быть строкой сверки.
        # Не назвал — не судим (поле ответа необязательно); signed_at не сличается: его формат у contract_pdf не сверен
        have = got.get("row")
        if have not in (None, "") and row is not None and str(have).strip() != str(row).strip():
            return fail("строка реестра PDF при отправке %s, при сверке %s — договор сменился, не отправлено" % (
                str(have)[:20], str(row)[:20]))
        # K3-FIX F4: скелет PDF судится на ТЕХ ЖЕ байтах, что уйдут двери (`body` — его же отдаёт `media["fetch"]`), ДО
        # sending: не сошёлся — часть not_sent с причиной человеку, двери нет, повтора нет. Уровень — `PDF_LEVEL`
        body = raw
        shape_ok, shape_why = pdf_shape(body)
        if not shape_ok:
            self.log("черновик %d: PDF не прошёл проверку скелета (%s) — двери нет" % (draft_id, shape_why[:120]))
            return fail(W_PDF_SHAPE % shape_why)
        # ── sending ДО двери: рестарт после этой строки повтора не даст ──
        if self.db.execute("UPDATE pdf_parts SET state=?, sending_at=?, sha256=? WHERE draft_id=? AND state=?",
                           (A.SENDING, now, now_sha, draft_id, P_CLAIMED)).rowcount != 1:
            return None, "уже решено"
        media = {"kind": "document", "mime": PDF_MIME, "size": len(body), "filename": name, "caption": "",
                 "fetch": lambda cap: (body, "")}
        try:
            res = self.door.send_media(number, media) or {}
        except Exception as e:                                       # noqa: BLE001
            res = {"outcome": "unknown", "reason": "дверь упала: %s" % type(e).__name__}
        state = A._DOOR_STATE.get(res.get("outcome"), A.UNSURE)
        wamid = res.get("wamid") if state == A.SENT else None
        reason = A.relay_words(state, res) if state == A.NOT_SENT else str(res.get("reason") or "")[:300]

        def write():                                # исход части + outbox + журнал — одной транзакцией
            # ответ двери ЭТОЙ попытки сильнее «неизвестно», которое мог поставить старт второго экземпляра службы
            # посреди двери (R08): иначе wamid ушедшего PDF терялся, и «риск дубля» слал второй
            if self.db.execute("UPDATE pdf_parts SET state=?, reason=?, wamid=? WHERE draft_id=? AND attempt=? "
                               "AND state IN (?,?)", (state, reason, wamid, draft_id, int(attempt), A.SENDING,
                                                      A.UNSURE)).rowcount != 1:
                self.log("черновик %d: исход PDF попытки %d (%s) не лёг на часть — её решил другой процесс; "
                         "журнал и outbox пишутся" % (draft_id, int(attempt), state))
            if state == A.SENT:
                self._sent_out(wamid, number, "", A.VIA_AGENT, now, kind="document")
            self._plog(draft_id, "pdf", attempt, who, now, state, wamid, now_sha, reason)
        self._in_tx(write)
        return state, reason

    def _in_tx(self, write):
        """Записи одной транзакцией: все легли — COMMIT; исключение — ROLLBACK и наружу (не легло ничего).
        Транзакция не открылась (база занята) — записи без неё, как до NIGHT0710-B3v: исход двери не теряем."""
        try:
            self._tx_begin()
        except Exception as e:                                       # noqa: BLE001
            self.log("транзакция части не открылась (%s) — запись без неё" % type(e).__name__)
            return write()
        try:
            out = write()
            if not self._tx_commit():               # COMMIT не прошёл (база занята) — откат и запись без транзакции
                return write()
            return out
        except Exception:                                            # noqa: BLE001
            self._tx_end(ok=False)
            raise

    def _tx_commit(self):
        """COMMIT записи части → True. Упал (база занята дольше busy-таймаута) → откат, строка журнала, False: ответ
        двери уже получен, и подтверждённый провайдером wamid теряться не должен (второй круг, R21) — вызывающий
        пишет то же самое без транзакции, как при неоткрывшейся."""
        try:
            self._tx_end()
            return True
        except Exception as e:                                       # noqa: BLE001
            self.log("COMMIT части не прошёл (%s) — откат, запись без транзакции: исход двери не теряем"
                     % type(e).__name__)
            try:
                self._tx_end(ok=False)
            except Exception:                                        # noqa: BLE001
                pass
            return False

    def delivery_check(self, number, wamid):
        """Статусы провайдера по ТОЧНОМУ wamid попытки → (исход, слова). Исходы: delivered (delivered/read) ·
        accepted (только sent: «принято WhatsApp», не доставка) · unknown (wamid нет, статуса нет, не прочитано).
        Без wamid попытки подтверждать нечем: чужой статус этой попытке не принадлежит никогда."""
        if not wamid:
            return D_UNKNOWN, "у попытки нет wamid — статусом её не подтвердить"
        words = set()
        if self.attach:                             # сохранённые по точной части (NIGHT0710-B3v)
            words |= {str(w or "").strip().lower() for (w,) in self.db.execute(
                "SELECT status FROM part_status WHERE wamid=?", (wamid,)).fetchall()}
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT text FROM wa_inbox WHERE wamid=? AND from_number=? AND msg_type='status'",
                                 (wamid, number)).fetchall()
                if _has_table(q, "wa_status"):      # квитанции вебхука: все статусы wamid, а не первый
                    rows += q.execute("SELECT status FROM wa_status WHERE wamid=? AND recipient=?",
                                      (wamid, number)).fetchall()
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            if not words:
                return D_UNKNOWN, "статусы провайдера не прочитаны (%s)" % type(e).__name__
            rows = []
        words |= {str(w or "").strip().lower() for (w,) in rows}
        hit = [w for w in STATUS_DELIVERED if w in words]
        if hit:
            return D_DELIVERED, "доставлен (статус %s по wamid попытки)" % hit[-1]
        if STATUS_FAILED in words:
            return D_FAILED, "провайдер не доставил (статус failed по wamid попытки)"
        if STATUS_ACCEPTED in words:
            return D_ACCEPTED, "принято WhatsApp (статус sent по wamid попытки) — доставка не подтверждена"
        return D_UNKNOWN, "статуса по wamid попытки нет"

    def collect_statuses(self, now):
        """Поздние статусы по ТОЧНОЙ части (NIGHT0710-B3v): каждый wamid части из `part_log` (текст и каждая попытка
        PDF, не старше STATUS_DAYS) → его статусы из очереди (`wa_inbox` — первый на wamid) и из квитанций вебхука
        (`wa_status` — все). Получатель статуса обязан быть номером черновика; чужой wamid не берётся вовсе.
        → число сохранённых этим вызовом · None — очередь не прочитана (хранимое не трогается)."""
        if not self.attach:
            return 0
        ours = {}
        for did, part, att, wamid, number in self.db.execute(
                "SELECT l.draft_id, l.part, l.attempt, l.wamid, d.number FROM part_log l JOIN drafts d "
                "ON d.id=l.draft_id WHERE l.wamid IS NOT NULL AND l.at >= ?",
                (float(now) - STATUS_DAYS * 86400,)).fetchall():
            ours[wamid] = (did, part, att, number)
        if not ours:
            return 0
        found = []
        try:
            q = self._queue()
            try:
                status_table = _has_table(q, "wa_status")
                keys = sorted(ours)
                for i in range(0, len(keys), 200):
                    chunk = keys[i:i + 200]
                    marks = ",".join("?" * len(chunk))
                    found += [r + ("wa_inbox",) for r in q.execute(
                        "SELECT wamid, text, from_number, COALESCE(ts_msg, ts_queued) FROM wa_inbox "
                        "WHERE msg_type='status' AND wamid IN (%s)" % marks, chunk).fetchall()]
                    if status_table:
                        found += [r + ("wa_status",) for r in q.execute(
                            "SELECT wamid, status, recipient, COALESCE(ts_msg, ts_queued) FROM wa_status "
                            "WHERE wamid IN (%s)" % marks, chunk).fetchall()]
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            self.log("статусы частей не прочитаны: %s" % type(e).__name__)
            return None
        n = 0
        failed = []
        for wamid, word, who, ts, src in found:
            word = str(word or "").strip().lower()
            did, part, att, number = ours[wamid]
            if word not in STATUS_KEEP or not who or who != number:
                continue
            got = self.db.execute("INSERT OR IGNORE INTO part_status(wamid, status, part, draft_id, attempt, ts, seen, "
                                  "src) VALUES(?,?,?,?,?,?,?,?)", (wamid, word, part, did, int(att), ts, now,
                                                                    src)).rowcount
            n += got
            if got and word == STATUS_FAILED and part == "pdf":
                failed.append((did, int(att), wamid))
        if n:
            self.log("статусы частей: сохранено %d" % n)
        for did, att, wamid in failed:              # failed PDF не молчит (второй круг, R10d): на карточку и «Дослать»
            why = W_FAILED % att
            if self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND attempt=? AND wamid=? "
                               "AND state=?", (A.NOT_SENT, why, did, att, wamid, A.SENT)).rowcount == 1:
                self._plog(did, "pdf", att, W_PROVIDER, now, A.NOT_SENT, wamid, reason=why)
                self._card_settle(did, now, W_PROVIDER)
        return n

    def tick(self, now=None):
        now = self.clock() if now is None else now
        made = super().tick(now)
        if self.attach and (self._status_last is None or now - self._status_last >= STATUS_EVERY):
            self._status_last = now
            try:
                self.collect_statuses(now)
            except Exception as e:                                   # noqa: BLE001
                self.log("статусы частей упали: %s" % type(e).__name__)
        return made

    def card_buttons(self, draft_id):
        """Кнопки исхода карточки (рукам Telegram, `card_done`) → [(надпись, действие, черновик, попытка)]. Текст ушёл,
        PDF не ушёл — «Дослать PDF»; PDF «неизвестно» — ещё «Дослать PDF — риск дубля». На кнопке номер ПОПЫТКИ:
        устаревшая ответит «уже решено». Иначе — пусто: кнопки снимаются, как у ядра."""
        if not self.attach:
            return []
        row = self.db.execute("SELECT state FROM drafts WHERE id=?", (draft_id,)).fetchone()
        part, meta = self._part(draft_id), self._attach(draft_id)
        if not row or row[0] != A.SENT or not part or not meta or not meta[0] or part[0] not in (A.NOT_SENT, A.UNSURE):
            return []
        out = [("📄 Дослать PDF", ACT_PDF, int(draft_id), int(part[1]))]
        if part[0] == A.UNSURE:
            out.append(("⚠️ Дослать PDF — риск дубля", ACT_PDF_RISK, int(draft_id), int(part[1])))
        return out

    def _foreign_after(self, number, since):
        """Статусы НЕИЗВЕСТНЫХ нам сообщений этого номера после попытки → список wamid; None — не прочитаны.
        Наши wamid (черновики, outbox, PDF) — не они. Это не подтверждение доставки, а улика возможного дубля."""
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT wamid, text FROM wa_inbox WHERE from_number=? AND msg_type='status' "
                                 "AND COALESCE(ts_msg, ts_queued) >= ? ORDER BY id",
                                 (number, float(since or 0) - STATUS_SKEW)).fetchall()
            finally:
                q.close()
        except Exception:                                            # noqa: BLE001
            return None
        out = []
        for wamid, word in rows:
            if not wamid or str(word or "").strip().lower() not in STATUS_ANY:
                continue
            if self._our_wamid(wamid) or self.db.execute("SELECT 1 FROM pdf_parts WHERE wamid=?",
                                                         (wamid,)).fetchone():
                continue
            out.append(wamid)
        return out

    def press_pdf(self, draft_id, attempt, who, now=None, permit=False):
        """«Дослать PDF» (attempt — номер попытки на кнопке). → {"ok", "state", "words"}."""
        now = self.clock() if now is None else now
        row = self.db.execute("SELECT number, state FROM drafts WHERE id=?", (draft_id,)).fetchone()
        part, meta = self._part(draft_id), self._attach(draft_id)
        if not row or not part or not meta or not meta[0]:
            return {"ok": False, "state": None, "words": "у черновика нет PDF-части"}
        number, tstate = row
        pstate, patt, pwho, pat, _wamid, preason, psend = part
        if int(attempt) != patt or pstate not in (A.NOT_SENT, A.UNSURE):
            return {"ok": False, "state": pstate, "words": "уже решено: PDF — %s, %s, попытка %d%s" % (
                pwho or "—", A.hm_phuket(pat) if pat else "—", patt,
                " — %s" % state_word(pstate, preason, pdf=True))}          # K3-FIX N1: словом, а не кодом
        if tstate != A.SENT:
            return {"ok": False, "state": pstate, "words": "дослать нельзя: %s" % (
                W_TEXT_UNSURE if tstate == A.UNSURE else W_TEXT_NOT)}
        held = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
        if held and held[0]:                        # человек ведёт беседу с телефона — как у «Отправить» (R17)
            self.log("черновик %d: «Дослать PDF» — клиент на паузе, PDF не ушёл" % draft_id)
            return {"ok": False, "state": pstate, "words": W_PAUSED}
        twin = self._pdf_twin(number, meta[3], draft_id)
        if twin:                                    # тот же договор ушёл (или мог уйти) другим черновиком (R03)
            self.log("черновик %d: «Дослать PDF» — тот же договор уже уходил (черновик %d, PDF: %s)" % (
                draft_id, twin[0], twin[1]))
            return {"ok": False, "state": pstate, "words": "дослать нельзя: " + W_TWIN % (twin[2][:12], twin[0],
                                                                                        twin[1])}
        if pstate == A.UNSURE:
            verdict, extra = self.delivery_check(number, _wamid)
            if verdict in (D_DELIVERED, D_ACCEPTED):
                # статус ТОЧНОГО wamid этой попытки: WhatsApp сообщение взял — PDF sent, повтор был бы дублем
                def confirm():                      # исход + outbox + журнал — одной транзакцией
                    if self.db.execute("UPDATE pdf_parts SET state=?, reason=? WHERE draft_id=? AND state=? "
                                       "AND attempt=?", (A.SENT, extra, draft_id, A.UNSURE, patt)).rowcount != 1:
                        return False
                    self._sent_out(_wamid, number, "", A.VIA_AGENT, now, kind="document")
                    self._plog(draft_id, "pdf", patt, who, now, A.SENT, _wamid, reason="сверка статусов: %s" % verdict)
                    return True
                if not self._in_tx(confirm):
                    return {"ok": False, "state": None, "words": "уже решено"}
                words = parts_words(A.SENT, A.SENT) + " (%s) — дослать нельзя" % extra
                card = self._said(draft_id, wamids=True) + " (%s) — дослать нельзя" % extra   # K3-FIX N1: с wamid
                self._done(draft_id, "%s — %s, %s" % (card, who, A.hm_phuket(now)), now)
                return {"ok": False, "state": A.SENT, "words": words, "delivery": verdict}
            foreign = self._foreign_after(number, psend)
            if foreign is None:
                why = "статусы провайдера не прочитаны"
                self.log("черновик %d: «Дослать PDF» — %s, дослать нельзя" % (draft_id, why))
                return {"ok": False, "state": A.UNSURE, "words": "%s — дослать нельзя, PDF: неизвестно" % why}
            if foreign:
                self.log("черновик %d: «Дослать PDF» — после попытки статусы неизвестных сообщений: %d, "
                         "PDF неизвестно, дослать нельзя" % (draft_id, len(foreign)))
                return {"ok": False, "state": A.UNSURE, "words": W_FOREIGN % len(foreign), "delivery": D_UNKNOWN}
            if not permit:
                self.log("черновик %d: «Дослать PDF» — доставка не подтверждена, нужен явный повтор" % draft_id)
                return {"ok": False, "state": A.UNSURE, "words": W_RISK, "need_permit": True}
        if not self._door_open():                   # дверь WA_SEND закрыта — ДО моста и захвата (как у «Отправить»)
            self.log("черновик %d: «Дослать PDF» — отправка выключена, часть ждёт" % draft_id)
            return {"ok": False, "state": pstate, "words": W_DOOR_OFF}
        ok, basis_why = self._recheck(draft_id, number)     # реестр перечитан ДО PDF (T4B3BASIS0510)
        if not ok:
            self.log("черновик %d: «Дослать PDF» — основание не подтверждено реестром, PDF не ушёл" % draft_id)
            return {"ok": False, "state": pstate, "words": W_BASIS_PDF % basis_why}
        ver0 = self.db.execute("SELECT ver FROM drafts WHERE id=?", (draft_id,)).fetchone()   # K3-FIX N2
        ver0 = ver0[0] if ver0 else None
        pstate2, why = self._send_pdf(draft_id, number, who, now, patt + 1, (pstate,), meta, permit=permit,
                                      prev=int(attempt))
        if pstate2 is None:
            return {"ok": False, "state": None, "words": "уже решено: PDF — повтор уже идёт"}
        # K3-FIX N2: исход попытки перечитан; поздний ответ (попытка или версия новее) карточку не правит
        words, card, fresh, _tnow, pnow = self._settled(draft_id, ver0, A.SENT, pstate2, why, patt + 1)
        if fresh:
            self._done(draft_id, "%s — дослал %s, %s%s" % (card, who, A.hm_phuket(now),
                                                            " (риск дубля принят)" if permit else ""), now)
        return {"ok": pnow == A.SENT, "state": pnow, "words": words}

    def parts(self, draft_id):
        """Исходы частей черновика → {"text": state, "pdf": state | None, "words": …}."""
        row = self.db.execute("SELECT state, reason FROM drafts WHERE id=?", (draft_id,)).fetchone()
        part = self._part(draft_id) if self.attach else None
        t = row[0] if row else None
        out = {"text": t, "pdf": part[0] if part else None,
               "words": parts_words(t, part[0] if part else None, part[5] if part else "",
                                    text_reason=(row[1] or "") if row else None)}
        if part:
            # «ушёл» — дверь приняла; доставку говорит ТОЛЬКО статус wamid этой попытки (sent — «принято WhatsApp»)
            num = self.db.execute("SELECT number, wamid FROM drafts WHERE id=?", (draft_id,)).fetchone()
            out["delivery"] = self.delivery_check(num[0] if num else None, part[4])
            out["text_delivery"] = self.delivery_check(num[0] if num else None, num[1] if num else None)
        return out


def _size_words(size):
    try:
        size = int(size)
    except (TypeError, ValueError):
        return "размер ?"
    if size < 1024:
        return "%d Б" % size
    if size < 1024 * 1024:
        return "%.0f КБ" % (size / 1024.0)
    return "%.1f МБ" % (size / 1024.0 / 1024.0)


def _has_table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def make_core(env, *args, pdf_fetch=None, contract_find=None, **kw):
    """Флаг выкл — прежний `Core` (24ad256); вкл — `AttachCore` с дверью байтов PDF и дверью реестра договоров."""
    if not enabled(env):
        return A.Core(*args, **kw)
    return AttachCore(*args, attach=True, pdf_fetch=pdf_fetch, contract_find=contract_find, **kw)
