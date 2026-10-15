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
(K3-FIX шаг 3q, `attach_of`). PDF модель не звала, а договор привязан кодом, — `contract_pdf` по `pdf_id` этого
договора читает сам код той же дверью (K3-FIX шаг 3r, `AttachCore._code_pdf`). Иначе вложения нет, и черновик хранит
ПРИЧИНУ словами. В базе — только метаданные (id, имя, размер, sha256, строка реестра); байты PDF берутся из `contract_pdf`
в момент отправки.

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

КАРТОЧКА ПОСЛЕ ПОДПИСИ (SIGNEDCARD1410; выключатель службы WA_AGENT_SIGNED_CARD, по умолчанию выкл; `signed=True` —
только при attach и дверях contract_find, pdf_fetch и аренды — дверь `rental` (и `case` при деле аренды) берётся у модели
ТЕМ ЖЕ способом, что у её сверки: `model._tool_doors(номер, …)`). Такт (`make_signed_cards`, не чаще SIGNED_EVERY) ищет
клиентов без паузы с последним входящим в окне 24 ч минус запас (правило напоминания `Core._follow_due`), без
claimed/sending и после тишины ядра (`quiet` — первым на последнее входящее отвечает модель, её PDF может «покрыть»
версию): аренда и договор читаются `T.call_tool` с контекстом номера (тот же код привязки, что у модели; второго поиска
без срока нет — фактом он не бывает), PDF — `_code_pdf`, итог — `attach_of` по договору, привязанному кодом (путь
реальной модели `contract {}`). Версия = (номер, doc_id, signed_at, file_id) + sha256, таблица `signed_cards`: одна
карточка на версию навсегда, запись версии, снятие ждущего, вставка черновика и очередь его карточки — одной транзакцией.
Водораздел `signed_since` (meta, первый запуск с флагом, now − WA_AGENT_SIGNED_LOOKBACK_H): версии раньше него карточки не
получают; рестарт его не сдвигает. Карточки нет: двойник sha256 (`_pdf_twin`) · тот же sha256 уже решён другой версией
реестра · у живого черновика номера уже есть этот PDF (версия «покрыта») · у ушедшего черновика этот PDF ждёт «Дослать
PDF» · документ после подписи уже отправил человек (с телефона или из темы) · окно закрыто · привязка не FACT. «Покрыта»
черновиком, который ядро потом сняло само (stale/superseded без решения человека), — версия снова открыта. Ждущий
черновик без этого PDF → superseded «заменён карточкой подписанного договора» (вопрос клиента и его язык переходят в
черновик подписи). Черновик подписи — kind='signed' (во всём остальном — обычный ответ: «Отправить» с перечитыванием
реестра, текст, затем PDF; новое входящее — stale), текст по языку последнего входящего (кириллица → RU, иначе EN), после
30 мин с подписи — с извинением. Клиенту ничего не уходит без нажатия «Отправить»; PDF с карточки подписи снят (двойник,
версия по пояснению без PDF) — «Отправить» снимает её stale, текст без PDF не уходит.
ПРОХОД НЕ ДЕРЖИТ ПОТОК СЛУЖБЫ: общий бюджет SIGNED_PASS_SEC (служба кладёт его плечам моста — `signed_budget`), не больше
SIGNED_PASS_MAX поисков в реестре, первый таймаут или отказ двери кончает проход, следующий продолжает с того же места
(курсор). Номер с решённой версией, подписью раньше водораздела или третьим подряд «договора нет» проверяется не чаще
SIGNED_IDLE (новое входящее клиента — сразу); сбой двери или PDF подряд — паузы SIGNED_RETRY.

ПРОСЬБА КЛИЕНТА ПРИСЛАТЬ СВОЙ ДОГОВОР (CASEPDF1510). Детектор — чистые функции ЭТОГО модуля (`ask_verdict`,
`ask_verdict_many`, только `re`; импорты модуля прежние), `contract_ask` — тонкая обёртка над ними. При карточке подписи
ядро судит просьбу само (параметр `ask_of` по умолчанию — этот детектор; служба передаёт None выключателем
WA_AGENT_CONTRACT_ASK=0); карточки подписи нет или `ask_of=None` — путь прежний байт-в-байт. Ответ клиенту строит МОДЕЛЬ
своим циклом, как прежде; детектор — только ограничитель первого узкого транспорта: вправе ли код сам приложить
проверенный PDF или сам нажать. Неотвеченные входящие (echo=0, живые, id > done_upto) судятся вместе: pure — явная просьба
и всё прочее нейтральное; mixed — просьба и рядом другое (в том числе второй вопрос); None — просьбы нет (отказ, вопрос об
условиях, «договорились», чужой договор). M2 — в проходе подписи: просьба не ждёт паузы номера «договора нет / раньше
водораздела» (частым шагом — не дольше ASK_EAGER_SEC от последнего входящего, дальше прежний ритм) и открывает версию,
подписанную раньше водораздела (прочие замки прежние); pure — карточка подписи (шаблон) и, как первая карточка версии,
замена ждущего ответа модели; mixed — карточки нет, ответ модели жив; двойник и решённая версия — карточки нет, повтор по
просьбе назван словами. M3 — в `_attach_decide`: модель contract не звала, просьба mixed (или pure, когда первую карточку
версии проход дать не может: прежнюю карточку сняло ядро, ответ модели жив — `_signed_wait_live`) — код привязывает договор
тем же помощником, что проход (`_signed_find` → `_signed_pdf`), и строка `attach` несёт PDF с опорой OPORA_ASKED; ответ
модели не снимается, текст не меняется; неудача — прежняя строка. M4 — WA_AGENT_AUTOSEND_CONTRACT (autosend): карточка
подписи по pure тем же тактом нажимается системой (`press`, AUTO_WHO), весь путь нажатия прежний; перед нажатием ещё раз
окно 24 ч, пауза, `_fresh`, потолки AUTOSEND_DAY_MAX в сутки и одна на версию, и карточка не снимала ответ, который правил
человек (версия больше 1, пояснение) или где модель просила человека (причины «нужен человек» переходят в карточку
подписи); начало пишется ДО нажатия (`signed_asks.auto_at`) — повтора нет; исход — по ОБЕИМ частям. Автоотправки НЕТ у
карточки события без просьбы, у mixed и у ответа модели. Таблица `signed_asks` — черновики, рождённые просьбой: номер +
doc_id + версия + sha256, вид, снятый ответ, исход; текста клиента нет — её прочтёт будущий читатель дела аренды.

ОЖИДАНИЕ ПОДПИСИ В БАЗЕ (CSTATE1510; выключатель службы WA_AGENT_CONTRACT_STATE, по умолчанию выкл; `cstate=True` — только
при карточке подписи). «Ждём подпись по просьбе» жило только в памяти процесса (`_signed_memo`); теперь — строка
`contract_expect` (её же читает блок фактов модели `wa_agent_cstate`). Открывает её ФАКТ, а не обещание из текста модели:
реестр пуст (EMPTY) и в неотвеченных входящих просьба прислать договор (`ask_of`) или сообщение «подписал» (`claim_of` —
детектор передаёт служба: замок импортов этого модуля прежний); срок — конец окна 24 ч от последнего входящего (окно
прохода не расширяется). Каждая проверка реестра по номеру с открытым ожиданием пишет `checked_at`/`outcome` (timeout и
refused его не закрывают); ритм — `_cstate_due` по базе (первые ASK_EAGER_SEC от открытия — каждый проход, дальше не
чаще SIGNED_IDLE), после рестарта — без опоры на память. Закрывает карточка подписи (`card:<id>` в ТОЙ ЖЕ транзакции
`_signed_insert`), решённая версия (`held`, `_signed_keep`) или срок (`expired` и строка журнала). Клиенту ничего не
уходит: карточка подписи и автоотправка CASEPDF1510 — как прежде. Выключено — ни таблицы, ни обращений к ней.

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
# K3-FIX шаг 3r (B2 повтора real): модель contract_pdf не звала — PDF привязанного кодом договора читает код
W_PDF_NOT_CALLED = "PDF договора не сверен (contract_pdf не звали)"
W_PDF_CODE_FAIL = "PDF договора не получен: модель contract_pdf не звала, код читал сам — %s — %s"
W_PDF_CODE_NOTE = " (PDF читал код: модель contract_pdf не звала)"

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

# ── карточка после подписи (SIGNEDCARD1410) ───────────────────────────────────────────────
F_SIGNED = "WA_AGENT_SIGNED_CARD"              # выключатель службы; читает `wa_agent_svc` (ядро окружение не читает)
KIND_SIGNED = "signed"                         # drafts.kind: карточка подписанного договора; ведёт себя как ответ
SIGNED_EVERY = 120                             # поиск подписанных договоров — не чаще, с
SIGNED_LOOKBACK_H = 6                          # водораздел первого запуска: now − столько часов
SIGNED_SINCE = "signed_since"                  # meta: водораздел (эпоха); пишется один раз, рестарт не сдвигает
SIGNED_LOOKBACK_MAX_H = 24                     # водораздел дальше суток назад не ставится (окно 24 ч всё равно уже)
SIGNED_LATE = 30 * 60                          # с подписи до карточки дольше — извинение в начале текста
SIGNED_LOOK = 50                               # входящих клиента (от новых к старым), где ищется язык
SIGNED_PASS_SEC = 20                           # проход: общий бюджет, с (поток службы один — нажатия ждут прохода)
SIGNED_PASS_MAX = 10                           # проход: поисков в реестре не больше; остальные — следующим (курсор)
SIGNED_IDLE = 600                              # решённая версия · раньше водораздела · «договора нет» подряд — не чаще, с
SIGNED_EMPTY_FREE = 2                          # «договора нет» подряд — столько проходов с обычным шагом, дальше IDLE
SIGNED_RETRY = (0, 0, 600, 1800, 3600)         # сбой двери/PDF подряд: пауза после N-го сбоя (первые два — шаг такта)
SIGNED_BUDGET_ERR = "card_deadline"           # = bridge_client.CARD_DEADLINE_ERROR: общий бюджет прохода исчерпан
SIGNED_PASS_SLACK = 2                          # отказ двери за столько с до конца бюджета прохода — бюджет, а не сбой
SIGNED_DEAD = (A.STALE, A.SUPERSEDED)          # покрывший черновик снят ЯДРОМ (без решения человека) — версия открыта
W_SIGNED_LABEL = "📄 Договор подписан"          # метка карточки вместо «📝 Черновик»
W_SIGNED_SUPERSEDED = "заменён карточкой подписанного договора (черновик №%d)"
W_SIGNED_NO_PDF = ("устарело: карточка подписанного договора без PDF не уходит — %s; текст без PDF не шлём, ничего не "
                   "отправлено")
W_SIGNED_PDF_WAIT = ("PDF договора сейчас не прочитан (%s) — клиенту ничего не отправлено, текст без PDF не шлём; "
                     "черновик ждёт: нажмите «Отправить» ещё раз")
W_SIGNED_PACE = "карточка подписанного договора — ритму не подлежит: текст и PDF уходят сразу по нажатию"
SIGNED_TEXT = {"ru": "Направляем ваш подписанный договор.", "en": "Here is your signed rental agreement."}
SIGNED_SORRY = {"ru": "Извините за задержку с ответом и договором. ",
                "en": "Sorry for the delay with our reply and the agreement. "}
OPORA_SIGNED = " · прочитал КОД: карточка подписанного договора, модель не звалась"
_SIGNED_SCHEMA = """
CREATE TABLE IF NOT EXISTS signed_cards (
    number      TEXT    NOT NULL,
    doc_id      TEXT    NOT NULL,
    signed_at   TEXT    NOT NULL,
    file_id     TEXT    NOT NULL,
    sha256      TEXT    NOT NULL,
    draft_id    INTEGER,                          -- черновик подписи; у «покрытой» версии — черновик, который её несёт
    ts          REAL    NOT NULL,
    PRIMARY KEY (number, doc_id, signed_at, file_id)
);
"""
# ── просьба клиента прислать СВОЙ договор (CASEPDF1510) ─────────────────────────────────
# Детектор — чистые функции ниже (только `re`, импорты модуля прежние — тест сверяет); `contract_ask` — обёртка над ними.
# Он — ограничитель транспорта, а не голова: ответ строит модель своим циклом, как прежде.
F_AUTOSEND = "WA_AGENT_AUTOSEND_CONTRACT"      # выключатель службы; ядро окружение не читает (флаг — параметр autosend)
F_CONTRACT_ASK = "WA_AGENT_CONTRACT_ASK"       # выключатель службы детектора (0 — ask_of=None, путь SIGNEDCARD1410)
ASK_PURE, ASK_MIXED = "pure", "mixed"          # = contract_ask.PURE / MIXED (тест сверяет)
ASKED = (ASK_PURE, ASK_MIXED)
ASK_CARD, ASK_ANSWER = "card", "answer"        # signed_asks.kind: карточка подписи · PDF к ответу модели
ASK_REOPENS = ("empty", "since")               # паузы номера («договора нет», «раньше водораздела»), которые просьба не ждёт
ASK_EAGER_SEC = SIGNED_LATE                    # столько от последнего входящего просьба не ждёт паузы номера «договора нет»
AUTO_WHO = "агент: автоотправка своего договора по просьбе"
AUTOSEND_DAY_MAX = 10                          # автоотправок на службу за скользящие 24 ч; на версию договора — одна
AUTO_PRESSING, AUTO_SKIP = "pressing", "skipped"
AUTO_TEXT_ONLY = "text_only"                   # auto_state: текст ушёл, PDF — нет (`text_only:<исход PDF>`)
OPORA_ASKED = " · прочитал КОД: клиент просит договор, модель contract не звала"
W_CONTRACT_NOT_CALLED = "договор не сверялся (contract не звали)"
W_ASK_OPEN = (W_CONTRACT_NOT_CALLED, "сверки не было")   # итог сверки модели, при котором M3 привязывает договор сам
W_ASK_REPEAT = ("клиент просит договор, а версия решена без новой карточки — %s; повтор по просьбе не автоматизирован: "
                "решает человек")
_ASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS signed_asks (
    draft_id    INTEGER PRIMARY KEY,              -- черновик, рождённый явной просьбой клиента прислать СВОЙ договор
    number      TEXT    NOT NULL,                 -- ключ дела: номер + doc_id + версия (signed_at, file_id) + sha256
    doc_id      TEXT,
    signed_at   TEXT,
    file_id     TEXT,
    sha256      TEXT,
    asked       TEXT    NOT NULL,                 -- pure | mixed (contract_ask)
    kind        TEXT    NOT NULL,                 -- card — карточка подписи · answer — PDF к ответу модели
    upto_id     INTEGER,                          -- последнее входящее, по которому судилась просьба (текста клиента нет)
    ts          REAL    NOT NULL,
    auto_at     REAL,                             -- автоотправка НАЧАТА (до нажатия); NULL — не было
    auto_state  TEXT,                             -- sent (текст И PDF) · text_only:<PDF> · исход нажатия · skipped · pressing
    auto_words  TEXT,                             -- слова исхода — наши, без текста клиента
    replaced_id INTEGER,                          -- ответ, который карточка подписи сняла (NULL — не снимала)
    replaced_why TEXT                             -- почему автоотправки не будет: снятый ответ правил человек / просила модель
);
CREATE INDEX IF NOT EXISTS signed_asks_version ON signed_asks(number, doc_id, signed_at, file_id);
"""
_ASK_COLS = (("replaced_id", "INTEGER"), ("replaced_why", "TEXT"))      # база первого прогона выпуска — догнать колонки
# ── ожидание подписи в базе (CSTATE1510) ────────────────────────────────────────────────────────────────────
F_CSTATE = "WA_AGENT_CONTRACT_STATE"           # выключатель службы; ядро окружение не читает (параметр cstate)
EXPECT_OPEN, EXPECT_CLOSED, EXPECT_EXPIRED = "open", "closed", "expired"
EXPECT_ASK, EXPECT_CLAIM = "ask", "signed_claim"   # contract_expect.why: просьба · клиент сообщил о подписи
EXPECT_HELD = "held"                           # closed_by: версия решена без новой карточки (иначе «card:<id>»)
_EXPECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS contract_expect (
    number      TEXT    NOT NULL,
    opened_at   REAL    NOT NULL,
    why         TEXT    NOT NULL,                 -- ask | signed_claim
    upto_id     INTEGER,                          -- последнее входящее при открытии (текста клиента нет)
    due_at      REAL    NOT NULL,                 -- конец окна 24 ч от последнего входящего
    checked_at  REAL,                             -- последняя проверка реестра по номеру
    outcome     TEXT,                             -- её исход: empty | timeout | refused (fact | conflict — словами T)
    state       TEXT    NOT NULL,                 -- open | closed | expired
    closed_at   REAL,
    closed_by   TEXT,                             -- card:<id> | held
    PRIMARY KEY (number, opened_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS contract_expect_open ON contract_expect(number) WHERE state='open';
"""

# Детектор (M1): «тексты НЕОТВЕЧЕННЫХ входящих → pure | mixed | None». НЕ решает, что ответить клиенту (это модель), и не
# судит интеллект агента: отвечает ровно на вопрос транспорта — вправе ли код сам приложить проверенный PDF (mixed — к ответу
# модели) или сам нажать «Отправить» на карточке подписи (pure, флаг WA_AGENT_AUTOSEND_CONTRACT). Примеры живут в тестах.
#   · pure  — явная просьба прислать / дать / показать СВОЙ договор (копию, PDF договора) или спросить, где он, и всё прочее —
#             нейтральное (приветствие, спасибо, пожалуйста, «подписал», ок, эмодзи);
#   · mixed — просьба есть, но рядом другой вопрос или содержание; вопрос «…?», где есть слово кроме вежливости, — содержание
#             («Где договор? Готово?», «Пришлите договор. Вы подписали?»);
#   · None  — просьбы нет: «договорились», вопросы о существовании и условиях, «договор подписан / получил», отказ и отмена
#             (в ЛЮБОМ из сообщений снимает просьбу целиком), чужой договор («его / её / ваш договор», his / her / your).
# НАПРАВЛЕНИЕ СОМНЕНИЯ — в сторону «НЕ pure» (pure разрешает автоотправку): глагол просьбы и «договор» связаны только
# служебными словами (мне, пожалуйста, копию, подписанный, мой, the, my, copy of …); вложение без текста, цифры и незнакомые
# слова — содержание (mixed); не разобрали — None.
_CA_SEP = r"[\s,;:\-–—]+"                              # между словами одного предложения (без . ? ! и перевода строки)
_CA_NOUN = (r"(?:(?:договор|контракт)(?:а|у|ом|е|ы|ов)?(?:\s+аренды)?"
            r"|(?:(?:rental|lease|rent)\s+)?(?:contract|agreement|pdf)s?)")
_CA_COPY = r"(?:копи(?:ю|я|и)|экземпляр|скан|copy)"     # «пришлите копию» — просьба, если договор назван в сообщении
# служебные слова между глаголом просьбы и договором: связь «прислать — договор» ими не рвётся. Чужого договора здесь нет:
# «его / её / ваш договор», his / her / your — связь рвётся, и просьбой СВОЕГО договора это не считается
_CA_GAP = ("мне", "нам", "пожалуйста", "пожалуйсто", "плиз", "пжл", "пж", "еще", "раз", "снова", "повторно", "уже", "сразу",
           "ка", "копию", "копия", "скан", "файл", "пдф", "pdf", "подписанный", "подписанного", "подписаный", "подписанную",
           "подписал", "подписала", "подписали", "мой", "моего", "мою", "наш", "нашего", "этот", "этого",
           "сюда", "тут", "здесь", "в", "ватсап", "вотсап", "whatsapp", "же", "вы",
           "me", "us", "the", "my", "our", "a", "an", "copy", "of", "signed", "please", "pls", "plz", "kindly", "again",
           "here", "over", "back", "this", "that", "final", "full", "scan", "file", "it", "via", "on")
_CA_GAPS = r"(?:%s(?:%s)\b)*" % (_CA_SEP, "|".join(_CA_GAP))
# голова просьбы: повелительное, «можете прислать», «где», «жду»; EN — send / can I get / where is
_CA_HEAD_RU_IMP = (r"(?:(?:при|вы|пере)шли(?:те)?|(?:при|вы|пере)шле(?:шь|те)|(?:при|вы)сыла(?:й|йте)"
                   r"|скин(?:ь|ьте|ешь|ете)|скидыва(?:й|йте)|кин(?:ь|ьте)|сброс(?:ь|ьте)|отправ(?:ь|ьте|ишь|ите)"
                   r"|отправля(?:й|йте)|да(?:й|йте|дите|шь)|покаж(?:и|ите))")
_CA_HEAD_RU_MODAL = (r"(?:(?:вы\s+)?(?:можете|сможете|(?:не\s+)?могли\s+бы(?:\s+вы)?)|можно(?:\s+ли)?)"
                     r"(?:\s+(?:мне|нам|пожалуйста|бы|ли))*\s+"
                     r"(?:прислать|выслать|переслать|скинуть|кинуть|сбросить|отправить|дать|показать|получить|увидеть)")
_CA_HEAD_RU_OTHER = r"(?:где|жд(?:у|ем))"
_CA_HEAD_EN = (r"(?:(?:(?:can|could|would|will)\s+(?:you|u)\s+(?:please\s+|pls\s+|plz\s+|kindly\s+)?)?"
               r"(?:send|resend|re-send|forward|share|give)"
               r"|(?:can|could|may)\s+(?:i|we)\s+(?:please\s+)?(?:get|have|see|receive)"
               r"|where(?:\s+is|\s+are)?)")
_CA_HEAD = r"(?:%s|%s|%s|%s)" % (_CA_HEAD_RU_IMP, _CA_HEAD_RU_MODAL, _CA_HEAD_RU_OTHER, _CA_HEAD_EN)
_CA_RX_HEAD_NOUN = re.compile(r"\b%s\b%s%s\b%s\b" % (_CA_HEAD, _CA_GAPS, _CA_SEP, _CA_NOUN))
# «договор подписал, пришлите копию», «the contract, please send it» — договор назван ДО глагола
_CA_RX_NOUN_HEAD = re.compile(r"\b%s\b%s%s\b(?:%s|send|resend|forward|share)\b(?:%s(?:%s|%s)\b)*" % (
    _CA_NOUN, _CA_GAPS, _CA_SEP, _CA_HEAD_RU_IMP, _CA_SEP, "|".join(_CA_GAP), _CA_COPY))
_CA_RX_HEAD_COPY = re.compile(r"\b%s\b%s%s\b%s\b%s" % (_CA_HEAD, _CA_GAPS, _CA_SEP, _CA_COPY, _CA_GAPS))
# «можно (копию) договор(а)» без глагола — просьба, только если до конца предложения нет ничего, кроме нейтрального:
# «можно договор на год?» — вопрос об условиях, а не просьба
_CA_RX_CAN_NOUN = re.compile(r"\bможно(?:\s+(?:мне|нам|ли))*%s%s\b%s\b" % (_CA_GAPS, _CA_SEP, _CA_NOUN))
# сочинение: «пришлите адрес и договор», «send me the price and the contract» — просьба есть, рядом другое
_CA_RX_COORD = re.compile(r"\b(?:%s|%s)\b[^.?!\n]*?(?:,|\bи\b|\band\b|&)%s\s*\b%s\b" % (
    _CA_HEAD_RU_IMP, _CA_HEAD_EN, _CA_GAPS, _CA_NOUN))
_CA_RX_ANY_NOUN = re.compile(r"\b%s\b" % _CA_NOUN)
_CA_RX_REFUSE = re.compile(
    r"\bне\s+(?:надо|нужно|нужен|нужна|нужны|требуется|присыла\w*|высыла\w*|отправля\w*|скидыва\w*|кида\w*|шли\w*)\b"
    r"|\bотмен\w*|\bбез\s+(?:договор|контракт)\w*"
    r"|\b(?:do\s+not|does\s+not|dont|no\s+need|not\s+need(?:ed)?|never\s*mind|cancel\w*)\b")
# вежливость — нейтральна и в вопросе («…, да?», «please?», «а?»): пинг, а не второй вопрос
_CA_POLITE = (
    r"здравствуйте", r"здравствуй", r"здрасте", r"здрасьте", r"приветствую", r"привет",
    r"добрый\s+(?:день|вечер)", r"доброе\s+утро", r"доброй\s+ночи", r"доброго\s+(?:дня|утра|вечера|времени\s+суток)",
    r"спасибо\s+(?:большое|огромное|заранее)", r"спасибо", r"благодарю", r"спс",
    r"пожалуйста", r"пожалуйсто", r"плиз", r"пжл", r"пж", r"окей", r"оки", r"ок", r"хорошо", r"ладно", r"ага", r"угу",
    r"да", r"а", r"ну",
    r"good\s+(?:morning|afternoon|evening|day)", r"hello", r"hiya", r"hi", r"hey",
    r"thank\s+you\s+(?:so|very)\s+much", r"thank\s+you", r"thanks\s+(?:a\s+lot|so\s+much)", r"thanks", r"thx", r"ty",
    r"cheers", r"please", r"pls", r"plz", r"kindly", r"okay", r"okey", r"ok", r"sure", r"yes", r"yeah", r"yep")
# нейтральное вне вопроса: вежливость + «подписал(а)», «уже», «все», местоимения и связки
_CA_NEUTRAL = _CA_POLITE + (
    r"ясно", r"понятно", r"отлично", r"супер", r"класс",
    r"подписала", r"подписали", r"подписал", r"подписано", r"подписана", r"подписан", r"готово", r"сделано",
    r"уже", r"все", r"я", r"вы", r"и", r"так", r"вот", r"же", r"ой", r"мне", r"нам", r"его", r"еще",
    r"снова", r"раз", r"повторно", r"мой", r"моего",
    r"k", r"great", r"good", r"fine", r"perfect", r"alright", r"all\s+right", r"cool",
    r"i\s+have\s+signed\s+it", r"i\s+have\s+signed", r"i\s+signed\s+it", r"i\s+signed", r"signed\s+it", r"signed",
    r"just", r"already", r"done", r"and", r"so", r"oh", r"i", r"have", r"it", r"the", r"a", r"an", r"my", r"me",
    r"us", r"our")
_CA_RX_NEUTRAL = re.compile(r"\b(?:%s)\b" % "|".join(sorted(_CA_NEUTRAL, key=len, reverse=True)))
_CA_RX_POLITE = re.compile(r"\b(?:%s)\b" % "|".join(sorted(_CA_POLITE, key=len, reverse=True)))
_CA_RX_SENTENCE_END = re.compile(r"[.?!\n]")
_CA_RX_QUESTION = re.compile(r"[^.?!\n]*\?")              # предложение, кончающееся вопросом
_CA_RX_CONTENT = re.compile(r"[^\W_]")                    # буква или цифра: содержание
_CA_CONTRACTIONS = ((r"\bi've\b", "i have"), (r"\bwhere's\b", "where is"), (r"\bdon't\b", "do not"),
                    (r"\bdoesn't\b", "does not"), (r"\bit's\b", "it is"), (r"\bcan't\b", "can not"))


def _ca_norm(text):
    """Нижний регистр, ё → е, апостроф одним знаком, сокращения EN раскрыты, пробелы схлопнуты."""
    s = str(text or "").lower().replace("ё", "е").replace("’", "'").replace("`", "'")
    for rx, full in _CA_CONTRACTIONS:
        s = re.sub(rx, full, s)
    return re.sub(r"[ \t]+", " ", s).strip()


def _ca_left(rx, piece):
    """Что остаётся в куске, если снять слова шаблона rx: есть ли там буква или цифра."""
    return _CA_RX_CONTENT.search(rx.sub(" ", piece)) is not None


def _ca_tail_neutral(s, pos):
    """От pos до конца предложения — только нейтральное?"""
    end = _CA_RX_SENTENCE_END.search(s, pos)
    return not _ca_left(_CA_RX_NEUTRAL, s[pos:end.start() if end is not None else len(s)])


def _ca_parse(text):
    """Одно сообщение → {"request": есть ли просьба, "other": есть ли рядом другое содержание, "refusal": отказ}."""
    s = _ca_norm(text)
    spans = [m.span() for m in _CA_RX_HEAD_NOUN.finditer(s)] + [m.span() for m in _CA_RX_NOUN_HEAD.finditer(s)]
    # «копию» — только если договор назван в том же сообщении и после «копию» до конца предложения нет своего объекта
    # («пришлите копию паспорта» — не договор); «можно договор» — только без хвоста условий («можно договор на год?»)
    copies = [m.span() for m in _CA_RX_HEAD_COPY.finditer(s) if _ca_tail_neutral(s, m.end())] \
        if _CA_RX_ANY_NOUN.search(s) is not None else []
    spans += [m.span() for m in _CA_RX_CAN_NOUN.finditer(s) if _ca_tail_neutral(s, m.end())]
    if copies:                                             # «копию» отсылает к названному договору: он — не содержание
        spans += copies + [m.span() for m in _CA_RX_ANY_NOUN.finditer(s)]
    rest = list(s)
    for a, b in spans:
        rest[a:b] = " " * (b - a)
    rest = "".join(rest)
    coord = _CA_RX_COORD.search(rest) is not None
    # второй вопрос рядом с просьбой — содержание, даже из «нейтральных» слов («Где договор? Готово?»); голый «?» и
    # вежливый пинг («…, да?», «please?») — нет
    question = any(_ca_left(_CA_RX_POLITE, m.group(0)) for m in _CA_RX_QUESTION.finditer(rest))
    return {"request": bool(spans) or coord, "other": coord or question or _ca_left(_CA_RX_NEUTRAL, rest),
            "refusal": _CA_RX_REFUSE.search(s) is not None}


def ask_verdict(text):
    """Одно сообщение клиента → "pure" | "mixed" | None (смыслы — выше)."""
    return ask_verdict_many([text])


def ask_verdict_many(texts):
    """НЕОТВЕЧЕННЫЕ входящие клиента вместе → "pure" | "mixed" | None. Отказ в любом сообщении — None; просьба хотя бы в
    одном и всё прочее нейтральное — pure; просьба и где угодно другое содержание — mixed; просьбы нет — None.
    Элемент не строка (вложение без подписи) — нейтральным не считается: зовущий передаёт его словом вида."""
    got = [_ca_parse(t if isinstance(t, str) else "[%s]" % type(t).__name__) for t in (texts or [])]
    if not any(p["request"] for p in got) or any(p["refusal"] for p in got):
        return None
    return ASK_MIXED if any(p["other"] for p in got) else ASK_PURE


_ASK_BUILTIN = object()                                  # умолчание `ask_of`: детектор этого модуля (при карточке подписи)
_CYR = re.compile(r"[А-Яа-яЁё]")
_LETTER = re.compile(r"[^\W\d_]")


def signed_lang(text):
    """Язык текста клиента для карточки подписи: кириллица → ru, другие буквы → en, букв нет → None."""
    s = str(text or "")
    if _CYR.search(s):
        return "ru"
    if _LETTER.search(s):
        return "en"
    return None


def signed_text(lang, late):
    """Текст черновика подписи по шаблону: язык ru|en (иначе en), late — с извинением в начале. Других слов нет."""
    lang = lang if lang in SIGNED_TEXT else "en"
    return (SIGNED_SORRY[lang] if late else "") + SIGNED_TEXT[lang]


def signed_epoch(signed_at, now):
    """signed_at реестра «yyyy-MM-dd HH:mm» (время Пхукета) → эпоха | None: без дня или времени версию по времени не
    судим (водораздел и извинение — только по разобранному времени)."""
    m = T.B.moment_of(signed_at)
    if m is None:
        return None
    return float(now) - (T.B.local_now(now) - m).total_seconds()


class _NoBudget:
    """Бюджет прохода не передан (ядро без службы, тесты) — проход без общего бюджета плеч моста; свой предел
    SIGNED_PASS_SEC по часам ядра остаётся. Своя заглушка, а не `contextlib`: импорты модуля прежние (тест сверяет)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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


def attach_of(tools_out, since=None, read_pdf=None):
    """Итог сверки Т4а (`ModelAdapter.last["tools"]`) → (метаданные PDF | None, причина словами).
    Вложение — только при однозначно принятом подписанном договоре этой аренды В ОПОРЕ СУДЬИ (`sift` с `since` =
    последнее входящее клиента, T4B3BASIS0510); иначе — почему вложения нет. `read_pdf(pdf_id, results)` (K3-FIX шаг 3r)
    — ответ `contract_pdf`, прочитанный КОДОМ: зовётся не больше раза и только когда модель contract_pdf не звала."""
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
        return None, W_CONTRACT_NOT_CALLED
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
    code = None
    if not pdf and callable(read_pdf) and c.get("pdf_id") and str(c.get("bound_by") or "").strip() \
            and all(_term(res, c, {})):
        # K3-FIX шаг 3r (B2 повтора real, решение интегратора 12.10): модель позвала `contract {}`, договор принят и
        # привязан КОДОМ (`bound_by`, окно срока ответа `contract`), а `contract_pdf` не звала (real_far2 K06, K15: текст
        # «PDF следующим сообщением», документов 0). PDF ЭТОГО договора (`pdf_id`) читает код — ОДИН раз, той же дверью и
        # тем же разбором, что у модели (`AttachCore._code_pdf`); дальше — прежние проверки. Модель contract_pdf звала
        # (свой или чужой id) — путь прежний; чтение не удалось — отказ словами, повтора нет; в журнал модели не идёт.
        try:
            code = read_pdf(str(c.get("pdf_id")), res)
        except Exception as e:                                       # noqa: BLE001
            return None, W_PDF_CODE_FAIL % ("unknown", "чтение упало: %s" % type(e).__name__)
        if not (isinstance(code, dict) and code.get("outcome") == T.FACT):
            got = code if isinstance(code, dict) else {}
            return None, W_PDF_CODE_FAIL % (got.get("outcome") or "unknown", got.get("reason") or "ответа нет")
        pdf = [code]
    if not pdf:
        return None, W_PDF_NOT_CALLED
    pdfs = [f for f in code.get("facts") or [] if isinstance(f, dict) and f.get("kind") == "pdf"] if code else kind("pdf")
    pf = [f for f in pdfs if str(f.get("id") or "") == str(c.get("pdf_id") or "") and c.get("pdf_id")]
    if not pf and code:
        return None, "сверен PDF не этого договора" + W_PDF_CODE_NOTE
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
        return None, "у PDF нет sha256 или размера — прикладывать нельзя" + (W_PDF_CODE_NOTE if code else "")
    signed_at = str(c.get("signed_at") or "").strip()
    if not signed_at:
        return None, "у договора нет signed_at — версию перед отправкой не сверить, вложения нет"
    date_from, date_to = _term(res, c, rent[-1])
    meta = {"file_id": str(p.get("id")), "name": str(p.get("name") or "contract.pdf"), "size": size,
           "sha256": sha, "row": p.get("row") if p.get("row") is not None else c.get("row"),
           "doc_id": c.get("doc_id"), "signed_at": signed_at, "date_from": date_from, "date_to": date_to}
    if code:
        meta["pdf_by"] = "код"                  # K3-FIX шаг 3r: PDF прочитан кодом — отметка на карточке (опора)
    return meta, ""


# ── K3-FIX F1: опора черновика на карточке — источник, время ЧТЕНИЯ, версия ТОЛЬКО от источника ──────────────────
OPORA_HEAD = "🧾 опора черновика — факты сверки Т4а (инструмент · источник · время чтения · версия источника)%s:"
OPORA_NONE = "🧾 опора черновика: фактов сверки нет%s"
OPORA_UNREAD = "🧾 опора черновика не разобрана (%s) — источники фактов не названы"
OPORA_LEGACY = "🧾 опора черновика не записана: сверка записана до K3-FIX F1"
OPORA_OFF = "• прочитано фактом, но не в опоре судьи (тот же запрос прочитан позже, устарел или снят): %d"
OPORA_CUT = "• … не показано строк опоры: %d (предел карточки — %d строк, %d знаков)"
OPORA_ROWS, OPORA_CHARS = 6, 700
OPORA_CODE = " · прочитал КОД: модель contract_pdf не звала"   # K3-FIX шаг 3r: строка PDF, прочитанного кодом
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


def opora_of(tools_out, since=None, rows_max=OPORA_ROWS, chars_max=OPORA_CHARS, code=None, mark=OPORA_CODE, extra=()):
    """Итог сверки Т4а (`ModelAdapter.last["tools"]`) → опора черновика словами для карточки (K3-FIX F1) | None (сверки
    нет). Строка — на КАЖДЫЙ ответ инструмента, чьи факты остались в опоре судьи (`sift` с тем же since, что у
    `attach_of`), по порядку чтения: инструмент · источник (`source` ответа: дверь, лист, узел) · время ЧТЕНИЯ ДАННЫХ
    (`read_at`, K3-FIX3: у прямых дверей — `at`, который `_read` ставит ДО вызова двери; у снимков — время снимка; по
    Пхукету, как все слова сотрудникам) · версия ТОЛЬКО если её отдал источник
    (`source_version` ответа, F2_CONTRACT §1.1; сегодня её не отдаёт ни одна дверь) — иначе «неизвестна». Поле `version`
    результата версией источника НЕ является (там `signed_at` договора и длина правил — F2_CONTRACT §0.3), служебное
    `stand_meta` подделки моста в результат не попадает вовсе. Новых обращений к мосту нет — только уже прочитанное.
    Длина — потолок строк и знаков; усечение названо числом, как и факты, снятые опорой судьи. `code` (K3-FIX шаг 3r) —
    ответ `contract_pdf`, прочитанный КОДОМ для вложения: последней строкой, с отметкой `mark` (по умолчанию `OPORA_CODE`;
    у карточки подписи — `OPORA_SIGNED`). `extra` (CASEPDF1510, M3) — ответы аренды и договора, прочитанные КОДОМ по просьбе
    клиента: после строк модели, перед строкой PDF, с той же отметкой `mark` (пусто — опора прежняя байт-в-байт)."""
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
    for r in extra or ():
        if isinstance(r, dict) and r.get("outcome") == T.FACT:
            rows.append(_opora_row(r, len(r.get("facts") or [])) + mark)
    if isinstance(code, dict) and code.get("outcome") == T.FACT:
        rows.append(_opora_row(code, len(code.get("facts") or [])) + mark)
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

    def __init__(self, *args, attach=False, pdf_fetch=None, contract_find=None, signed=False,
                 signed_lookback_h=SIGNED_LOOKBACK_H, signed_budget=None, ask_of=_ASK_BUILTIN, autosend=False,
                 cstate=False, claim_of=None, **kw):
        self.attach = bool(attach)
        self.pdf_fetch = pdf_fetch                  # file_id → ответ `bridge_client.contract_pdf` (content_b64, verified)
        self.contract_find = contract_find          # (phone, date_from, date_to) → ответ `bridge_client.contract_find`
        # карточка после подписи (SIGNEDCARD1410): дверь аренды — у МОДЕЛИ тем же способом, что у её сверки
        # (`ModelAdapter._tool_doors` → «rental», при деле аренды и «case»); нет её или любой двери договоров — выключена.
        # Модель — третий аргумент ядра (`Core(db, queue, model, …)`); `_startup` (из `Core.__init__`) уже судит по флагу
        model = args[2] if len(args) > 2 else kw.get("model")
        self.signed = bool(signed) and self.attach and callable(pdf_fetch) and callable(contract_find) \
            and callable(getattr(model, "_tool_doors", None))
        try:
            hours = min(max(0.0, float(signed_lookback_h)), float(SIGNED_LOOKBACK_MAX_H))
        except (TypeError, ValueError):
            hours = float(SIGNED_LOOKBACK_H)
        self.signed_lookback = hours * 3600
        # signed_budget(секунд) → контекст общего бюджета плеч моста на проход (служба: `bridge_client.card_budget`)
        self.signed_budget = signed_budget if callable(signed_budget) else None
        # просьба клиента прислать СВОЙ договор (CASEPDF1510): ask_of(тексты) → "pure" | "mixed" | None. По умолчанию —
        # детектор этого модуля (`ask_verdict_many`); None (служба: WA_AGENT_CONTRACT_ASK=0) или карточка подписи
        # выключена — M2/M3 мертвы, путь прежний байт-в-байт. autosend (WA_AGENT_AUTOSEND_CONTRACT) — только поверх него
        if ask_of is _ASK_BUILTIN:
            ask_of = ask_verdict_many
        self.ask_of = ask_of if callable(ask_of) and self.signed else None
        self.autosend = bool(autosend) and self.ask_of is not None
        # CSTATE1510: ожидание подписи — в базе (`contract_expect`), только при карточке подписи; claim_of(текст) → bool —
        # «клиент сообщил о подписи» (детектор `wa_contract_state.signed_claim` передаёт служба: импорты модуля прежние)
        self.cstate = bool(cstate) and self.signed
        self.claim_of = claim_of if callable(claim_of) and self.cstate else None
        self._signed_auto = []                      # черновики подписи по чистой просьбе этого прохода — к автоотправке
        self._signed_last = None                    # такт поиска подписанных (SIGNED_EVERY)
        self._signed_said = set()                   # причины «карточки нет» — строкой журнала один раз на процесс
        self._signed_cursor = None                  # последний разобранный номер: следующий проход — с номера после него
        self._signed_memo = {}                      # номер → когда проверять снова (решено/пусто/сбой подряд)
        self._signed_halt = None                    # почему прерван прошлый проход (строка журнала — на смену причины)
        self._signed_resume = None                  # номер, прерванный исчерпанным бюджетом: следующий проход — С него
        self._signed_t0 = None                      # начало идущего прохода (часы ядра): отказ у конца бюджета — не сбой
        self.signed_made = []                       # черновики подписи последнего вызова `make_signed_cards`
        self._signed_pre = {}                       # черновик подписи → байты PDF, прочитанные ДО текста (одно нажатие)
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
        if self.signed:                             # SIGNEDCARD1410: выключено — таблицы и метки нет, база прежняя
            self.db.executescript(_SIGNED_SCHEMA)
            if self.ask_of is not None:             # CASEPDF1510: детектора нет — таблицы нет, база прежняя
                self.db.executescript(_ASK_SCHEMA)
                have = {r[1] for r in self.db.execute("PRAGMA table_info(signed_asks)").fetchall()}
                for col, typ in _ASK_COLS:          # база первого прогона выпуска — колонки снятого ответа догнать
                    if col not in have:
                        self.db.execute("ALTER TABLE signed_asks ADD COLUMN %s %s" % (col, typ))
            if self.cstate:                         # CSTATE1510: выключено — таблицы нет, база прежняя
                self.db.executescript(_EXPECT_SCHEMA)
            if self.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                               (SIGNED_SINCE, repr(float(self.clock()) - self.signed_lookback))).rowcount == 1:
                self.log("подпись: водораздел записан — версии, подписанные раньше %s (Пхукет), карточки не получают"
                         % T.B.local_now(self._signed_since()).strftime("%d.%m %H:%M"))
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
        code = {}                                   # K3-FIX шаг 3r: ответ contract_pdf, прочитанный кодом (модель не звала)

        def read_pdf(pdf_id, results):
            code["r"] = self._code_pdf(pdf_id, results)
            return code["r"]
        meta, why = attach_of(out, since, read_pdf)  # опора судьи: sift с since = последнее входящее (T4B3BASIS0510)
        # CASEPDF1510 (M3): модель contract не звала, а клиент просит СВОЙ договор вместе с другим вопросом (или чисто, но
        # первую карточку версии проход дать не может) — код сам привязывает договор тем же помощником, что проход
        # подписи; ответ модели не снимается, текст не меняется
        asked = None
        if meta is None and ver is None and why in W_ASK_OPEN and self.ask_of is not None:
            asked = self._ask_attach(number, upto)     # None — просьбы для M3 нет: строка прежняя
            if asked is not None and asked["meta"]:
                meta, why = asked["meta"], ""
            elif asked is not None:
                self.log("черновик %d: клиент просит договор (%s) — код PDF не приложил (%s); ответ модели без PDF, "
                         "строка прежняя" % (did, asked["asked"], str(asked["why"])[:160]))
        by_code = bool(meta and meta.get("pdf_by"))
        if meta:
            twin = self._pdf_twin(number, meta["sha256"], did)
            if twin:
                meta, why = None, W_TWIN % (twin[2][:12], twin[0], twin[1])
                if asked is not None:
                    self.log("черновик %d: %s" % (did, W_ASK_REPEAT % ("этот PDF уже уходил черновиком %d (%s)" % (
                        twin[0], twin[1]))))
        m = meta or {}
        # K3-FIX F1: опора для карточки — из того же итога сверки; шаг 3r: + PDF, прочитанный кодом, с отметкой;
        # CASEPDF1510 (M3): + аренда, договор и PDF, прочитанные кодом по просьбе клиента, с отметкой OPORA_ASKED
        if asked is not None and meta:
            opora = opora_of(out, since, code=asked["code"], mark=OPORA_ASKED, extra=asked["rows"])
        else:
            opora = opora_of(out, since, code=code.get("r") if by_code else None)
        self.db.execute("INSERT OR REPLACE INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, "
                        "reason, ts, signed_at, number, date_from, date_to, opora) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (did, m.get("file_id"), m.get("name"), m.get("size"), m.get("sha256"), m.get("row"),
                         m.get("doc_id"), why or None, now, m.get("signed_at"), number if meta else None,
                         m.get("date_from"), m.get("date_to"), opora))
        if ver is not None:                         # Д2: строка — итог сверки ЭТОЙ версии по пояснению
            self.db.execute("UPDATE attach SET ver=? WHERE draft_id=?", (int(ver), did))
        if asked is not None and meta:              # черновик помечен просьбой: ключ дела — номер, doc_id, версия
            self.db.execute("INSERT OR REPLACE INTO signed_asks(draft_id, number, doc_id, signed_at, file_id, sha256, "
                            "asked, kind, upto_id, ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (did, number, m.get("doc_id"), m.get("signed_at"), m.get("file_id"), m.get("sha256"),
                             asked["asked"], ASK_ANSWER, upto, now))
        self.log("черновик %d: вложение %s%s%s" % (
            did, "PDF договора, sha256 %s…" % m["sha256"][:12] if meta else "нет — %s" % why,
            (" — клиент просит договор: договор и PDF привязал КОД (модель contract не звала)" if asked is not None
             else " — PDF прочитан кодом (модель contract_pdf не звала)") if meta and by_code else "",
            " (сверка версии %d по пояснению)" % ver if ver is not None else ""))

    def _code_pdf(self, file_id, results):
        """K3-FIX шаг 3r: `contract_pdf` по `pdf_id` привязанного кодом договора — КОДОМ, когда модель его не звала.
        Дверь — та же, что у сверки модели (`pdf_fetch` — дверь `contract_pdf` из `model.tools`, `wa_agent_svc.attach_of`),
        разбор — тот же (`T.call_tool` → `T._read` → `T.pdf_result`: факт только для pdf_id договора, принятого сверкой).
        Один вызов, без повтора; двери нет, отказ, таймаут — исход со словами, а не исключение."""
        return T.call_tool("contract_pdf", {"file_id": file_id}, {"contract_pdf": self.pdf_fetch}, self.clock,
                           {"results": results})

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

    def _pace_due(self, number, upto, text, now):
        """Ритм (WAHUMANPACE0210) карточке подписи не назначается (SIGNEDCARD1410): отложенное ушло бы мимо нажавшего, а
        при непрочитанном PDF вернулось бы в pending с карточкой «уйдёт в …». Нажатие захватило черновик подписи этого
        номера — срока нет, уходит сразу; иначе — ритм ядра."""
        if self.attach and self.db.execute("SELECT 1 FROM drafts WHERE number=? AND state=? AND kind=?",
                                           (number, A.CLAIMED, KIND_SIGNED)).fetchone():
            return None, W_SIGNED_PACE
        return super()._pace_due(number, upto, text, now)

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
        if (not meta or not meta[0]) and self.draft_kind(draft_id) == KIND_SIGNED:
            # SIGNEDCARD1410: текст карточки подписи («Направляем ваш подписанный договор») без самого PDF — неправда
            # клиенту. PDF снят (двойник: этот же PDF успел уйти другим черновиком; версия по пояснению без PDF) —
            # черновик stale словами, ДО двери: ни текста, ни PDF; реестр не перечитывается — отправлять нечего
            why = str((meta[5] if meta else "") or "PDF не приложен")
            words = W_SIGNED_NO_PDF % why[:220]
            if not self._close(draft_id, A.STALE, words, now, from_states=(from_state,)):
                return {"ok": False, "state": None, "words": self._decided(draft_id)}
            self.log("черновик %d → stale: карточка подписанного договора без PDF — ничего не отправлено" % draft_id)
            return {"ok": False, "state": A.STALE, "words": words}
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
        if self.draft_kind(draft_id) == KIND_SIGNED:
            # SIGNEDCARD1410 (финальный разбор): текст подписи — только ВМЕСТЕ с PDF. Байты читаются и сверяются (verified,
            # sha256 сверки, строка реестра, скелет) ДО текстовой части; часть PDF уйдёт этими же байтами, второго чтения
            # нет. Не прочитаны — захват назад: клиенту ничего, черновик ждёт, кнопки живы (как «очередь не прочитана»)
            body, pwhy = self._pdf_checked(draft_id, meta)
            if body is None:
                if self.db.execute("UPDATE drafts SET state=?, decided_by=NULL, decided_at=NULL WHERE id=? AND state=?",
                                   (A.PENDING, draft_id, from_state)).rowcount != 1:
                    return {"ok": False, "state": None, "words": self._decided(draft_id)}
                words = W_SIGNED_PDF_WAIT % str(pwhy)[:200]
                self.log("черновик %d: карточка подписи — PDF не прочитан до текста (%s): ничего не отправлено, черновик "
                         "ждёт" % (draft_id, str(pwhy)[:120]))
                return {"ok": False, "state": A.PENDING, "words": words}
            self._signed_pre[draft_id] = body
        try:
            return self._deliver_parts(draft_id, number, upto, text, who, now, from_state, meta, ver0)
        finally:
            self._signed_pre.pop(draft_id, None)

    def _deliver_parts(self, draft_id, number, upto, text, who, now, from_state, meta, ver0):
        """Текст, затем PDF (`_deliver` после перечитывания реестра; SIGNEDCARD1410 — вынесено, чтобы байты подписи,
        прочитанные до текста, гарантированно не пережили нажатие)."""
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

    def _pdf_checked(self, draft_id, meta):
        """Байты PDF из contract_pdf и обе сверки договора — verified, sha256 сверки, строка реестра, скелет (K3-FIX F4) →
        (байты, None) | (None, причина словами). Одно место на часть PDF (`_send_pdf`) и на карточку подписи, где байты
        читаются ДО текста (SIGNEDCARD1410): причины те же, что у части PDF до выноса."""
        file_id, _name, _size, sha, row, _why = meta
        try:
            got = self.pdf_fetch(file_id) if self.pdf_fetch else {"ok": False, "error": "двери contract_pdf нет"}
        except Exception as e:                                       # noqa: BLE001
            got = {"ok": False, "error": "дверь contract_pdf упала: %s" % type(e).__name__}
        if not (isinstance(got, dict) and got.get("ok") and got.get("verified") is True):
            err = got.get("error") if isinstance(got, dict) else "ответ не словарь"
            return None, "PDF не получен из contract_pdf: %s" % (err or "без verified")
        try:
            raw = base64.b64decode(got.get("content_b64") or "", validate=True)
        except Exception as e:                                       # noqa: BLE001
            return None, "PDF не декодирован: %s" % type(e).__name__
        now_sha = hashlib.sha256(raw).hexdigest()
        if now_sha != sha:
            return None, "sha256 PDF при отправке %s… не равен sha256 сверки %s… — файл изменился, не отправлено" % (
                now_sha[:12], sha[:12])
        # второй замок того же договора (NIGHT0710-B3v): мост назвал строку реестра — она обязана быть строкой сверки.
        # Не назвал — не судим (поле ответа необязательно); signed_at не сличается: его формат у contract_pdf не сверен
        have = got.get("row")
        if have not in (None, "") and row is not None and str(have).strip() != str(row).strip():
            return None, "строка реестра PDF при отправке %s, при сверке %s — договор сменился, не отправлено" % (
                str(have)[:20], str(row)[:20])
        # K3-FIX F4: скелет PDF судится на ТЕХ ЖЕ байтах, что уйдут двери (`body` — его же отдаёт `media["fetch"]`), ДО
        # sending: не сошёлся — часть not_sent с причиной человеку, двери нет, повтора нет. Уровень — `PDF_LEVEL`
        shape_ok, shape_why = pdf_shape(raw)
        if not shape_ok:
            self.log("черновик %d: PDF не прошёл проверку скелета (%s) — двери нет" % (draft_id, shape_why[:120]))
            return None, W_PDF_SHAPE % shape_why
        return raw, None

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

        # SIGNEDCARD1410: байты карточки подписи уже прочитаны и сверены ДО текста (`_deliver`) — второго чтения нет
        body = self._signed_pre.pop(draft_id, None)
        if body is None:
            body, why = self._pdf_checked(draft_id, meta)
            if body is None:
                return fail(why)
        now_sha = hashlib.sha256(body).hexdigest()
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

    # ── карточка после подписи (SIGNEDCARD1410) ───────────────────────────────────────────

    def _signed_since(self):
        """Водораздел карточек подписи (meta `signed_since`) → эпоха | None (метки нет или она битая)."""
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (SIGNED_SINCE,)).fetchone()
        try:
            return float(row[0]) if row else None
        except (TypeError, ValueError):
            return None

    def _signed_note(self, key, words):
        """Причина «карточки нет» — строкой журнала один раз на процесс (такт каждые SIGNED_EVERY с не шумит)."""
        if key in self._signed_said:
            return
        self._signed_said.add(key)
        self.log("подпись: %s" % words)

    def _signed_window(self, number, now):
        """Окно 24 ч клиента — ТЕМ ЖЕ правилом, что у напоминания (`Core._follow_due`): последнее входящее (echo=0, не
        квитанция и не реакция; время — ts_msg, иначе ts_queued) не старше FOLLOW_WINDOW − FOLLOW_SPARE. → (открыто,
        слова). Очередь не прочитана — не открыто: не измерено — не «открыто»."""
        try:
            q = self._queue()
            try:
                got = q.execute("SELECT MAX(COALESCE(NULLIF(ts_msg, 0), ts_queued)) FROM wa_inbox WHERE from_number=? "
                                "AND echo=0 AND msg_type IS NOT NULL AND msg_type NOT IN ('status', 'reaction')",
                                (number,)).fetchone()
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            return False, "очередь не прочитана (%s)" % type(e).__name__
        win = got[0] if got else None
        if win is None:
            return False, "окно 24 ч неизвестно — входящих клиента нет"
        if now - float(win) > A.FOLLOW_WINDOW - A.FOLLOW_SPARE:
            return False, "окно 24 ч закрыто или кончается"
        return True, "окно открыто"

    def _signed_lang(self, number, upto):
        """Язык карточки — по последнему входящему клиента (`signed_lang`): кириллица → ru, иначе en. Входящее без букв
        (фото, стикер, одни цифры) языка не говорит — берётся предыдущее входящее с буквами; букв нет нигде — en."""
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT text, msg_type, echo, history FROM wa_inbox WHERE from_number=? AND id<=? "
                                 "ORDER BY id DESC LIMIT ?", (number, int(upto), SIGNED_LOOK)).fetchall()
            finally:
                q.close()
        except Exception as e:                                       # noqa: BLE001
            self.log("подпись: язык не прочитан (%s) — EN" % type(e).__name__)
            return "en"
        for text, msg_type, echo, history in rows:
            if self._live_kind(msg_type, echo, history) != A.wa_kind.KIND_INBOUND:
                continue
            lang = signed_lang(text)
            if lang:
                return lang
        return "en"

    def _signed_keep(self, key, sha, draft_id, now, reopen=None):
        """Версия решена без новой карточки («покрыта», двойник, документ ушёл человеком) → строка `signed_cards`:
        больше не читается. reopen — черновик прежнего «покрытия», снятый ядром: та же строка переходит к новому решению
        (условно — только если её не перехватил другой процесс)."""
        if reopen is None:
            self.db.execute("INSERT OR IGNORE INTO signed_cards(number, doc_id, signed_at, file_id, sha256, draft_id, ts) "
                            "VALUES(?,?,?,?,?,?,?)", key + (sha, draft_id, now))
        else:
            self.db.execute("UPDATE signed_cards SET draft_id=?, sha256=?, ts=? WHERE number=? AND doc_id=? AND "
                            "signed_at=? AND file_id=? AND draft_id=?", (draft_id, sha, now) + key + (reopen,))
        if self.cstate and self._cstate_close(key[0], now, EXPECT_HELD):     # CSTATE1510: версия решена без карточки
            self.log("ожидание подписи: закрыто — версия решена без новой карточки")

    def _signed_record(self, key):
        """Решение по версии (`signed_cards`) → (черновик | None,) | None — версия ещё не решалась."""
        return self.db.execute("SELECT draft_id FROM signed_cards WHERE number=? AND doc_id=? AND signed_at=? AND "
                               "file_id=?", key).fetchone()

    def _signed_dead(self, draft_id):
        """Черновик, «покрывший» версию, снят ЯДРОМ, а не решением человека: не карточка подписи, stale | superseded,
        decided_by пуст (клиент написал ещё, ответили с телефона). Подписанный PDF с ним не ушёл и уже не уйдёт —
        версия снова открыта. «Не нужно», отправка, «Пересобрать», устаревание при нажатии — решение человека: нет."""
        if draft_id is None:
            return None
        row = self.db.execute("SELECT kind, state, decided_by FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return False
        if row[0] == KIND_SIGNED:
            # финальный разбор SIGNEDCARD1410: сама карточка подписи, снятая БЕЗ отправки и без «Не нужно» (клиент написал
            # ещё — до нажатия или при нём; ответили с телефона; реестр не прочитан при нажатии; служба без PDF-ядра) —
            # договор клиенту не ушёл, версия снова открыта. Двойник, «покрыта», документ человеком, отзыв в реестре —
            # проверяются заново следующим проходом. Решение человека навсегда: отправка, «Не нужно», «Пересобрать»
            return row[1] == A.STALE or (row[1] == A.SUPERSEDED and not row[2])
        return row[1] in SIGNED_DEAD and not row[2]

    def _signed_held(self, number, sha, key):
        """Почему версию с этим PDF карточкой подписи не подаём → (черновик | None, слова) | None. Только база агента:
        зовётся и до транзакции, и ВНУТРИ неё (второй экземпляр службы мог успеть между ними)."""
        twin = self._pdf_twin(number, sha, 0)
        if twin:
            return twin[0], "этот PDF уже уходил черновиком %d (%s)" % (twin[0], twin[1])
        other = [r[0] for r in self.db.execute(
            "SELECT draft_id FROM signed_cards WHERE number=? AND sha256=? AND NOT (doc_id=? AND signed_at=? AND "
            "file_id=?)", (number, sha) + tuple(key[1:])).fetchall()]
        alive = [d for d in other if not self._signed_dead(d)]
        if alive:
            return alive[0], "этот PDF уже решён другой версией реестра (черновик %s)" % (
                alive[0] if alive[0] is not None else "— документ ушёл человеком")
        cover = self.db.execute("SELECT d.id FROM drafts d JOIN attach a ON a.draft_id=d.id WHERE d.number=? "
                                "AND d.state IN (?,?,?,?) AND a.file_id IS NOT NULL AND a.sha256=? ORDER BY d.id DESC "
                                "LIMIT 1", (number, A.PENDING, A.CLAIMED, A.SENDING, A.SCHEDULED, sha)).fetchone()
        if cover:
            return cover[0], "версия покрыта черновиком %d (тот же PDF)" % cover[0]
        # текст ушёл, а PDF — нет: на карточке того черновика живёт «Дослать PDF» (`card_buttons`); вторая карточка с тем
        # же файлом дала бы две кнопки на один PDF, а нажатые обе — текст подписи без PDF (его теперь снимает `_deliver`)
        wait = self.db.execute("SELECT d.id FROM drafts d JOIN attach a ON a.draft_id=d.id JOIN pdf_parts p ON "
                               "p.draft_id=d.id WHERE d.number=? AND d.state=? AND p.state=? AND a.file_id IS NOT NULL "
                               "AND a.sha256=? ORDER BY d.id DESC LIMIT 1",
                               (number, A.SENT, A.NOT_SENT, sha)).fetchone()
        if wait:
            return wait[0], "этот PDF ждёт «Дослать PDF» на карточке черновика %d" % wait[0]
        return None

    def _signed_human_doc(self, number, at):
        """Документ клиенту после подписи отправил ЧЕЛОВЕК → слова | None. Из темы — строка `outbox` через «тема» вида
        document (relay медиа); с телефона — живое эхо вида document (не наше, не автоприветствие): паузы оно не ставит
        (WAPAUSEMEDIA0410), и без этой проверки клиент получил бы второй PDF. Очередь не прочитана — исключение: не
        измерено — не «человек не отправлял» (зовущий карточку не делает, повтор — следующим проходом)."""
        row = self.db.execute("SELECT ts FROM outbox WHERE number=? AND via=? AND kind=? AND ts>=? ORDER BY ts LIMIT 1",
                              (number, A.VIA_TOPIC, "document", float(at))).fetchone()
        if row:
            return "документ после подписи ушёл человеком из темы %s" % A.hm_phuket(row[0])
        q = self._queue()
        try:
            rows = q.execute("SELECT id, msg_type, echo, history, wamid, COALESCE(NULLIF(ts_msg, 0), ts_queued) "
                             "FROM wa_inbox WHERE from_number=? AND COALESCE(NULLIF(ts_msg, 0), ts_queued) >= ? "
                             "ORDER BY id", (number, float(at))).fetchall()
        finally:
            q.close()
        for rid, msg_type, echo, history, wamid, ts in rows:
            if (A.wa_kind._type(msg_type) == "document"
                    and self._live_kind(msg_type, echo, history) == A.wa_kind.KIND_ECHO
                    and not self._our_wamid(wamid) and not self._greeted(rid)):
                return "документ после подписи ушёл человеком с телефона %s" % A.hm_phuket(ts)
        return None

    def _signed_doors(self, number, upto):
        """Двери номера для привязки — ТЕ ЖЕ, что у сверки модели: аренда (и дело аренды) — `model._tool_doors`, реестр —
        дверь contract_find ядра (та же, что перечитывает реестр перед отправкой)."""
        probe = getattr(self.model, "_tool_doors", None)
        got = probe(number, upto) if callable(probe) else None
        doors = {k: v for k, v in (got or {}).items() if k in ("rental", T.CASE_TOOL)}
        doors["contract"] = self.contract_find
        return doors

    # ── ритм прохода: курсор, паузы номера, бюджет ─────────────────────────────────────────

    def _signed_due(self, number, last_in, now):
        """Пора ли проверять номер: пауза после сбоев подряд — по времени; «решено/пусто» — до нового входящего."""
        memo = self._signed_memo.get(number)
        if not memo:
            return True
        if now < memo.get("fail_at", 0):
            return False
        return not (memo.get("in") == last_in and now < memo.get("idle_at", 0))

    def _signed_set(self, number, last_in):
        memo = self._signed_memo.setdefault(number, {})
        if memo.get("in") != last_in:                # новое входящее — «решено/пусто» прежнего не в счёт
            memo.update({"in": last_in, "idle_at": 0, "empty": 0})
        return memo

    def _signed_idle(self, number, last_in, now, why="decided"):
        """Номер решён (версия решена, раньше водораздела, карточка сделана) — до нового входящего не чаще SIGNED_IDLE;
        сбои подряд кончились. why — почему (CASEPDF1510: паузу «раньше водораздела» явная просьба не ждёт)."""
        memo = self._signed_set(number, last_in)
        memo.update({"idle_at": now + SIGNED_IDLE, "fails": 0, "fail_at": 0, "why": why})

    def _signed_empty(self, number, last_in, now):
        """Подписанного договора в сроке нет (или привязка не факт): первые SIGNED_EMPTY_FREE проходов — обычный шаг
        (клиент подписывает прямо сейчас), дальше до нового входящего — не чаще SIGNED_IDLE."""
        memo = self._signed_set(number, last_in)
        memo.update({"empty": memo.get("empty", 0) + 1, "fails": 0, "fail_at": 0, "why": "empty"})
        if memo["empty"] > SIGNED_EMPTY_FREE:
            memo["idle_at"] = now + SIGNED_IDLE

    def _signed_fail(self, number, now):
        memo = self._signed_memo.setdefault(number, {})
        memo["fails"] = memo.get("fails", 0) + 1
        memo["fail_at"] = now + SIGNED_RETRY[min(memo["fails"], len(SIGNED_RETRY)) - 1]

    def _signed_ok(self, number):
        memo = self._signed_memo.get(number)
        if memo:
            memo["fails"], memo["fail_at"] = 0, 0

    def _signed_stop(self, stop):
        """Почему проход прерван — строкой журнала на СМЕНУ причины (каждые SIGNED_EVERY с одно и то же не пишем)."""
        if stop and stop != self._signed_halt:
            self.log("подпись: проход прерван — %s; остальные номера — следующим проходом, с того же места" % stop)
        elif not stop and self._signed_halt:
            self.log("подпись: проход снова целиком")
        self._signed_halt = stop

    def card_label(self, draft_id):
        """Метка карточки (рукам Telegram): черновик подписи С PDF — «📄 Договор подписан»; иначе None — метка прежняя
        (PDF с карточки снят — двойник, версия по пояснению без PDF: «Договор подписан» звучал бы неправдой)."""
        if not self.attach or self.draft_kind(draft_id) != KIND_SIGNED:
            return None
        meta = self._attach(draft_id)
        return W_SIGNED_LABEL if meta and meta[0] else None

    def signed_counts(self):
        """Решения по версиям для сводки службы: карточка · покрыта (другой черновик несёт или нёс этот PDF) · человек.
        CASEPDF1510 (детектор передан): + черновики по просьбе клиента (карточка подписи · PDF к ответу модели) и
        автоотправки (начато · ушли текст и PDF) — ключ только при ненулевом числе: без просьб сводка прежняя."""
        if not self.signed:
            return None
        out = dict(self.db.execute(
            "SELECT CASE WHEN s.draft_id IS NULL THEN 'человек' WHEN d.kind=? THEN 'карточка' ELSE 'покрыта' END, "
            "COUNT(*) FROM signed_cards s LEFT JOIN drafts d ON d.id=s.draft_id GROUP BY 1", (KIND_SIGNED,)).fetchall())
        if self.ask_of is not None:
            row = self.db.execute("SELECT SUM(kind=?), SUM(kind=?), SUM(auto_at IS NOT NULL), SUM(auto_state=?) FROM "
                                  "signed_asks", (ASK_CARD, ASK_ANSWER, A.SENT)).fetchone()
            for k, v in zip(("просьба_карточка", "просьба_ответ", "автоотправка", "автоотправка_ушла"), row or ()):
                if v:
                    out[k] = int(v)
        return out

    # ── просьба клиента прислать СВОЙ договор (CASEPDF1510) ──────────────────────────────────

    @staticmethod
    def _ask_text(msg_type, text):
        """Входящее → текст детектору: у текста — сам текст; вложение — словом вида (+ подпись): вложение без слов
        нейтральным не считается — при сомнении НЕ «чистая просьба»."""
        kind = A.wa_kind._type(msg_type)
        if kind == "text":
            return str(text or "")
        return ("[%s] %s" % (kind or "вложение", text or "")).strip()

    def _signed_asked(self, number, upto=None):
        """НЕОТВЕЧЕННЫЕ входящие клиента (echo=0, живые входящие `_live_kind`, id > clients.done_upto, id ≤ last_in_id или
        ≤ upto черновика) → детектор → "pure" | "mixed" | None. Детектора нет — None без чтения очереди (путь прежний);
        очередь не прочитана или детектор упал — None: при сомнении НЕ просьба. Текстов клиента в журнале нет."""
        if self.ask_of is None:
            return None
        cl = self.db.execute("SELECT last_in_id, done_upto FROM clients WHERE number=?", (number,)).fetchone()
        if not cl:
            return None
        top = int(cl[0]) if upto is None else int(upto)
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT id, msg_type, echo, history, text FROM wa_inbox WHERE from_number=? AND echo=0 "
                                 "AND id>? AND id<=? ORDER BY id", (number, int(cl[1] or 0), top)).fetchall()
            finally:
                q.close()
            texts = [self._ask_text(msg_type, text) for _rid, msg_type, echo, history, text in rows
                     if self._live_kind(msg_type, echo, history) == A.wa_kind.KIND_INBOUND]
            got = self.ask_of(texts) if texts else None
        except Exception as e:                                       # noqa: BLE001
            self.log("подпись: просьба клиента не разобрана (%s) — как без просьбы" % type(e).__name__)
            return None
        return got if got in ASKED else None

    def _signed_carried(self, number):
        """У номера живой черновик (ждёт · захвачен · уходит · отложен) уже несёт PDF — просьбу ведёт он."""
        return self.db.execute("SELECT 1 FROM drafts d JOIN attach a ON a.draft_id=d.id WHERE d.number=? AND d.state IN "
                               "(?,?,?,?) AND a.file_id IS NOT NULL LIMIT 1",
                               (number, A.PENDING, A.CLAIMED, A.SENDING, A.SCHEDULED)).fetchone() is not None

    def _signed_ask_due(self, number, now):
        """M2: номер на паузе «договора нет» / «раньше водораздела», а клиент сам просит договор и живого черновика с
        PDF нет — проверить сейчас (явная просьба паузу не ждёт: клиент подписывает прямо сейчас). Частым шагом — не
        дольше ASK_EAGER_SEC от последнего входящего клиента: просьба, которую никто не отвечает часами, реестр каждые
        SIGNED_EVERY не дёргает — дальше прежний ритм паузы (SIGNED_IDLE). Пауза после сбоев двери — ждёт всегда."""
        if self.ask_of is None:
            return False
        memo = self._signed_memo.get(number) or {}
        if now < memo.get("fail_at", 0) or memo.get("why") not in ASK_REOPENS:
            return False
        cl = self.db.execute("SELECT last_in_ts FROM clients WHERE number=?", (number,)).fetchone()
        eager = cl is not None and now - float(cl[0] or 0) <= ASK_EAGER_SEC
        return eager and not self._signed_carried(number) and self._signed_asked(number) in ASKED

    def _ask_attach(self, number, upto):
        """M3: просьба → привязка кодом тем же помощником, что у прохода подписи (аренда-FACT → contract FACT →
        `_code_pdf` → `attach_of` по договору, привязанному кодом). Смешанная — всегда (карточки подписи у неё нет);
        чистая — только когда первую карточку версии проход дать не может (`_signed_wait_live`: прежнюю карточку подписи
        сняло ядро, а этот ответ модели жив и ради шаблона не снимается) — иначе её ведёт карточка подписи (M2).
        → None — просьбы для M3 нет (строка прежняя) | {"asked", "meta", "why", "rows": [аренда, договор], "code": ответ
        contract_pdf}. Под общим бюджетом прохода (SIGNED_PASS_SEC): больной мост не держит такт ответа модели дольше
        прохода подписи."""
        asked = self._signed_asked(number, upto)
        if not (asked == ASK_MIXED or (asked == ASK_PURE and self._signed_wait_live(number))):
            return None
        got = {"asked": asked, "meta": None, "why": "", "rows": [], "code": None}
        try:
            with (self.signed_budget(SIGNED_PASS_SEC) if self.signed_budget else _NoBudget()):
                rental, contract = self._signed_find(number, upto)
                if contract is not None and self.cstate:
                    self._cstate_m3(number, contract)   # CSTATE1510: проверка реестра — исход в открытое ожидание
                if contract is None:
                    got["why"] = "аренда: %s" % (rental.get("outcome") if isinstance(rental, dict) else "ответа нет")
                elif contract.get("outcome") != T.FACT:
                    got["why"] = "договор: %s — %s" % (contract.get("outcome"), str(contract.get("reason") or "")[:80])
                else:
                    meta, why, code_r = self._signed_pdf(contract)
                    got.update(meta=meta, why=why, rows=[rental, contract], code=code_r)
        except Exception as e:                                       # noqa: BLE001
            got["why"] = "привязка кодом упала (%s)" % type(e).__name__
        return got

    def _ask_replaced(self, old, prev):
        """Ответ модели, который снимает карточка подписи по просьбе, — тронут человеком или модель просила человека? →
        слова (наши, без текста клиента и без причин модели дословно) | None. Тронут: версия больше 1 (правка «Исправить»
        или версия по пояснению), пояснение к нему (ждёт или сделано), причины «нужен человек» (или они не прочитаны).
        Таблицу пояснений не прочитали — тоже «тронут»: при сомнении автоотправки нет."""
        try:
            ver = int(prev[2] or 1)
        except (TypeError, ValueError):
            ver = 0
        if ver != 1:
            return "карточка сняла ответ (черновик %d), который правил человек: версия %s" % (old, prev[2])
        try:
            hinted = self.db.execute("SELECT COUNT(*) FROM hints WHERE draft_id=?", (old,)).fetchone()[0]
        except Exception as e:                                       # noqa: BLE001
            return "карточка сняла ответ (черновик %d): пояснения человека не прочитаны (%s)" % (old, type(e).__name__)
        if hinted:
            return "карточка сняла ответ (черновик %d), к которому было пояснение человека" % old
        hand = A.handoff_of(prev[3])
        if hand is None:
            return "карточка сняла ответ (черновик %d): причины «нужен человек» не прочитаны" % old
        if hand:
            return "карточка сняла ответ (черновик %d), где модель просила человека: причин %d" % (old, len(hand))
        return None

    def _auto_block(self, did, now):
        """M4: почему автоотправку НЕ делать → слова | None. Только чистая просьба и карточка подписи, черновик ждёт,
        карточка не снимала ответ, который правил человек или где модель просила человека, по версии автоотправки ещё
        не было, суточный потолок не исчерпан, клиент не на паузе, окно 24 ч открыто, после черновика клиент не писал и
        с телефона не отвечали."""
        if not self.autosend:
            return "флаг %s выкл" % F_AUTOSEND
        if not self._door_open():                   # дверь закрыта — попытку версии не тратим: нажатие было бы впустую
            return "отправка выключена (WA_SEND)"
        row = self.db.execute("SELECT d.number, d.upto_id, d.state, s.asked, s.kind, s.doc_id, s.signed_at, s.file_id, "
                              "s.replaced_why FROM drafts d JOIN signed_asks s ON s.draft_id=d.id WHERE d.id=?",
                              (int(did),)).fetchone()
        if not row:
            return "черновик не помечен просьбой клиента"
        number, upto, state, asked, kind, doc_id, signed_at, file_id, replaced = row
        if asked != ASK_PURE or kind != ASK_CARD:
            return "не чистая просьба (%s, %s) — только по нажатию" % (asked, kind)
        if state != A.PENDING:
            return "черновик уже не ждёт: %s" % state_word(state)
        if replaced:                                # решение человека / просьба модели о человеке шаблоном не отменяется
            return "%s — решает человек" % replaced
        if self.db.execute("SELECT COUNT(*) FROM signed_asks WHERE number=? AND doc_id=? AND signed_at=? AND file_id=? "
                           "AND auto_at IS NOT NULL", (number, doc_id, signed_at, file_id)).fetchone()[0]:
            return "по этой версии договора автоотправка уже была — повтор только нажатием"
        day = self.db.execute("SELECT COUNT(*) FROM signed_asks WHERE auto_at >= ?", (float(now) - 86400,)).fetchone()[0]
        if day >= AUTOSEND_DAY_MAX:
            return "суточный потолок автоотправок %d исчерпан" % AUTOSEND_DAY_MAX
        cl = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
        if not cl or cl[0]:
            return "клиент на паузе — беседу ведёт человек" if cl else "клиента нет в базе"
        ok, why = self._signed_window(number, now)
        if not ok:
            return "окно 24 ч: %s" % why
        try:
            fresh = self._fresh(number, upto)
        except Exception as e:                                       # noqa: BLE001
            return "очередь не прочитана (%s)" % type(e).__name__
        if fresh:
            return "после черновика %s (строка %d)" % (
                "клиент написал ещё" if fresh[0] == A.wa_kind.KIND_INBOUND else "ответили с телефона", fresh[1])
        return None

    def _signed_autosend(self, did):
        """M4 (WA_AGENT_AUTOSEND_CONTRACT): карточка подписи по ЧИСТОЙ просьбе — система сама нажимает штатное
        «Отправить» (`press`, who=AUTO_WHO): весь путь нажатия прежний — захват, `_outdated`, `_fresh`, пауза, ритм,
        перечитывание реестра, PDF до текста, текст, PDF, квитанции. Начало ложится в `signed_asks.auto_at` ДО нажатия —
        повтора нет ни тактом, ни рестартом. Исход — строкой журнала и в `signed_asks`. → ответ нажатия | None."""
        now = self.clock()
        why = self._auto_block(did, now)
        if why:
            self.db.execute("UPDATE signed_asks SET auto_state=?, auto_words=? WHERE draft_id=? AND auto_at IS NULL",
                            (AUTO_SKIP, why[:300], int(did)))
            self.log("подпись: автоотправка черновика %d — не делалась: %s; карточка ждёт нажатия «Отправить»"
                     % (did, why))
            return None
        if self.db.execute("UPDATE signed_asks SET auto_at=?, auto_state=? WHERE draft_id=? AND auto_at IS NULL",
                           (now, AUTO_PRESSING, int(did))).rowcount != 1:
            return None
        ver = self.db.execute("SELECT ver FROM drafts WHERE id=?", (int(did),)).fetchone()
        try:
            res = self.press(did, int(ver[0]) if ver else 1, A.ACT_SEND, AUTO_WHO, now)
        except Exception as e:                                       # noqa: BLE001
            res = {"ok": False, "state": None, "words": "нажатие упало (%s) — исход неизвестен, не повторяем"
                   % type(e).__name__}
        res = res if isinstance(res, dict) else {}
        parts = res.get("parts") if isinstance(res.get("parts"), dict) else {}
        # исход — по ОБЕИМ частям: «sent» только у текста И PDF; текст ушёл, а PDF нет — не «sent» (клиент получил
        # «Направляем договор» без файла, на карточке «Дослать PDF»): будущий читатель дела не прочтёт «доставлен»
        tstate, pstate = parts.get("text"), parts.get("pdf")
        if tstate == A.SENT and pstate == A.SENT:
            state = A.SENT
        elif tstate == A.SENT:
            state = "%s:%s" % (AUTO_TEXT_ONLY, pstate or "?")
        else:
            state = str(tstate or res.get("state") or "?")
        words = str(res.get("words") or "исход не назван")
        self.db.execute("UPDATE signed_asks SET auto_state=?, auto_words=? WHERE draft_id=?", (state, words[:300], int(did)))
        self.log("подпись: автоотправка черновика %d — %s" % (did, words[:300]))
        return res

    def make_signed_cards(self, now):
        """Подписанный договор → ОДНА карточка с PDF на версию (SIGNEDCARD1410). → число созданных карточек.
        Не чаще SIGNED_EVERY; выключено (signed) или черновиков нет — ничего, ни одного вызова двери. Проход держит
        поток службы не дольше SIGNED_PASS_SEC (общий бюджет плеч моста — `signed_budget` службы), не больше
        SIGNED_PASS_MAX поисков в реестре, до первого таймаута или отказа двери; следующий — с номера после курсора."""
        made = 0
        self.signed_made = []
        if not (self.attach and self.signed and self.drafts):
            return made
        if self._signed_last is not None and 0 <= now - self._signed_last < SIGNED_EVERY:
            return made
        self._signed_last = now
        self._cstate_expire(now)                    # CSTATE1510: срок ожиданий подписи — до прохода (выкл — ничего)
        since = self._signed_since()
        if since is None:
            self._signed_note(("since",), "водораздела нет в базе — карточек подписи нет (метка пишется на старте)")
            return made
        rows = self.db.execute("SELECT number, last_in_id FROM clients WHERE paused=0 AND last_in_id > 0 AND "
                               "last_in_ts >= ? ORDER BY number",
                               (now - A.FOLLOW_WINDOW - 3600,)).fetchall()     # грубый отсев, как у напоминания
        names = {r[0] for r in rows}
        self._signed_memo = {n: m for n, m in self._signed_memo.items() if n in names}
        cur, start, self._signed_resume = self._signed_cursor, self._signed_resume, None
        if start is not None:                       # номер, которому не хватило бюджета прошлого прохода, — первым
            rows = [r for r in rows if r[0] >= start] + [r for r in rows if r[0] < start]
        elif cur is not None:                       # по кругу: прерванный проход продолжается с номера после курсора
            rows = [r for r in rows if r[0] > cur] + [r for r in rows if r[0] <= cur]
        t0, asked, stop = self.clock(), 0, None
        self._signed_t0 = t0
        self._signed_auto = []
        with (self.signed_budget(SIGNED_PASS_SEC) if self.signed_budget else _NoBudget()):
            for number, last_in in rows:
                if self.clock() - t0 >= SIGNED_PASS_SEC:
                    stop = "бюджет прохода %d с исчерпан" % SIGNED_PASS_SEC
                    break
                if asked >= SIGNED_PASS_MAX:
                    stop = "поисков в реестре за проход %d" % SIGNED_PASS_MAX
                    break
                # CASEPDF1510 (M2): явная просьба клиента паузу «договора нет» / «раньше водораздела» не ждёт;
                # CSTATE1510: открытое ожидание подписи — свой ритм по базе (`_cstate_due`), без опоры на память
                if not self._signed_due(number, last_in, now) and not self._signed_ask_due(number, now) \
                        and not self._cstate_due(number, now):
                    continue
                self._signed_cursor = number
                try:
                    did, called, halt = self._signed_one(number, now, since)
                except Exception as e:                               # noqa: BLE001
                    self._tx_end(ok=False)
                    self._signed_fail(number, now)
                    self._signed_note((number, "crash", type(e).__name__), "номер %s — разбор упал (%s), карточки "
                                      "нет" % (T._tail(T.last9(number)), type(e).__name__))
                    continue
                asked += 1 if called else 0
                if did is not None:
                    made += 1
                    self.signed_made.append(did)
                if halt:
                    stop = halt
                    break
        self._signed_stop(stop)
        # CASEPDF1510 (M4): автоотправка — тем же тактом, ПОСЛЕ прохода и вне его общего бюджета: нажатие идёт тем же
        # путём и с теми же бюджетами дверей, что нажатие человека (перечитывание реестра не съедает остаток прохода)
        auto, self._signed_auto = self._signed_auto, []
        for did in auto:
            try:
                self._signed_autosend(did)
            except Exception as e:                                   # noqa: BLE001
                self._tx_end(ok=False)
                self.log("подпись: автоотправка черновика %d упала (%s) — исход по базе, не повторяем"
                         % (did, type(e).__name__))
        self._signed_last = now + max(0.0, self.clock() - t0)    # пауза SIGNED_EVERY — от КОНЦА прохода
        return made

    def _signed_wait_live(self, number):
        """Повторное предложение версии (прежнюю карточку подписи сняло ядро — `_signed_dead`) при ЖИВОМ ответе модели
        этому номеру (pending/claimed/sending/scheduled) ждёт: ответ на новое сообщение клиента («а когда вернуть байк?»)
        ради шаблона подписи не снимается; карточка — следующим проходом после его решения (финальный разбор
        SIGNEDCARD1410). Первая карточка версии по-прежнему заменяет ждущий черновик без этого PDF (выбор владельца)."""
        if not self.db.execute("SELECT 1 FROM drafts WHERE number=? AND state IN (?,?,?,?)",
                               (number, A.PENDING, A.CLAIMED, A.SENDING, A.SCHEDULED)).fetchone():
            return False
        rows = self.db.execute("SELECT draft_id FROM signed_cards WHERE number=? AND draft_id IS NOT NULL",
                               (number,)).fetchall()
        return any(self._signed_dead(r[0]) for r in rows)

    def _signed_short(self, number, res):
        """Отказ двери — исчерпанный ОБЩИЙ бюджет прохода (мост ответил card_deadline либо отказ пришёл у самого конца
        бюджета: снимок броней теряет причину моста), а не сбой двери. → True: сбоем номеру НЕ засчитывается (паузы
        SIGNED_RETRY не растут), следующий проход начинается С этого номера (финальный разбор SIGNEDCARD1410)."""
        reason = str(res.get("reason") or "") if isinstance(res, dict) else ""
        short = SIGNED_BUDGET_ERR in reason or (
            self._signed_t0 is not None and self.clock() - self._signed_t0 >= SIGNED_PASS_SEC - SIGNED_PASS_SLACK)
        if short:
            self._signed_resume = number
        return short

    # ── ожидание подписи в базе (CSTATE1510) ──────────────────────────────────────────────────────────────────

    def _cstate_claimed(self, number):
        """В НЕОТВЕЧЕННЫХ входящих (то же чтение очереди, что у `_signed_asked`: echo=0, живые входящие, id >
        clients.done_upto и ≤ last_in_id) клиент сообщает, что подписал (`claim_of`)? Детектора нет, клиента нет, очередь
        не прочитана или детектор упал — нет: при сомнении ожидание не открывается. Текстов клиента в журнале нет."""
        if self.claim_of is None:
            return False
        cl = self.db.execute("SELECT last_in_id, done_upto FROM clients WHERE number=?", (number,)).fetchone()
        if not cl:
            return False
        try:
            q = self._queue()
            try:
                rows = q.execute("SELECT id, msg_type, echo, history, text FROM wa_inbox WHERE from_number=? AND echo=0 "
                                 "AND id>? AND id<=? ORDER BY id", (number, int(cl[1] or 0), int(cl[0]))).fetchall()
            finally:
                q.close()
            return any(bool(self.claim_of(self._ask_text(msg_type, text))) for _rid, msg_type, echo, history, text in rows
                       if self._live_kind(msg_type, echo, history) == A.wa_kind.KIND_INBOUND)
        except Exception as e:                                       # noqa: BLE001
            self.log("ожидание подписи: сообщение о подписи не разобрано (%s) — ожидание не открыто" % type(e).__name__)
            return False

    def _cstate_note(self, number, outcome, now, last_in=None, ask=None):
        """Проверка реестра по номеру (исход двери договора `outcome`) → ожидание подписи в базе. Открытое — пишет
        `checked_at`/`outcome` (timeout и refused его не закрывают). Открытого нет, реестр пуст (EMPTY), а клиент просит
        договор (`ask`) или сообщил о подписи (`_cstate_claimed`) — открывается: срок — конец окна 24 ч от последнего
        входящего. → True — открыто этим вызовом. Выключено — ничего, ни одного обращения к базе; сбой базы — строкой
        журнала (один раз на процесс), карточка подписи — как прежде."""
        if not self.cstate:
            return None
        try:
            if self._cstate_checked(number, outcome, now):
                return None
            if outcome != T.EMPTY:
                return None
            why = EXPECT_ASK if ask in ASKED else EXPECT_CLAIM if self._cstate_claimed(number) else None
            if why is None:
                return None
            cl = self.db.execute("SELECT last_in_ts FROM clients WHERE number=?", (number,)).fetchone()
            due = float((cl or (0,))[0] or 0) + A.FOLLOW_WINDOW
            if due <= now:
                return None
            n = self.db.execute("INSERT OR IGNORE INTO contract_expect(number, opened_at, why, upto_id, due_at, "
                                "checked_at, outcome, state) VALUES(?,?,?,?,?,?,?,?)",
                                (number, now, why, last_in, due, now, outcome, EXPECT_OPEN)).rowcount
        except Exception as e:                                       # noqa: BLE001
            self._signed_note(("cstate", type(e).__name__), "ожидание подписи не записано (%s) — карточка подписи как "
                              "прежде" % type(e).__name__)
            return None
        if n == 1:
            self.log("ожидание подписи: открыто — номер %s, %s, реестр пуст; проверяется сам до %s (Пхукет)" % (
                T._tail(T.last9(number)), "просьба прислать договор" if why == EXPECT_ASK else "клиент сообщил о подписи",
                T.B.local_now(due).strftime("%d.%m %H:%M")))
        return n == 1

    def _cstate_checked(self, number, outcome, now):
        """Проверка реестра по номеру → открытое ожидание: `checked_at` и `outcome` (исход двери словом
        `wa_agent_tools`). → число строк: 0 — открытого ожидания у номера нет. Ничего не открывает и не закрывает."""
        return self.db.execute("UPDATE contract_expect SET checked_at=?, outcome=? WHERE number=? AND state=?",
                               (now, str(outcome or "?"), number, EXPECT_OPEN)).rowcount

    def _cstate_m3(self, number, contract):
        """M3 (PDF к ответу модели по просьбе) тоже читает реестр по номеру: исход — в открытое ожидание. Ожидание здесь
        не открывается (открывает его только проход подписи); сбой записи — строкой журнала, привязка M3 не падает."""
        try:
            self._cstate_checked(number, contract.get("outcome"), self.clock())
        except Exception as e:                                       # noqa: BLE001
            self._signed_note(("cstate-m3", type(e).__name__), "ожидание подписи: исход проверки реестра при ответе "
                              "модели не записан (%s)" % type(e).__name__)

    def _cstate_due(self, number, now):
        """Открытое ожидание подписи → пора ли проверять реестр (CSTATE1510): срок не вышел, паузы после сбоев двери нет;
        первые ASK_EAGER_SEC от открытия — каждый проход, дальше — не чаще SIGNED_IDLE от прошлой проверки. Ритм — по
        базе (`contract_expect`), а не по памяти процесса: после рестарта ожидание продолжается."""
        if not self.cstate:
            return False
        if now < (self._signed_memo.get(number) or {}).get("fail_at", 0):
            return False
        try:
            row = self.db.execute("SELECT opened_at, due_at, checked_at FROM contract_expect WHERE number=? AND state=?",
                                  (number, EXPECT_OPEN)).fetchone()
        except Exception:                                            # noqa: BLE001
            return False
        if not row or now >= float(row[1]):
            return False
        if now - float(row[0]) < ASK_EAGER_SEC:
            return True
        return row[2] is None or now - float(row[2]) >= SIGNED_IDLE

    def _cstate_close(self, number, now, by):
        """Открытое ожидание номера → закрыто (`card:<id>` — карточкой подписи в её транзакции; `held` — версия решена
        без новой карточки). → число закрытых: 0 — открытого не было."""
        return self.db.execute("UPDATE contract_expect SET state=?, closed_at=?, closed_by=? WHERE number=? AND state=?",
                               (EXPECT_CLOSED, now, by, number, EXPECT_OPEN)).rowcount

    def _cstate_expire(self, now):
        """Срок ожиданий подписи (конец окна 24 ч) вышел → expired и строка журнала на каждое (CSTATE1510). Клиенту
        ничего: ожидание только просило код проверять реестр. → число истёкших; выключено — 0 без обращений к базе."""
        if not self.cstate:
            return 0
        n = 0
        try:
            rows = self.db.execute("SELECT number, opened_at, why, outcome FROM contract_expect WHERE state=? AND "
                                   "due_at<=? ORDER BY opened_at", (EXPECT_OPEN, now)).fetchall()
            for number, opened, why, outcome in rows:
                if self.db.execute("UPDATE contract_expect SET state=?, closed_at=? WHERE number=? AND opened_at=? AND "
                                   "state=?", (EXPECT_EXPIRED, now, number, opened, EXPECT_OPEN)).rowcount != 1:
                    continue
                n += 1
                # последняя проверка нашла подписанный (карточки по нему не было: версия решена, ответ модели) — не
                # «без подписанного договора»: слова строки — по исходу последней проверки, а не по сроку
                self.log("ожидание подписи: истекло — номер %s, открыто %s (%s): %s; клиенту ничего не отправлено" % (
                    T._tail(T.last9(number)), A.hm_phuket(opened),
                    "просьба" if why == EXPECT_ASK else "клиент сообщил о подписи",
                    "срок 24 ч вышел — подписанный в реестре найден, новой карточки по нему нет" if outcome == T.FACT
                    else "окно 24 ч кончилось без подписанного договора в реестре"))
        except Exception as e:                                       # noqa: BLE001
            self._signed_note(("cstate-expire", type(e).__name__), "ожидание подписи: срок не проверен (%s)"
                              % type(e).__name__)
        return n

    def _signed_one(self, number, now, since):
        """Один клиент → (черновик подписи | None, звался ли реестр, почему прервать проход | None). Карточки нет —
        причина в журнал один раз на процесс. CASEPDF1510 (M2): явная просьба клиента прислать СВОЙ договор открывает
        версию, подписанную раньше водораздела; pure — карточка подписи (и к автоотправке при флаге), mixed — карточки нет:
        PDF к ответу модели прикладывает код (M3); прочие замки прежние."""
        tail = T._tail(T.last9(number))
        if self.db.execute("SELECT 1 FROM drafts WHERE number=? AND state IN (?,?)",
                           (number, A.CLAIMED, A.SENDING)).fetchone():
            return None, False, None                                     # нажатие идёт — такт пропускаем
        cl = self.db.execute("SELECT last_in_id, last_in_ts FROM clients WHERE number=?", (number,)).fetchone()
        if not cl:
            return None, False, None
        last_in = int(cl[0])
        if float(cl[1] or 0) > now - self.quiet:
            # тишина ядра (`make_drafts`: quiet после последнего входящего) не вышла — первой на него отвечает модель:
            # её черновик с этим PDF «покроет» версию, а вопрос клиента («подписал, во сколько доставка?») увидит она
            return None, False, None
        if self._signed_wait_live(number):
            return None, False, None                                     # повторное предложение ждёт ответа модели
        ok, why = self._signed_window(number, now)
        if not ok:
            if why.startswith("очередь"):
                self._signed_note((number, "window", why), "номер %s — %s, карточки нет" % (tail, why))
            return None, False, None                                     # окно закрыто — дверей не зовём
        # CASEPDF1510 (M2): клиент сам просит СВОЙ договор? (детектора нет — None без чтения очереди, путь прежний)
        ask = self._signed_asked(number)
        rental, contract = self._signed_find(number, last_in)            # та же аренда, что у привязки договора
        got = rental.get("outcome") if isinstance(rental, dict) else None
        if got in (T.TIMEOUT, T.REFUSED):
            if self._signed_short(number, rental):
                return None, False, "бюджет прохода %d с исчерпан на двери аренды" % SIGNED_PASS_SEC
            self._signed_fail(number, now)
            self._signed_note((number, "rental", got), "номер %s — дверь аренды: %s (%s), карточки нет" % (
                tail, got, str(rental.get("reason") or "")[:80]))
            return None, False, "дверь аренды: %s" % got
        if got != T.FACT:
            self._signed_ok(number)
            return None, False, None                                     # аренды-факта нет — договор не к чему привязать
        got = contract.get("outcome")
        if got in (T.TIMEOUT, T.REFUSED):
            if self._signed_short(number, contract):
                return None, True, "бюджет прохода %d с исчерпан на реестре подписей" % SIGNED_PASS_SEC
            self._cstate_note(number, got, now)     # CSTATE1510: сбой реестра ожидание не закрывает
            self._signed_fail(number, now)
            self._signed_note((number, "find", got, contract.get("reason")), "номер %s — реестр подписей: %s (%s), "
                              "карточки нет" % (tail, got, str(contract.get("reason") or "")[:80]))
            return None, True, "реестр подписей: %s" % got
        if got != T.FACT:
            self._signed_empty(number, last_in, now)
            # CSTATE1510: реестр пуст, а клиент просит договор или сообщил о подписи — ожидание подписи открывается
            self._cstate_note(number, got, now, last_in, ask)
            if got != T.EMPTY:
                self._signed_note((number, "bind", got, contract.get("reason")),
                                  "номер %s — привязка договора не факт (%s), карточки нет" % (tail, got))
            return None, True, None
        self._cstate_note(number, got, now)         # CSTATE1510: подписанный найден — исход проверки ожидания
        c = (contract.get("facts") or [{}])[-1]
        key = (number, str(c.get("doc_id") or "").strip(), str(c.get("signed_at") or "").strip(),
               str(c.get("pdf_id") or "").strip())
        row = c.get("row")
        if not all(key):
            self._signed_idle(number, last_in, now)
            self._signed_note((number, "key") + key[1:], "номер %s, строка реестра %s — у договора нет doc_id, "
                              "signed_at или pdf_id, карточки нет" % (tail, row))
            return None, True, None
        rec = self._signed_record(key)
        reopen = None
        if rec is not None:
            if not self._signed_dead(rec[0]):
                self._signed_idle(number, last_in, now)
                if ask in ASKED:                    # повтор просьбы по решённой версии — назван словами, решает человек
                    st = self.db.execute("SELECT state FROM drafts WHERE id=?", (rec[0],)).fetchone() \
                        if rec[0] is not None else None
                    self._signed_note((number, "ask-decided") + key[1:], W_ASK_REPEAT % (
                        "версия решена черновиком %d (%s)" % (rec[0], state_word(st[0]) if st else "нет в базе")
                        if rec[0] is not None else "документ ушёл человеком"))
                return None, True, None                                  # версия уже решена — одна на версию навсегда
            reopen = rec[0]                                              # «покрытие» сняло ядро — версия снова открыта
        at = signed_epoch(key[2], now)
        if at is None:
            self._signed_idle(number, last_in, now)
            self._signed_note((number, "at") + key[1:], "номер %s, строка реестра %s — время подписи не разобрано, "
                              "карточки нет" % (tail, row))
            return None, True, None
        if at < since:
            if ask not in ASKED:
                self._signed_idle(number, last_in, now, why="since")
                self._signed_note((number, "since") + key[1:], "номер %s, строка реестра %s — подписан раньше "
                                  "водораздела, карточки нет" % (tail, row))
                return None, True, None
            # M2: явная просьба клиента прислать СВОЙ договор сильнее водораздела — версия открыта
            self._signed_note((number, "since-ask") + key[1:], "номер %s, строка реестра %s — подписан раньше "
                              "водораздела, но клиент сам просит договор (%s): версия открыта" % (tail, row, ask))
        meta, why, code_r = self._signed_pdf(contract)
        if not meta:
            got_pdf = code_r if isinstance(code_r, dict) else {}
            if got_pdf.get("outcome") in (T.TIMEOUT, T.REFUSED) and self._signed_short(number, got_pdf):
                return None, True, "бюджет прохода %d с исчерпан на PDF договора" % SIGNED_PASS_SEC
            self._signed_fail(number, now)                               # PDF не прочитан — паузы SIGNED_RETRY подряд
            self._signed_note((number, "meta") + key[1:], "номер %s, строка реестра %s — PDF не приложить: %s" % (
                tail, row, str(why)[:160]))
            pdf = got_pdf.get("outcome")
            return None, True, ("PDF договора: %s" % pdf if pdf in (T.TIMEOUT, T.REFUSED) else None)
        sha = meta["sha256"]
        held = self._signed_held(number, sha, key)
        if held is None:
            human = self._signed_human_doc(number, at)
            held = (None, human) if human else None
        if held is not None:
            self._signed_keep(key, sha, held[0], now, reopen)
            self._signed_idle(number, last_in, now, why="held")
            self.log("подпись: строка реестра %s, sha256 %s… — %s, новой карточки нет" % (
                meta.get("row"), sha[:12], held[1]))
            if ask in ASKED and (held[0] is None or held[1].startswith("этот PDF уже уходил")):
                # PDF уже у клиента (ушёл черновиком или документом человека): второй копии сам код не шлёт
                self._signed_note((number, "ask-held") + key[1:], W_ASK_REPEAT % held[1])
            return None, True, None
        if ask == ASK_MIXED:
            # M2: просьба вместе с другим вопросом — карточки подписи нет, ответ модели не снимается: PDF к нему
            # прикладывает код (M3, `_attach_decide`) при его сверке; клиенту ничего без нажатия. Сюда приходят, только
            # если живого ответа С ЭТИМ PDF нет (иначе версию «покрыл» он, `_signed_held`) — слова говорят, как есть
            self._signed_idle(number, last_in, now, why="mixed")
            live = self._live_draft(number)
            self._signed_note((number, "mixed") + key[1:], "номер %s, строка реестра %s — клиент просит договор вместе "
                              "с другим вопросом: карточки подписи нет — %s" % (tail, row, (
                                  "живой ответ модели (черновик %d) этот PDF не несёт; задним числом код его не "
                                  "прикладывает — решает человек, PDF получит следующий ответ модели" % live[0])
                                  if live else "ответа модели пока нет; PDF к нему приложит код при его сверке"))
            return None, True, None
        did, old, lang, carried = self._signed_insert(number, key, meta, now, at, reopen, rental, contract,
                                                      code_r, last_in, ask=ask)
        if did is None:
            return None, True, None
        self._signed_idle(number, last_in, now, why="card")
        late = now - at > SIGNED_LATE
        self.log("подпись: черновик %d — карточка подписанного договора, строка реестра %s, sha256 %s…, язык %s%s%s%s%s%s"
                 % (did, meta.get("row"), sha[:12], lang.upper(),
                    ", с извинением (с подписи %d мин)" % ((now - at) // 60) if late else "",
                    ", заменён черновик %d" % old if old is not None else "",
                    " (вопрос клиента — из него)" if carried else "",
                    ", версия снова открыта: черновик %d с этим PDF снят ядром" % reopen if reopen is not None else "",
                    ", по просьбе клиента (%s)" % ask if ask in ASKED else ""))
        self._card_new(did, 1, now)                 # очередь карточки легла в транзакции — здесь только первая попытка
        if ask == ASK_PURE and self.autosend:       # M4: нажатие — после прохода, тем же тактом
            self._signed_auto.append(did)
        return did, True, None

    def _signed_find(self, number, upto):
        """Привязка номера — ТЕ ЖЕ двери и тот же код, что у сверки модели (`_signed_doors`, `T.bind_ctx`, `T.call_tool`):
        аренда обращения, затем `contract {}`, привязанный кодом к ней. → (ответ аренды, ответ договора | None — аренда
        не факт). Второй поиск без срока (K07, `_other_term`) договор только НАЗЫВАЕТ, фактом он не бывает никогда —
        здесь не нужен; замыкание аренды держит свой `may_call`, этот запрет его не касается. Один помощник на проход
        подписи (M2) и на PDF к ответу модели по просьбе (M3)."""
        doors = self._signed_doors(number, upto)
        ctx = T.bind_ctx(number, doors, [], self.clock)
        rental = ctx["rental"]()
        if (rental.get("outcome") if isinstance(rental, dict) else None) != T.FACT:
            return rental, None
        ctx["may_call"] = lambda: False
        return rental, T.call_tool("contract", {}, doors, self.clock, ctx)

    def _signed_pdf(self, contract):
        """Договор, привязанный кодом → (метаданные PDF | None, причина, ответ contract_pdf, прочитанный кодом | None).
        Путь реальной модели: `contract {}` без `rental` — договор, привязанный КОДОМ к аренде обращения (`bound_by`, номера
        байков сверены `bind_contract`); байк не сличается второй раз строкой («400СС» кириллицей и «400CC» латиницей —
        один байк). PDF читает код той же дверью (`_code_pdf`)."""
        code = {}

        def read_pdf(pdf_id, results):
            code["r"] = self._code_pdf(pdf_id, results)
            return code["r"]
        meta, why = attach_of({"state": T.DONE, "results": [contract]}, None, read_pdf)
        return meta, why, code.get("r")

    def _signed_insert(self, number, key, meta, now, at, reopen, rental, contract, code, upto, ask=None):
        """Черновик подписи — ОДНОЙ транзакцией: перепроверка (нажатие, пауза, новое входящее, двойник, покрытие, решение
        версии), снятие ждущего, вставка черновика, строки attach и версии, очередь карточки и решённая карточка снятого.
        ask (CASEPDF1510) — черновик рождён явной просьбой клиента: в той же транзакции строка `signed_asks` (ключ дела:
        номер, doc_id, версия; текста клиента нет).
        → (черновик | None, снятый | None, язык, вопрос перенесён?). Исключение — откат, наружу (не легло ничего)."""
        sha = meta["sha256"]
        late = now - at > SIGNED_LATE
        opora = opora_of({"state": T.DONE, "results": [rental, contract]}, None, code=code, mark=OPORA_SIGNED)
        lang = self._signed_lang(number, upto)                          # очередь читается ДО транзакции базы агента
        text = signed_text(lang, late)
        if self._fresh(number, upto):
            # клиент уже написал ещё (очередь — даже то, что скан не разобрал): первой на это отвечает модель, карточка —
            # следующим проходом после её ответа (финальный разбор SIGNEDCARD1410); ничего не легло
            return None, None, lang, False
        self._tx_begin()
        try:
            busy = self.db.execute("SELECT 1 FROM drafts WHERE number=? AND state IN (?,?)",
                                   (number, A.CLAIMED, A.SENDING)).fetchone()
            cl = self.db.execute("SELECT last_in_id, ctx, paused FROM clients WHERE number=?", (number,)).fetchone()
            rec = self._signed_record(key)
            again = (rec[0] if rec else None) != reopen or (rec is None) != (reopen is None)
            if busy or not cl or cl[2] or int(cl[0]) != upto or again or self._signed_held(number, sha, key):
                self._tx_end(ok=False)                  # нажатие, пауза, новое входящее, второй процесс — такт позже
                return None, None, lang, False
            live = self._live_draft(number)
            if reopen is not None and (live is not None or self.db.execute(
                    "SELECT 1 FROM drafts WHERE number=? AND state=?", (number, A.SCHEDULED)).fetchone()):
                self._tx_end(ok=False)                  # повторное предложение не снимает живой ответ модели — такт позже
                return None, None, lang, False
            old = live[0] if live else None
            prev = self.db.execute("SELECT question, q_lang, ver, handoff FROM drafts WHERE id=?", (old,)).fetchone() \
                if old is not None else None
            # CASEPDF1510 (M4): карточка по просьбе снимает ответ, который правил человек или где модель просила человека, —
            # автоотправки у неё не будет (решение человека шаблоном не отменяется), а причины «нужен человек» переходят
            # в карточку подписи: человек увидит, о чём просила модель. Карточка события без просьбы — как прежде
            replaced = self._ask_replaced(old, prev) if ask in ASKED and prev is not None else None
            hand = prev[3] if ask in ASKED and prev is not None and A.handoff_of(prev[3]) != [] else None
            # ждущий без этого PDF снимается тем же условным захватом, что у ядра (`Core._close`): только из pending;
            # не снялся — откат, такт позже
            if old is not None and self.db.execute("UPDATE drafts SET state=?, closed_at=? WHERE id=? AND state=?",
                                                   (A.SUPERSEDED, now, old, A.PENDING)).rowcount != 1:
                self._tx_end(ok=False)
                return None, None, lang, False
            # вопрос клиента и его язык (WACARDQ0410) — из снятого ответа модели: карточка подписи покажет, ЧТО спросил
            # клиент, и шаблон после 24 ч возьмёт его язык; снятого нет — язык этого текста
            did = self.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, kind, ctx, question, "
                                  "q_lang, handoff) VALUES(?,?,1,?,?,?,?,?,?,?,?)",
                                  (number, A.PENDING, text, upto, now, KIND_SIGNED, cl[1], prev[0] if prev else None,
                                   (prev[1] if prev and prev[1] else lang), hand)).lastrowid
            words = W_SIGNED_SUPERSEDED % did
            if old is not None:
                self.db.execute("UPDATE drafts SET reason=? WHERE id=?", (words, old))
                # карточка снятого — решена ЗДЕСЬ ЖЕ (правку несёт очередь `card_out`): сбой после COMMIT её не теряет
                self.db.execute("UPDATE card_out SET state=?, decided_at=COALESCE(decided_at, ?), words=?, "
                                "edit=CASE WHEN message_id IS NULL THEN NULL ELSE ? END, edit_tries=0, edit_unk=0, "
                                "next_at=0 WHERE draft_id=? AND ver=?",
                                (A.CARD_DECIDED, now, words, A.EDIT_WAIT, old, int(prev[2]) if prev else 1))
            self.db.execute("INSERT INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, reason, ts, "
                            "signed_at, number, date_from, date_to, opora) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (did, meta["file_id"], meta["name"], meta["size"], sha, meta["row"], meta["doc_id"], None,
                             now, meta["signed_at"], number, meta["date_from"], meta["date_to"], opora))
            if reopen is None:
                n = self.db.execute("INSERT OR IGNORE INTO signed_cards(number, doc_id, signed_at, file_id, sha256, "
                                    "draft_id, ts) VALUES(?,?,?,?,?,?,?)", key + (sha, did, now)).rowcount
            else:
                n = self.db.execute("UPDATE signed_cards SET draft_id=?, sha256=?, ts=? WHERE number=? AND doc_id=? AND "
                                    "signed_at=? AND file_id=? AND draft_id=?", (did, sha, now) + key + (reopen,)).rowcount
            if n != 1:
                self._tx_end(ok=False)
                return None, None, lang, False
            # CSTATE1510: ожидание подписи номера закрывает карточка — в ЭТОЙ ЖЕ транзакции (откат — не закрыто)
            expect = self._cstate_close(number, now, "card:%d" % did) if self.cstate else 0
            if ask in ASKED:                        # CASEPDF1510: черновик рождён просьбой клиента — ключ дела, без слов
                self.db.execute("INSERT OR REPLACE INTO signed_asks(draft_id, number, doc_id, signed_at, file_id, sha256, "
                                "asked, kind, upto_id, ts, replaced_id, replaced_why) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                (did, number) + tuple(key[1:]) + (sha, ask, ASK_CARD, upto, now, old, replaced))
            # очередь карточки — в той же транзакции: черновик без строки `card_out` никто бы не показал до рестарта
            self.db.execute("INSERT OR IGNORE INTO card_out(draft_id, ver, state, created_at) VALUES(?,1,?,?)",
                            (did, A.CARD_WAIT, now))
            # на это входящее уже есть ответ — пауза повтора модели («модель не дала текста», MODEL_RETRY_SEC) больше
            # ничего не ждёт; клиент напишет ещё — ядро снимет карточку (stale) и спросит модель сразу после тишины,
            # как после любого своего черновика, а не через 5 мин от прежней пустой попытки
            self.db.execute("UPDATE clients SET next_try=0 WHERE number=?", (number,))
            self._tx_end()
        except Exception:                                            # noqa: BLE001
            self._tx_end(ok=False)
            raise
        if old is not None:                         # карточка снятого — исходом, как у ядра (`_close` → `_done`)
            self.log("черновик %d → %s" % (old, A.SUPERSEDED))
            self._done(old, words, now)
        if expect:
            self.log("ожидание подписи: закрыто карточкой подписи %d (ждёт нажатия)" % did)
        return did, old, lang, bool(prev and prev[0])

    def tick(self, now=None):
        now = self.clock() if now is None else now
        made = super().tick(now)
        if self.signed and self.drafts:             # SIGNEDCARD1410: после make_drafts/make_followups ядра
            try:
                self.make_signed_cards(now)
                made = list(made) + list(self.signed_made)
            except Exception as e:                                   # noqa: BLE001
                self.log("подпись: такт упал: %s" % type(e).__name__)
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
