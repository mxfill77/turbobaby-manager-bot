# -*- coding: utf-8 -*-
"""Агент WhatsApp с инструментами чтения и журналом (AGENTLOOPA0310, Т4а). Флаг WA_AGENT_TOOLS, по умолчанию выкл.

Было (9c4aac6): черновик — ОДИН вызов модели (`wa_agent_model.ModelAdapter.draft`), всё, что модель знает, код кладёт
в промпт заранее. Стало (флаг вкл): модель САМА выбирает, что прочитать, — до MAX_CALLS вызовов и MAX_SEC секунд на
черновик; каждый вызов и ответ двери пишутся в журнал. Суммы, разности и денежные роли считает КОД из принятых
фактов, а не модель: модель лишь пишет текст, код его проверяет (правило владельца 03.10.2026-1 узла business_rules).

Инструменты — только чтение, двери подаются снаружи (в тестах подмены):
  history  — переписка (очередь и архив WA);            rental   — аренда (снимок броней, номер WhatsApp);
  cash     — касса (`bridge_client.tx_find`);           contract — договор (`contract_find`);
  contract_pdf — метаданные подписанного PDF (`contract_pdf`; содержимое отбрасывается — отправка PDF это Т4б);
  delivery — Delivery: двери нет, исход всегда «неизвестно»;  rules — правила (узел мозга business_rules).

Ответ каждого инструмента: tool · outcome · source · ref · at (начало нашего запроса) · read_at (время данных; у
снимков — время снимка) · source_version (+ source_version_basis) · version (мёртвое, пусто) · window · reason · facts.
Фактом считается ТОЛЬКО outcome == FACT. Отказ, таймаут, пусто, отменено, неоднозначно, неизвестно и неполная
выборка — не факт: они идут в журнал отказов, суждения на них не строятся.

Касса: факт — строка с источником (row, msg_id или link, время), связью с арендой (booking_id или байк и срок) и
ролью по category. `checked.complete` не True (нет поля — дверь до TXFINDFIX, ветка tx-find-0310 = 83ee219; обрезка;
строки без дня) — выборка неполная, суммы и даты «не проверено», оплату такая выборка не подтверждает. Общий
`total` двери не читается вовсе: оплату и залог он не подтверждает.

Договор (AGENTFIX0410, Т4а ч.1): факт — только ответ двери `one` с подписанным `pick`, пустым `checked.unread` и
`checked.undated_signed` = 0 (неподписанные строки без дня допустимы); `unread` непуст — «реестр прочитан не целиком,
мог скрыть другой подписанный», `incomplete` двери и ответ без полей полноты (дверь до CONTRACTFIX0410) — INCOMPLETE.
Привязка — кодом, а не аргументами модели: телефон договора (или ник, сверенный дверью по номеру обращения) совпадает
с номером обращения по последним 9 цифрам; номер байка договора — с байком аренды из `rental` (аренду код читает сам);
дата договора — внутри срока аренды, оба дня включительно. Не совпало — CONFLICT с причиной; не проверить или аренды
нет — не факт. PDF — факт только для `pdf_id` принятого договора.

Ожидание и другие клиенты: черновики служба делает по одному за такт (`wa_agent.Core.make_drafts`), поэтому сверка
одного клиента держит остальных не дольше MAX_SEC. Новое входящее посреди сверки (`fresh()`) обрывает её сразу:
черновика нет, служба повторит позже — как и сегодня после модели.

Опора (AGENTDEDUP0410, Т4а ч.2) — каждый факт ОДИН раз и в ПОСЛЕДНЕЙ версии (`sift`):
  * ответ запроса — последний: тот же инструмент с теми же аргументами прочитан снова — прежний ответ не опора; позднее
    не-FACT того же запроса (отказ, таймаут, неполнота) снимает прежний FACT;
  * идентичность факта (`fact_key`): касса — источник + row + msg_id|link; договор — row + doc_id; аренда — booking_id;
    PDF — id. Одна строка, прочитанная двумя запросами, считается один раз, версия — последнего прочтения;
  * свежесть: ответ, прочитанный раньше последнего входящего клиента (`since`), устарел и не опора.
calc и pay_confirmed видят только отсеянное. Оплата подтверждена, только если аренда обращения одна (`rental_of`), строка
кассы оплаты — этой аренды, и второй источник — той же аренды (договор, привязанный к ней кодом, либо её строка листа
«клиенты» вместе с той же суммой в переписке).

Деньги одной аренды (T4BFACTS0410, Т4б шаг 2): сумма кода, опора чисел ответа и сумма, которую текст называет полученной
оплатой, — только строки кассы аренды обращения (`cash_split`); прочая наличность — «не привязано», в сумму и в опору не
входит. Аренды обращения нет — сумма берётся, только если вся наличность и все аренды опоры называют одну и ту же аренду
(она единственная в поле зрения); подтверждения оплаты без аренды обращения по-прежнему нет. Версия факта — по НАЧАЛУ
запроса (`at` ставит `_read` до вызова двери), а не по приходу ответа (`read_order`): новейшее прочтение ключа снято
(отказ, неизвестность, неполнота того же запроса или его новый ответ без этой строки) — факт не подтверждён, и старая
версия из другого запроса не возвращается.

Общий предел (AGENTDEDUP0410): дедлайн t0 + MAX_SEC на ВСЮ сверку, включая запасной вызов. Сверка не начинает вызовов
(модели и дверей, включая аренду, которую код читает сам) после t0 + MAX_SEC − FALLBACK_SEC; остаток — запасному
обычному вызову. Запасной вызов начинается только до дедлайна; после дедлайна вызовов нет — черновика нет, служба
повторит (`MODEL_RETRY_SEC`). Уже идущий синхронный вызов этот код не обрывает — его держит собственный таймаут двери.

K3-FIX шаг 3 (09–10.10.2026): договор ищется в ДОВЕРЕННОМ контексте обращения (`contract_query`: номер обращения и
срок аренды подставляет код; чужой или противоречивый фильтр модели — CONFLICT с причиной, реестр не читается, привязка
не подменяется; в сроке нет — тот же номер без срока только НАЗЫВАЕТ договор другой аренды, `_other_term`; тождество
запроса — запрос кода); сдача — детерминированно кодом (`change_of`, блок «РАСЧЁТ КОДА»), слова клиента оплатой не становятся;
утвердительные формы оплаты («вижу оплату», «оплата отражена», «с оплатой всё в порядке») ловит то же определение
`_PAY_CLAIM`, отрицание и обещание проверки — нет; поле `version` больше не пишется: версия — только `source_version` от
источника (сегодня null, «источник версии не отдаёт»), время данных — `read_at` (у снимков — время СНИМКА).
K3-FIX шаг 3b (10.10.2026, D1 приёмки): то же определение ловит утвердительные ФОРМЫ оплаты («аренда оплачена»,
«платёж получен», «оплата зафиксирована/есть в кассе», «деньги получили», «your payment went through»), а не список
фраз (`_PAY_FORMS`, второй проход `_PayClaim`); прежние формы не тронуты.
K3-FIX шаг 3c (10.10.2026): у каждого совпадения определения — НАЗВАННЫЙ исход (`_PayClaim.verdict`: «утверждение»
либо имя того, почему это не утверждение; пустым исход не бывает, `explain` отдаёт исходы наружу), и исключения
не-утверждений — одни на оба прохода: долженствование и ожидание («должна быть получена», «требует подтверждения»),
предмет после предлога цели или времени («ссылку на оплату получили», «после оплаты …»), основа сказуемого внутри
другого слова («пришлём», «прошлую», «при получении»), документ вместо оплаты («перевод договора», «payment details»).
K3-FIX шаг 3d (10.10.2026, независимая проверка 3b+3c, R1–R3): исключения шага 3c сужены до своего места — слово
долженствования снимает утверждение, только когда управляет САМИМ сказуемым оплаты («должна быть получена»), а не стоит
при другом глаголе главной части («You should know that your payment has been received», «должна была поступить вчера и
поступила»); предлог цели перед словом оплаты — только при слове документа перед ним («ссылку на оплату», а не «7790 бат
на оплату аренды получены», «Thank you for the payment received»). Третий проход того же определения (`_PAY_SUMS`):
подтверждение получения отглагольным существительным («подтверждаю получение оплаты», «confirm receipt of your
payment») и глагол получения с денежной суммой или словом суммы без слова «оплата» («получили 7790 бат», «сумма
получена», «деньги у нас»).
K3-FIX шаг 3e (10.10.2026, решение координатора после круга 3d): четвёртый проход того же определения (`_PAY_CTX`) —
три семейства, которых текст САМ оплатой не называет: краткое утвердительное получение или подтверждение без предмета
(«Да, всё пришло.», «Получили, спасибо.», «We got it, thanks!») — утверждение, только когда входящее клиента об оплате
(`pay_asked`; признак адаптер передаёт в `run` и `judge` тем же местом, что `cash_said`); «долга нет» («задолженности
по аренде нет», «ничего не должны», «счёт закрыт», «no balance due», «all settled»); число без валюты при сказуемом
получения («Да, 7790 получили.») — когда оно равно известной денежной сумме сверки (`pay_sums`) либо входящее об оплате.
K3-FIX шаг 3g (10.10.2026, решение координатора после проверки 3d+3e+3f, блокеры D1 и D2): правило КЛАССА рядом со
словарём, а не ещё одно слово в нём, — тема оплаты открыта (`pay_topic`: хвост клиента, предыдущий обмен или наш последний
ответ об оплате) и оплата кодом не подтверждена (`pay_verdict`) ⇒ причина кода «нужен человек» при ЛЮБОМ тексте ответа
(`topic_reason`; слова причины — существующие `K.MONEY_WORDS`). Определение N4 и `pay_asked` не тронуты.
Вторая часть шага 3g (остатки Р1, Р2, Р5 первой части): тема оплаты — СОСТОЯНИЕ переписки, а не окно в один обмен.
Открытая тема остаётся открытой для всех следующих сообщений, пока её не закроет наше более раннее подтверждение оплаты
в переписке или давность (`PAY_TOPIC_HOURS`); история судится от хвоста назад обмен за обменом. Новых слов нет.
"""

import json
import re
import time

import wa_agent_knowledge as K
import wa_book_read as B

MAX_CALLS = 8                 # вызовов модели на один черновик
MAX_SEC = 90.0                # секунд на сверку одного черновика — ВКЛЮЧАЯ запасной вызов (AGENTDEDUP0410)
FALLBACK_SEC = 30.0           # остаток предела, который сверка не тратит: он — запасному обычному вызову

FACT, EMPTY, REFUSED, TIMEOUT = "fact", "empty", "refused", "timeout"
CANCELLED, AMBIGUOUS, UNKNOWN, INCOMPLETE = "cancelled", "ambiguous", "unknown", "incomplete"
CONFLICT = "conflict"         # ответ двери есть, но не этого клиента / не этой аренды (AGENTFIX0410)
OUTCOMES = (FACT, EMPTY, REFUSED, TIMEOUT, CANCELLED, AMBIGUOUS, UNKNOWN, INCOMPLETE, CONFLICT)

DONE, OVER, ABORTED = "done", "over", "aborted"        # исход сверки

TOOLS = ("history", "rental", "cash", "contract", "contract_pdf", "delivery", "rules")

INCOMPLETE_WORDS = "сверка не завершена"
PAY_WORDS = "оплата не подтверждена сверкой"
ROLE_WORDS = "денежная роль не сходится с кассой"
SUMS_WORDS = "суммы расходятся"
UNREAD_WORDS = "реестр прочитан не целиком, мог скрыть другой подписанный"
CONTRACT_WORDS = "договор не этого клиента или не этой аренды"
UNBOUND_WORDS = "не привязано"   # наличность не аренды обращения: в сумму и в опору не входит (T4BFACTS0410)

# роли денег по category кассы (splinter: rental|salary|advance|fuel|taxi|topup|other; deposit — passport|cash|null)
R_RENT, R_DEPOSIT, R_REFUND, R_OTHER = "оплата аренды", "залог", "возврат", "прочее"

_DEP_WORDS = re.compile(r"залог|депозит|deposit", re.I)
_REFUND_WORDS = re.compile(r"возврат|вернул|refund|return", re.I)
_CANCEL = re.compile(r"void|отмен|cancel", re.I)


def role_of(item):
    """Строка кассы → роль. Знак суммы и category решают; слова описания отличают залог от оплаты аренды."""
    cat = str(item.get("category") or "").strip().lower()
    words = " ".join(str(item.get(k) or "") for k in ("description", "raw"))
    amount = item.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return R_OTHER
    if amount < 0 and (_REFUND_WORDS.search(words) or _DEP_WORDS.search(words) or cat == "rental"):
        return R_REFUND
    if amount > 0 and _DEP_WORDS.search(words):
        return R_DEPOSIT
    if amount > 0 and cat == "rental":
        return R_RENT
    return R_OTHER


SV_BASIS = "источник версии не отдаёт"     # K3-FIX3 (F2_CONTRACT §0.1, §1.1): ни одна дверь сегодня версию данных не выдаёт
_AT = object()                              # read_at не передан — время данных = `at` (прямые двери: часы до вызова двери)


def result(tool, outcome, source="", ref="", at=None, version="", window="", reason="", facts=None, read_at=_AT):
    """Ответ инструмента. K3-FIX3 (F2-честность): `version` — мёртвое поле, код его больше не заполняет (заполнители
    `signed_at`/«N симв.» версией источника не являются, F2_CONTRACT §0.3, §1.5); версия — ТОЛЬКО `source_version`,
    выданная источником по явному контракту двери (сегодня такой нет ни у одной двери: null + `source_version_basis`);
    `read_at` — время ДАННЫХ: у прямых дверей = `at`, у снимочных (rental, rules) — время СНИМКА или None (неизвестно;
    время вызова старый снимок свежим не делает). `at` по-прежнему — начало НАШЕГО запроса (порядок и свежесть `sift`)."""
    return {"tool": tool, "outcome": outcome, "source": source, "ref": ref, "at": at, "version": version,
            "window": window, "reason": reason, "facts": list(facts or []),
            "source_version": None, "source_version_basis": SV_BASIS, "read_at": at if read_at is _AT else read_at}


# ------------------------------- разбор ответов дверей -------------------------------

def _refusal(tool, resp, source, at):
    err = str((resp or {}).get("error") or "ответ без ok") if isinstance(resp, dict) else "ответ не словарь"
    if err == "unknown_action":
        return result(tool, UNKNOWN, source, at=at, reason="дверь не выложена (unknown_action) — не просмотрено")
    return result(tool, REFUSED, source, at=at, reason=err)


def cash_result(resp, at=None):
    src = "касса Bot Data «транзакции» (tx_find)"
    if not (isinstance(resp, dict) and resp.get("ok")):
        return _refusal("cash", resp, src, at)
    checked = resp.get("checked") if isinstance(resp.get("checked"), dict) else {}
    window = "%s…%s" % (checked.get("span_from") or "?", checked.get("span_to") or "?")
    complete = checked.get("complete") is True and not checked.get("truncated")
    facts, bad = [], []
    for it in resp.get("items") or []:
        if not isinstance(it, dict):
            continue
        if _CANCEL.search(str(it.get("status") or "")):
            bad.append("строка %s отменена" % it.get("row"))
            continue
        amount = it.get("amount")
        when = it.get("date") or it.get("recorded_at")
        link = it.get("booking_id") or (it.get("bike") and window != "?…?" and "%s %s" % (it.get("bike"), window))
        if (it.get("row") is None or not (it.get("msg_id") or it.get("link")) or not when or not link
                or not isinstance(amount, (int, float)) or isinstance(amount, bool) or not it.get("currency")):
            bad.append("строка %s без источника, связи с арендой или суммы" % it.get("row"))
            continue
        facts.append({"kind": "cash", "src": "tx_find", "row": it.get("row"), "msg_id": it.get("msg_id"),
                      "link": it.get("link"),
                      "at": when, "booking_id": it.get("booking_id"), "bike": it.get("bike"), "amount": amount,
                      "currency": str(it.get("currency")).upper(), "role": role_of(it),
                      "category": it.get("category")})
    rows = checked.get("rows_scanned")
    if not complete:
        why = ("выборка неполная (checked.complete=%s, обрезка=%s) — суммы и даты «не проверено»"
               % (checked.get("complete", "нет поля: дверь до TXFINDFIX"), bool(checked.get("truncated"))))
        return result("cash", INCOMPLETE, src, ref="строк %s" % rows, at=at, window=window,
                      reason="; ".join([why] + bad), facts=facts)
    if not facts:
        return result("cash", CANCELLED if bad and all("отменена" in b for b in bad) else EMPTY, src,
                      ref="строк %s" % rows, at=at, window=window,
                      reason="; ".join(bad) or "просмотрено %s строк за %s, проводок нет" % (rows, window))
    return result("cash", FACT, src, ref="строк %s" % rows, at=at, window=window, reason="; ".join(bad), facts=facts)


_CC = frozenset(("125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"))   # = plateOf_ моста
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def plate_of(text):
    """Номер байка — как plateOf_ моста (BotData.js): последнее число от 3 цифр, не кубатура. Нет — ""."""
    nums = [n for n in re.findall(r"\d{3,}", str(text or "").lower()) if n not in _CC]
    return nums[-1] if nums else ""


def last9(value):
    d = re.sub(r"\D", "", str(value or ""))
    return d[-9:] if len(d) >= 9 else ""


def contract_phones(cell):
    """Последние 9 цифр каждого номера ячейки «Телефон» — как esignPhones_ двери (делители , ; / | и перевод строки)."""
    return [p for p in (last9(piece) for piece in re.split(r"[,;/|\n]+", str(cell or ""))) if p]


def phone_country_clash(cell, number):
    """Номер договора совпал с обращением ТОЛЬКО хвостом 9 цифр, а записан с ЯВНЫМ кодом страны («+» или «00»), и
    полный номер другой → True (NIGHT0710-B3v, второй круг, R12: «+7 981 234-56-78» и 66812345678 — разные люди с одним
    хвостом). Номер без явного кода («081…», «8 981…») сверяется по-прежнему хвостом — местную запись не судим."""
    key = last9(number)
    full = re.sub(r"\D", "", str(number or ""))
    hits = [p for p in re.split(r"[,;/|\n]+", str(cell or "")) if key and last9(p) == key]
    if not hits:
        return False
    for piece in hits:
        raw = piece.strip()
        d = re.sub(r"\D", "", raw)
        intl = d if raw.startswith("+") else d[2:] if d.startswith("00") else ""
        # «+66 081…» (лишний ноль после кода) — тот же номер: сравниваются приставки до хвоста без конечных нулей
        if not intl or intl[:-9].rstrip("0") == full[:-9].rstrip("0"):
            return False                            # хоть одна запись этого номера — местная или та же целиком
    return True


def _tail(key):
    return "…" + key[-4:] if key else "—"


def bind_contract(fact, resp, number, rental, ref="", at=None):
    """Принятый по полноте договор → FACT, только если он этого номера и этой аренды. Сверяет код:
    номер — телефон договора (или ник, который дверь сверила с ЭТИМ номером: `matched_on` nick и
    `filter.phone_last9` = номер обращения), байк — номером с байком аренды, дата — в сроке аренды включительно.
    Расхождение — CONFLICT с причиной; не проверить (поля пусты, аренды нет или она не одна) — UNKNOWN."""
    src = "реестр подписей TB e-Sign (contract_find)"
    key = last9(number)
    if not key:
        return result("contract", UNKNOWN, src, ref, at, reason="номер обращения не назван — договор не к чему привязать")
    flt = resp.get("filter") if isinstance(resp.get("filter"), dict) else {}
    on = fact.get("matched_on") if isinstance(fact.get("matched_on"), list) else []
    phones = contract_phones(fact.get("phone"))
    if key in phones and phone_country_clash(fact.get("phone"), number):
        return result("contract", CONFLICT, src, ref, at, reason="договор другого номера: телефон договора с кодом "
                      "страны совпал с обращением только последними 9 цифрами (%s), полный номер другой" % _tail(key))
    if key in phones:
        by = "телефон"
    elif "nick" in on and str(flt.get("phone_last9") or "") == key:
        by = "ник"
    elif phones or "nick" in on:
        return result("contract", CONFLICT, src, ref, at, reason="договор другого номера: %s %s, обращение %s" % (
            "ник" if not phones else "телефон", _tail(phones[0] if phones else str(flt.get("phone_last9") or "")),
            _tail(key)))
    else:
        return result("contract", UNKNOWN, src, ref, at, reason="телефон договора пуст, ник не сверен — номер не проверен")
    if not isinstance(rental, dict) or rental.get("outcome") != FACT or len(rental.get("facts") or []) != 1:
        return result("contract", UNKNOWN, src, ref, at, reason="аренда обращения не установлена (rental: %s) — "
                      "договор не к чему привязать" % ((rental or {}).get("outcome") if isinstance(rental, dict) else "—"))
    rent = rental["facts"][0]
    pc, pr = plate_of(fact.get("bike")), plate_of(rent.get("bike"))
    if not pc or not pr:
        return result("contract", UNKNOWN, src, ref, at, reason="номер байка не разобран (договор %s, аренда %s)"
                      % (pc or "—", pr or "—"))
    if pc != pr:
        return result("contract", CONFLICT, src, ref, at, reason="байк договора %s, байк аренды %s" % (pc, pr))
    cd = str(fact.get("contract_date") or "")
    ds, de = B.day_of(rent.get("date_start")), B.day_of(rent.get("date_end"))
    if not _ISO_DAY.match(cd) or ds is None or de is None:
        return result("contract", UNKNOWN, src, ref, at, reason="день договора или срок аренды неизвестен (%s; %s…%s)"
                      % (cd or "—", ds or "—", de or "—"))
    if not ds.isoformat() <= cd <= de.isoformat():
        return result("contract", CONFLICT, src, ref, at, reason="дата договора %s вне срока аренды %s…%s"
                      % (cd, ds.isoformat(), de.isoformat()))
    # rent_currency (K3-FIX F3): валюта аренды, к которой код привязал договор — опора `pay_verdict`, когда строки листа
    # среди фактов нет; в `_fact_ref` ключа нет — модели и журналу договор показывается прежним
    bound = dict(fact, booking_id=rent.get("booking_id"), bound_by=by, rent_currency=rent.get("currency"))
    # K3-FIX3 (F2): `signed_at` — время подписи, а не версия источника; он лежит в факте, поле `version` не пишется
    return result("contract", FACT, src, ref, at,
                  window="%s…%s" % (ds.isoformat(), de.isoformat()),
                  reason="привязан: номер по полю «%s», байк %s, дата %s в сроке аренды" % (by, pc, cd), facts=[bound])


def contract_result(resp, at=None, number="", rental=None):
    """Ответ contract_find → результат. Факт — только `one` + подписанный pick + пустой `unread` + `undated_signed` = 0,
    и только после привязки к номеру и аренде обращения (`bind_contract`)."""
    src = "реестр подписей TB e-Sign (contract_find)"
    if not (isinstance(resp, dict) and resp.get("ok")):
        return _refusal("contract", resp, src, at)
    out = resp.get("outcome")
    checked = resp.get("checked") if isinstance(resp.get("checked"), dict) else {}
    ref = "строк %s" % checked.get("rows_scanned")
    if out == "ambiguous":
        return result("contract", AMBIGUOUS, src, ref, at, reason="подписанных несколько — выбрать нельзя")
    if out == "incomplete":
        why = (resp.get("reason") or {}).get("message") if isinstance(resp.get("reason"), dict) else ""
        return result("contract", INCOMPLETE, src, ref, at,
                      reason="дверь: ответ неполон — %s" % (why or "подписанный без известного дня"))
    if out in ("none", "none_signed"):
        return result("contract", EMPTY, src, ref, at,
                      reason="подписанного нет" if out == "none_signed" else "договор не найден")
    pick = resp.get("pick") if isinstance(resp.get("pick"), dict) else None
    if out != "one" or not pick or pick.get("signed") is not True:
        return result("contract", UNKNOWN, src, ref, at, reason="исход двери не разобран: %s" % out)
    unread, undated_signed = checked.get("unread"), checked.get("undated_signed")
    if (not isinstance(unread, list) or not isinstance(undated_signed, int) or isinstance(undated_signed, bool)):
        return result("contract", INCOMPLETE, src, ref, at,
                      reason="нет полей полноты unread/undated_signed — дверь до CONTRACTFIX0410, ответ не судим")
    if unread:
        return result("contract", INCOMPLETE, src, ref, at,
                      reason="%s (не прочитано: %s)" % (UNREAD_WORDS, ", ".join(str(u) for u in unread)))
    if undated_signed != 0:
        return result("contract", INCOMPLETE, src, ref, at,
                      reason="подписанных без известного дня %d — выбрать один нельзя" % undated_signed)
    fact = {"kind": "contract", "row": pick.get("row"), "doc_id": pick.get("doc_id"), "bike": pick.get("bike"),
            "contract_date": pick.get("contract_date"), "signed_at": pick.get("signed_at"),
            "pdf_id": pick.get("pdf_id"), "phone": pick.get("phone"), "matched_on": pick.get("matched_on")}
    return bind_contract(fact, resp, number, rental, ref, at)


def pdf_result(resp, at=None, allowed=()):
    """PDF — факт только для `pdf_id` ПРИНЯТОГО договора (`allowed`): чужой файл к ответу не прикладывается."""
    src = "подписанный PDF (contract_pdf)"
    if not (isinstance(resp, dict) and resp.get("ok")):
        return _refusal("contract_pdf", resp, src, at)
    if resp.get("verified") is not True:
        return result("contract_pdf", REFUSED, src, at=at, reason="длина и sha256 не сверены клиентом")
    if not resp.get("id") or resp.get("id") not in set(allowed or ()):
        return result("contract_pdf", REFUSED, src, ref=str(resp.get("id") or ""), at=at,
                      reason="PDF не принятого договора этой аренды — не прикладывается")
    return result("contract_pdf", FACT, src, ref=str(resp.get("id") or ""), at=at, facts=[{   # без content_b64
        "kind": "pdf", "id": resp.get("id"), "name": resp.get("name"), "size": resp.get("size"),
        "sha256": resp.get("sha256"), "row": resp.get("row")}])


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def snap_time(resp):
    """K3-FIX3 (F2): время СНИМКА, которое снимочная дверь передала зарезервированным ключом `_taken_at` → эпоха | None.
    Не передано — None («неизвестно»), а не время вызова: свежий вызов старый снимок свежим не делает."""
    t = resp.get("_taken_at") if isinstance(resp, dict) else None
    return float(t) if _num(t) and t > 0 else None


def rental_result(resp, at=None):
    src = "снимок броней (лист «клиенты»)"
    taken = snap_time(resp)                          # K3-FIX3 (F2): время факта аренды — время снимка, а не вызова
    if not (isinstance(resp, dict) and resp.get("ok")):
        return dict(_refusal("rental", resp, src, at), read_at=taken)
    rows = [r for r in resp.get("rows") or [] if isinstance(r, dict)]
    live = [r for r in rows if not _CANCEL.search(str(r.get("status") or ""))]
    if rows and not live:
        return result("rental", CANCELLED, src, at=at, reason="аренды по номеру отменены", read_at=taken)
    if not live:
        return result("rental", EMPTY, src, at=at,
                      reason="по номеру аренда не найдена — это «не знаю», а не «аренды нет»", read_at=taken)
    if len(live) > 1:
        return result("rental", AMBIGUOUS, src, at=at, reason="аренд по номеру %d — выбрать нельзя" % len(live),
                      read_at=taken)
    r = live[0]
    return result("rental", FACT, src, ref=str(r.get("booking_id") or r.get("bike") or ""), at=at,
                  window="%s…%s" % (r.get("date_start") or "?", r.get("date_end") or "?"), facts=[{
                      "kind": "rental", "booking_id": r.get("booking_id"), "bike": r.get("bike"),
                      "date_start": r.get("date_start"), "date_end": r.get("date_end"), "status": r.get("status"),
                      "price": r.get("price") if isinstance(r.get("price"), (int, float)) else None,
                      # K3-FIX3 п.2: итог аренды по листу «клиенты» (колонка J «к оплате», ReadClients.js:48, 106) —
                      # опора расчёта сдачи (`change_of`); в `_fact_ref` ключа нет — модели и журналу факт прежний
                      "to_pay": r.get("to_pay") if _num(r.get("to_pay")) else None,
                      "currency": str(r.get("currency") or "THB").upper()}], read_at=taken)


def history_result(items, at=None):
    src = "переписка WA (очередь + архив)"
    if items is None:
        return result("history", REFUSED, src, at=at, reason="история не прочитана")
    if not items:
        return result("history", EMPTY, src, at=at, reason="переписки нет")
    text = "\n".join(str(it.get("text") or "") for it in items if isinstance(it, dict))
    return result("history", FACT, src, ref="строк %d" % len(items), at=at, facts=[{
        "kind": "history", "items": len(items), "amounts": sorted(set(K.thb_amounts(text)))}])


def rules_result(node, at=None):
    src = "мозг business_rules"
    if not isinstance(node, dict) or not node.get("read") or not node.get("text"):
        return result("rules", REFUSED, src, at=at, reason="узел не прочитан", read_at=None)
    taken = node.get("taken_at") if _num(node.get("taken_at")) else None   # K3-FIX3 (F2): время СНИМКА узла
    if K.node_stale(node, at):
        # K3-FIX F5: снимок старше своего предела — тот же признак, по которому промпт уже говорит НЕИЗВЕСТНО
        # (`K.node_block`): FACT со временем «сейчас» подал бы устаревшее модели как свежее
        age = K.node_age(node, at)
        return result("rules", UNKNOWN, src, ref="business_rules", at=at,
                      reason="снимок правил устарел: снят %d мин назад, предел %d мин — НЕИЗВЕСТНО, не факт"
                      % (int((age or 0) // 60), int(node["max_stale"]) // 60), read_at=taken)
    text = str(node["text"])
    # K3-FIX3 (F2): длина текста — не версия источника (тексты одной длины совпадут); она в факте `len`
    return result("rules", FACT, src, ref="business_rules", at=at, read_at=taken, facts=[{
        "kind": "rules", "len": len(text), "rule_0310": "03.10.2026-1" in text}])


# ------------------------------- вызов двери -------------------------------

_PHONE = re.compile(r"\+?\d[\d\s()-]{7,}\d")


def masked(args):
    """Вход инструмента для журнала без персональных данных: телефон — последние 4 цифры, имя — «[имя]»."""
    out = {}
    for k, v in sorted((args or {}).items()):
        s = str(v)
        if k == "name":
            s = "[имя]"
        elif k == "phone" or _PHONE.fullmatch(s.strip()):
            d = re.sub(r"\D", "", s)
            s = "…" + d[-4:] if d else ""
        out[k] = s[:60]
    return out


def request_key(tool, args):
    """Тождество ЗАПРОСА (AGENTDEDUP0410): инструмент + аргументы без пустых, пробелы и регистр сведены. Тот же запрос,
    прочитанный снова, заменяет прежний ответ — и позднее «не факт» снимает прежний факт."""
    norm = sorted((str(k), re.sub(r"\s+", " ", str(v)).strip().lower()) for k, v in (args or {}).items()
                  if v is not None and str(v).strip() != "")
    return "%s %s" % (tool, json.dumps(norm, ensure_ascii=False))


def _rent_one(rental):
    """Аренда обращения, которую код прочитал сам: ровно одна строка FACT → её факт | None."""
    if isinstance(rental, dict) and rental.get("outcome") == FACT and len(rental.get("facts") or []) == 1:
        return rental["facts"][0]
    return None


def contract_query(args, number, rental):
    """K3-FIX шаг 3 п.1: поиск договора — в ДОВЕРЕННОМ контексте обращения, а не по догадке модели.
    → (вход двери `contract_find` | None, причина конфликта | "", слова поиска для ответа).

    Модель выбирает ДЕЙСТВИЕ («договор»), фильтр ставит код: телефон = номер обращения (тот же, по которому договор
    привязывается в `bind_contract`), срок = дни аренды обращения, которую код читает сам (тот же ключ, что у
    перечитывания перед отправкой `wa_agent_attach.recheck_of`). Номер байка модели угадывать не нужно. Фильтр
    модели в поиск НЕ идёт: телефон, байк и период лишь сверяются с привязкой; явный чужой или противоречивый
    (другой номер по 9 цифрам или по явному коду страны, другой байк, другой период) — конфликт с причиной, реестр
    не читается, привязка не подменяется. Имя модели проверить кодом нечем — в поиск не идёт. Номера обращения нет —
    поиска нет (без связи с клиентом реестр не читаем)."""
    key = last9(number)
    if not key:
        return None, "", "номер обращения не назван"
    q = {"phone": str(number)}
    rent = _rent_one(rental)
    ds = B.day_of(rent.get("date_start")) if rent else None
    de = B.day_of(rent.get("date_end")) if rent else None
    if ds is not None and de is not None:
        q["date_from"], q["date_to"] = ds.isoformat(), de.isoformat()
    words = "поиск привязан кодом: номер обращения %s, %s" % (
        _tail(key), ("срок аренды %s…%s" % (q["date_from"], q["date_to"])) if "date_from" in q
        else "срок аренды неизвестен")
    a = args if isinstance(args, dict) else {}
    other, clash = [], []
    phone = str(a.get("phone") or "").strip()
    if phone and (last9(phone) != key or phone_country_clash(phone, number)):
        other.append("телефон %s, обращение %s" % (_tail(last9(phone) or re.sub(r"\D", "", phone)), _tail(key)))
    bike = str(a.get("bike") or "").strip()
    if bike and rent:
        pm, pr = plate_of(bike), plate_of(rent.get("bike"))
        if pm and pr and pm != pr:
            clash.append("байк %s, байк аренды %s" % (pm, pr))
    for k in ("date_from", "date_to"):
        v = str(a.get(k) or "").strip()
        if v and k in q and (B.day_of(v) is None or B.day_of(v).isoformat() != q[k]):
            clash.append("%s %s, срок аренды %s…%s" % (k, v[:20], q["date_from"], q["date_to"]))
    if other:
        return None, ("договор другого номера: фильтр модели — %s; чужой реестр не читаю, привязку к обращению не "
                      "подменяю" % "; ".join(other + clash)), words
    if clash:
        return None, ("договор другой аренды: фильтр модели — %s; поиск вне аренды обращения не делаю, привязку не "
                      "подменяю" % "; ".join(clash)), words
    return q, "", words


def _other_term(empty, door, q, at, number, rental):
    """K3-FIX3 п.1 (K07): в сроке аренды обращения подписанного договора нет (`empty` — EMPTY поиска со сроком). Тот же
    номер обращения БЕЗ срока — только чтобы НАЗВАТЬ договор другой аренды, а не принять его: `one` привязывает код
    (`bind_contract` → CONFLICT «дата договора вне срока аренды»), подписанных несколько → CONFLICT. Фактом второй поиск
    не становится никогда: FACT здесь — противоречие двери (в сроке не нашла, без срока нашла договор в сроке) →
    UNKNOWN. Не найдено, отказ, таймаут второго поиска — прежнее EMPTY поиска в сроке."""
    try:
        raw = door(phone=q["phone"])
    except Exception:                                               # noqa: BLE001 — второй поиск — не опора
        return empty
    if not (isinstance(raw, dict) and raw.get("ok")):
        return empty
    wide = contract_result(raw, at, number=number, rental=rental)
    if wide["outcome"] == EMPTY:
        return empty
    head = "в сроке аренды %s…%s подписанного договора нет; без срока по номеру обращения: " % (
        q.get("date_from"), q.get("date_to"))
    if wide["outcome"] == FACT:
        return result("contract", UNKNOWN, wide["source"], wide["ref"], at,
                      reason=head + "найден договор В сроке — ответы двери противоречат друг другу, не факт")
    if wide["outcome"] == AMBIGUOUS:
        return result("contract", CONFLICT, wide["source"], wide["ref"], at,
                      reason=head + "подписанных несколько — договор другой аренды, не прикладываю")
    return dict(wide, reason=head + wide["reason"])


def call_tool(tool, args, doors, clock=time.time, ctx=None):
    """Имя + вход → результат по контракту, с тождеством запроса `req` (AGENTDEDUP0410). K3-FIX3: у договора
    тождество — запрос, который код ПОСЛАЛ в дверь (`_read` кладёт его в `req`), а не аргументы модели: два вызова
    с разными словами модели и одним запросом двери — один запрос для `sift`."""
    res = _read(tool, args, doors, clock, ctx)
    res.setdefault("req", request_key(tool, args))
    return res


def _read(tool, args, doors, clock=time.time, ctx=None):
    """Имя + вход → результат по контракту. Двери нет · исключение · таймаут — не факт, а исход со словами.
    `ctx` (AGENTFIX0410) — что знает КОД, а не модель: {"number": номер обращения, "rental": () → результат аренды,
    "results": принятые до сих пор}. Без ctx договор и PDF фактом не бывают (привязать не к чему)."""
    at = clock()
    door = (doors or {}).get(tool)
    if tool not in TOOLS:
        return result(tool, REFUSED, at=at, reason="неизвестный инструмент")
    if tool == "delivery" or door is None:
        return result(tool, UNKNOWN, at=at, reason="двери %s нет — неизвестно" % tool)
    ctx = ctx or {}
    call_args, words, sent = args or {}, "", {}
    if tool == "contract":                       # K3-FIX3 п.1: поиск — в доверенном контексте обращения
        rental = ctx["rental"]() if callable(ctx.get("rental")) else None
        call_args, clash, words = contract_query(args, ctx.get("number"), rental)
        src = "реестр подписей TB e-Sign (contract_find)"
        if clash:
            return dict(result("contract", CONFLICT, src, at=at, reason=clash), query=words)
        if call_args is None:
            return result("contract", UNKNOWN, src, at=at,
                          reason="номер обращения не назван — договор не к чему привязать, реестр не читаю")
        # тождество запроса — то, что код послал в дверь (срок аренды; номер обращения в сверке один — без него)
        sent = {"req": request_key("contract", dict({k: v for k, v in call_args.items() if k != "phone"},
                                                    bound="code")), "query": words}
    try:
        raw = door(**call_args)
    except TimeoutError:
        return dict(result(tool, TIMEOUT, at=at, reason="таймаут двери"), **sent)
    except Exception as e:                                          # noqa: BLE001
        if "timeout" in type(e).__name__.lower():
            return dict(result(tool, TIMEOUT, at=at, reason="таймаут двери"), **sent)
        return dict(result(tool, REFUSED, at=at, reason="дверь упала: %s" % type(e).__name__), **sent)
    if tool == "contract":
        res = contract_result(raw, at, number=ctx.get("number") or "", rental=rental)
        if res["outcome"] == EMPTY and "date_from" in call_args:    # K07: договор другой аренды — назвать, не принять
            more = ctx.get("may_call")
            if callable(more) and not more():   # второй поиск — тоже вызов двери: после предела сверки его нет
                res["reason"] += "; договор другой аренды не искали — предел сверки"
            else:
                res = _other_term(res, door, call_args, at, ctx.get("number") or "", rental)
        res.update(sent)                         # слова поиска — ответу и журналу (только хвост номера)
        if res["outcome"] != FACT:
            res["reason"] = "%s (%s)" % (res["reason"], words)
        return res
    if tool == "contract_pdf":
        allowed = {f.get("pdf_id") for f in accepted(ctx.get("results") or []) if f.get("kind") == "contract"}
        return pdf_result(raw, at, allowed={a for a in allowed if a})
    parse = {"cash": cash_result, "rental": rental_result, "history": history_result, "rules": rules_result}[tool]
    return parse(raw, at)


def bind_ctx(number, doors, results, clock=time.time, may_call=None):
    """Контекст привязки одной сверки: номер обращения и аренда, которую код читает САМ (дверь rental без аргументов
    модели), один раз на сверку. `may_call()` (AGENTDEDUP0410) — есть ли время на новый вызов двери: нет — аренда
    не читается, исход TIMEOUT «предел сверки»."""
    memo = {}

    def rental():
        if "r" not in memo:
            if may_call is not None and not may_call():
                return result("rental", TIMEOUT, at=clock(), reason="предел сверки — аренда не прочитана")
            memo["r"] = call_tool("rental", {}, doors, clock)
        return memo["r"]
    # may_call — и второму поиску договора (K07 вне срока, K3-FIX3): после предела сверки вызовов дверей нет
    return {"number": number, "rental": rental, "results": results, "may_call": may_call}


# ------------------------------- код считает -------------------------------

def fact_key(f):
    """Тождество факта (AGENTDEDUP0410): касса — источник + row + msg_id|link; договор — row + doc_id; аренда —
    booking_id (без него — байк и срок); PDF — id; переписка и правила — одна на сверку."""
    k = f.get("kind")
    if k == "cash":
        return ("cash", str(f.get("src") or "tx_find"), str(f.get("row")), str(f.get("msg_id") or f.get("link") or ""))
    if k == "contract":
        return ("contract", str(f.get("row")), str(f.get("doc_id") or ""))
    if k == "rental":
        if f.get("booking_id"):
            return ("rental", str(f["booking_id"]))
        return ("rental", "", str(f.get("bike") or ""), str(f.get("date_start") or ""), str(f.get("date_end") or ""))
    if k == "pdf":
        return ("pdf", str(f.get("id") or ""))
    return (str(k),)


def stale(r, since):
    """Ответ прочитан раньше последнего входящего клиента — устарел (AGENTDEDUP0410). Время неизвестно — не судим."""
    at = r.get("at")
    return (since is not None and isinstance(at, (int, float)) and not isinstance(at, bool) and at < since)


def read_order(results):
    """Порядок прочтений — по НАЧАЛУ запроса (T4BFACTS0410): `at` ставит `_read` ДО вызова двери, а ответ запроса,
    начатого раньше, может прийти позже ответа запроса, начатого после него. Равное время — порядок списка; время
    неизвестно хоть у одного ответа — порядок списка целиком (сравнить начала нечем; прежнее поведение)."""
    ats = [r.get("at") for r in results]
    if all(isinstance(a, (int, float)) and not isinstance(a, bool) for a in ats):
        return sorted(range(len(results)), key=lambda i: (ats[i], i))
    return list(range(len(results)))


def sift(results, since=None):
    """Результаты → (опора, снятое). Опора — каждый факт ОДИН раз, в версии НОВЕЙШЕГО по началу прочтения
    (T4BFACTS0410; было — по приходу ответа): из каждого запроса берётся только последний начатый ответ (позднее
    «не факт» того же запроса снимает прежний FACT); ключ, чьё новейшее прочтение снято (отказ, неизвестность, неполнота
    того же запроса или его новый ответ без этой строки), не подтверждён — старая версия из другого запроса не
    возвращается; ответ, прочитанный раньше последнего входящего (`since`), устарел. Снятое — слова для журнала."""
    order = read_order(results)
    rank = {i: n for n, i in enumerate(order)}
    last = {}
    for i in order:
        last[results[i].get("req") or "#%d" % i] = i
    facts, dropped, born, gone = {}, [], {}, {}
    for i in order:
        r = results[i]
        if r["outcome"] != FACT:
            continue
        j = last[r.get("req") or "#%d" % i]
        if j != i:
            dropped.append("%s: факт снят — тот же запрос прочитан позже (%s)" % (r["tool"], results[j]["outcome"]))
            kept = {fact_key(g) for g in results[j]["facts"]} if results[j]["outcome"] == FACT else set()
            for key in {fact_key(g) for g in r["facts"]} - kept:       # ключ снят с началом запроса j
                gone[key] = max(gone.get(key, -1), rank[j])
            continue
        if stale(r, since):
            dropped.append("%s: факт устарел — прочитан раньше последнего входящего" % r["tool"])
            continue
        for f in r["facts"]:
            k = fact_key(f)
            if k in facts:
                dropped.append("%s: повтор факта — взята последняя версия" % r["tool"])
            facts[k] = f
            born[k] = rank[i]
    for k in [k for k in facts if gone.get(k, -1) > born.get(k, -1)]:
        dropped.append("%s: факт снят — новейшее прочтение того же ключа не подтверждено" % facts[k].get("kind"))
        del facts[k]
    return list(facts.values()), dropped


def accepted(results, since=None):
    return sift(results, since)[0]


def calc(facts):
    """Суммы по ролям и валютам — только строки кассы АРЕНДЫ ОБРАЩЕНИЯ (T4BFACTS0410, `cash_split`), каждая строка
    ОДИН раз (последняя версия); прочая наличность — «не привязано» (`unbound`), в сумму не входит; разность с ценой
    аренды, если она названа."""
    uniq = {}
    for f in facts:
        uniq[fact_key(f)] = f
    facts = list(uniq.values())
    bound, unbound = cash_split(facts)
    sums = {}
    for f in bound:
        key = "%s %s" % (f["role"], f["currency"])
        sums[key] = sums.get(key, 0) + f["amount"]
    out = {"sums": sums, "diffs": [], "unbound": [dict(_fact_ref(f), why=UNBOUND_WORDS) for f in unbound]}
    for f in facts:
        if f["kind"] == "rental" and f.get("price") is not None:
            paid = sums.get("%s %s" % (R_RENT, f["currency"]))
            if paid is not None:
                out["diffs"].append({"what": "цена аренды минус оплата", "currency": f["currency"],
                                     "value": f["price"] - paid})
    return out


def rental_of(facts):
    """Аренда обращения (AGENTDEDUP0410): booking_id строк листа «клиенты» и договоров, привязанных к аренде кодом.
    Ровно одна — она; ни одной или несколько — None: оплату не к чему привязать."""
    ids = {str(f["booking_id"]) for f in facts if f["kind"] in ("rental", "contract") and f.get("booking_id")}
    return ids.pop() if len(ids) == 1 else None


def cash_of_rental(f, bk, facts):
    """Строка кассы — этой аренды: её booking_id; без booking_id — байк номером и день внутри срока аренды bk."""
    if f.get("booking_id"):
        return str(f["booking_id"]) == bk
    rent = [r for r in facts if r["kind"] == "rental" and str(r.get("booking_id") or "") == bk]
    if len(rent) != 1:
        return False
    r = rent[0]
    pc, pr = plate_of(f.get("bike")), plate_of(r.get("bike"))
    d, ds, de = B.day_of(str(f.get("at") or "")[:10]), B.day_of(r.get("date_start")), B.day_of(r.get("date_end"))
    return bool(pc) and pc == pr and None not in (d, ds, de) and ds <= d <= de


def _rental_id(f):
    """Чью аренду называет факт: booking_id; без него — номер байка ("" — не назван)."""
    if f.get("booking_id"):
        return ("booking", str(f["booking_id"]))
    return ("bike", plate_of(f.get("bike")))


def cash_split(facts):
    """Строки кассы → (аренды обращения, «не привязано») (T4BFACTS0410). Аренда обращения есть (`rental_of`) — её строки
    (`cash_of_rental`), прочие не привязаны. Её нет — привязывать не к чему: наличность считается одной аренды, только если
    все строки кассы и все аренды и договоры опоры называют одну и ту же аренду (`_rental_id`); иначе не привязано всё."""
    cash = [f for f in facts if f["kind"] == "cash"]
    bk = rental_of(facts)
    if bk is not None:
        bound = [f for f in cash if cash_of_rental(f, bk, facts)]
    else:
        named = {_rental_id(f) for f in facts if f["kind"] in ("cash", "rental", "contract")}
        bound = cash if len(named) == 1 else []
    return bound, [f for f in cash if not any(f is g for g in bound)]


def rent_currency(facts, bk):
    """Валюта аренды bk (K3-FIX F3) → строка | None. Источники — только факты этой аренды: её строка листа «клиенты»
    (`rental_result`: лист валюты не пишет — THB по умолчанию, как было) и договор, привязанный к ней кодом
    (`bind_contract` кладёт `rent_currency` — валюту аренды, к которой привязан). Не названа ни одним или названа по-разному
    — None: валюта аренды неизвестна, оплату не подтверждаем."""
    cur = {str(f.get("currency") or "").strip().upper() for f in facts
           if f["kind"] == "rental" and str(f.get("booking_id") or "") == bk}
    cur |= {str(f.get("rent_currency") or "").strip().upper() for f in facts
            if f["kind"] == "contract" and str(f.get("booking_id") or "") == bk}
    cur.discard("")
    return cur.pop() if len(cur) == 1 else None


def pay_verdict(facts):
    """Подтверждена ли оплата аренды → (True, "") | (False, причина словами) (K3-FIX F3; правило — `pay_confirmed`).
    Деньги — только по совпадению суммы И валюты: строка роли «оплата аренды» в валюте, отличной от валюты аренды, оплатой
    этой аренды не засчитывается (пересчёта валют код не делает); валюта аренды неизвестна — не подтверждаем."""
    bk = rental_of(facts)
    if bk is None:
        return False, "аренда обращения не одна или не установлена — оплату не к чему привязать"
    rows = [f for f in facts if f["kind"] == "cash" and f["role"] == R_RENT and cash_of_rental(f, bk, facts)]
    if not rows:
        return False, "в кассе нет строки оплаты аренды %s" % bk
    cur = rent_currency(facts, bk)
    if cur is None:
        return False, "валюта аренды %s неизвестна — оплату не подтверждаю" % bk
    rent = [f for f in rows if str(f.get("currency") or "").upper() == cur]
    if not rent:
        return False, "строка оплаты аренды %s в %s, валюта аренды %s — валюта не совпала, оплатой аренды не засчитана " \
                      "(пересчёта валют код не делает)" % (bk, "/".join(sorted({str(f.get("currency")) for f in rows})), cur)
    if any(f["kind"] == "contract" and str(f.get("booking_id") or "") == bk for f in facts):
        return True, ""
    said = {a for f in facts if f["kind"] == "history" for a in f["amounts"]}
    if (any(f["kind"] == "rental" and str(f.get("booking_id") or "") == bk for f in facts)
            and any(f["amount"] in said for f in rent)):
        return True, ""
    return False, "нет второго источника той же аренды %s (договора или строки листа с той же суммой в переписке)" % bk


def pay_confirmed(facts):
    """Оплата подтверждена, только если аренда обращения одна, в кассе есть строка оплаты ЭТОЙ аренды В ВАЛЮТЕ АРЕНДЫ
    (K3-FIX F3: валюта неизвестна или другая — нет) И второй независимый источник ТОЙ ЖЕ аренды: договор, привязанный к
    ней кодом, либо её строка листа «клиенты» вместе с той же суммой в переписке (правило 03.10.2026-1; привязка —
    AGENTDEDUP0410). Причина отказа словами — `pay_verdict`."""
    return pay_verdict(facts)[0]


def known_amounts(price, facts, figures):
    out = set(K.thb_amounts(price.get("line") if isinstance(price, dict) else None))
    loose = {id(f) for f in cash_split(facts)[1]}       # «не привязано» — не опора чисел ответа (T4BFACTS0410)
    for f in facts:
        if id(f) in loose:
            continue
        for k in ("amount", "price"):
            if isinstance(f.get(k), (int, float)) and not isinstance(f.get(k), bool):
                out.add(abs(int(round(f[k]))))
    for v in list(figures["sums"].values()) + [d["value"] for d in figures["diffs"]]:
        out.add(abs(int(round(v))))
    ch = figures.get("change") if isinstance(figures.get("change"), dict) else {}
    if ch.get("state") == CHANGE_OK:              # K3-FIX3 п.2: числа расчёта сдачи кодом — опора ответа
        out.update(abs(int(round(ch[k]))) for k in ("value", "total", "tendered"))
    return out


# ------------------------------- сдача (K3-FIX шаг 3 п.2) -------------------------------

CHANGE_OK, CHANGE_NO = "ok", "refused"
CHANGE_HEAD = "РАСЧЁТ КОДА — сдача (считает код, не ты; другой суммы сдачи не называй):"
CHANGE_WORDS = "сдача посчитана со слов клиента о переданных наличных — сумму подтверждает человек"
_HANDED = re.compile(r"наличн|сдач|отдал|передал|(?<!\w)дал[аи]?(?!\w)|\bcash\b|\bchange\b|\bgave\b|\bhanded\b", re.I)


def cash_said(text):
    """Суммы, которые клиент назвал ПЕРЕДАННЫМИ наличными: числа в батах из его предложений о передаче денег или сдаче
    (`K.thb_amounts`; голое число без валюты суммой не считается). Это СЛОВА клиента: фактом оплаты они не становятся
    (в факты, `pay_verdict` и `pay_backing` не идут) — по ним код лишь считает сдачу при оплате, подтверждённой кассой."""
    out = []
    for sent in K._SENTENCE.split(str(text or "")):
        if _HANDED.search(sent):
            for v in K.thb_amounts(sent):
                if v > 0 and v not in out:
                    out.append(v)
    return out


# K3-FIX шаг 3e (п.1 решения круга 3e): входящее клиента — ОБ ОПЛАТЕ. Клиент говорит о СОСТОЯВШЕЙСЯ оплате («оплатил»,
# «перевёл», «отправил деньги / чек / 7790», «I paid», «payment sent») либо спрашивает, получена ли она («деньги
# пришли?», «видите перевод?», «проверьте оплату», «did you receive my payment?»). Вопрос о СПОСОБЕ, цене или будущей
# оплате («как оплатить?», «можно картой?», «оплачу завтра») и рассказ о несостоявшейся («оплата не прошла, попробую ещё
# раз») — нет. Это СЛОВА клиента: оплатой они не становятся — по признаку код лишь судит краткий ответ («Да, получили.»)
# как ответ на этот вопрос (`_PAY_CTX`).
_ASK_AMT = (r"(?:\d[\d   ]*(?:[.,]\d+)?\s?(?:бат(?:а|ов)?|baht|thb|руб\w*|rub|usd|доллар\w*|dollars?|евро|eur|"
            r"[฿$€])|(?<![\w.,:/+-])\d{3,6}(?![\w.,:/-]))")
_ASK_NOUN = (r"(?:(?:пред|до)?оплат\w*|плат[её]ж\w*|перевод(?!\w*\s+(?:договор|документ|текст|сообщени|паспорт|прав))\w*|"
             r"деньги|денег|средств\w*|сумм\w+|взнос\w*|чек(?:а|и|ом|у)?(?!\w)|квитанци\w*)")
_ASK_DID = re.compile(
    r"(?<!\w)(?:(?:пред|до|про)?оплатил[аи]?|(?:пред|до)?оплачен[аоы]?|заплатил[аи]?|перев[её]л|перевел[аи]|"
    r"перечислил[аи]?|вн[её]с|внесл[аи]|расплатил(?:ся|ась|ись))(?!\w)|"
    r"(?<!\w)(?:отправил[аи]?|скинул[аи]?|закинул[аи]?|кинул[аи]?|выслал[аи]?|послал[аи]?|переслал[аи]?|сделал[аи]?|"
    r"произв[её]л|произвел[аи]|пров[её]л|провел[аи]|отдал[аи]?|передал[аи]?|вручил[аи]?)\s+(?:\S+\s+){0,3}?"
    r"(?:" + _ASK_NOUN + r"|наличн\w+|на\s+карту|на\s+сч[её]т|по\s+реквизитам|по\s+qr|" + _ASK_AMT + r")|"
    r"(?:^|(?<=[.!?\n]))\s*paid(?!\w)(?!\s+(?:at|on|by|upon|when|in\s+advance))|"
    r"(?<!\w)" + _ASK_NOUN + r"\s+(?:\S+\s+){0,3}?(?:отправил[аи]?|отправлен[аоы]?|скинул[аи]?|сделал[аи]?|сделан[аоы]?|"
    r"произв[её]л|произведен[аоы]?|выполнен[аоы]?)(?!\w)|"
    r"(?<!\w)(?:i|we|i['’]ve|we['’]ve|i\s+have|we\s+have|just|already|have|has)\s+(?:just\s+|already\s+|now\s+)?"
    r"(?:paid|payed|transferred|wired|remitted)(?!\w)|"
    r"(?<!\w)(?:sent|made|did|completed|done|gave|handed)\s+(?:\S+\s+){0,3}?(?:payments?|transfers?|money|funds|"
    r"deposit|cash|" + _ASK_AMT + r")|"
    r"(?<!\w)(?:payments?|transfers?|money)\s+(?:is\s+|was\s+|has\s+been\s+|have\s+been\s+)?(?:sent|made|done|completed|"
    r"paid)(?!\w)", re.I)
_ASK_SUBJ = re.compile(
    r"(?<!\w)(?:(?:пред|до)?оплат\w*|плат[её]ж\w*|перевод(?!\w*\s+(?:договор|документ|текст|сообщени|паспорт|прав))\w*|"
    r"деньги|денег|"
    r"средств\w*|поступлени\w*|payments?|transfers?|money|funds)(?!\w)"
    r"(?!\s+(?:links?|details|methods?|options?|terms|page|button|instructions?))", re.I)
_ASK_GOT = re.compile(
    r"(?<!\w)(?:пришл[аои]|приш[её]л|дошл[аои]|дош[её]л|поступил[аои]?|прошл[аои]|прош[её]л|получили|получил[аи]?|"
    r"получен[аоы]?|видите|видели|видно|видна|виден|зачислил\w*|зачислен[аоы]?|отразил\w*|отражен[аоы]?|ушл[аои]|"
    r"уш[её]л|списал\w*|списан[аоы]?|подтвердите|"
    r"подтверждаете|проверьте|проверь|посмотрите|посмотри|гляньте|глянь|уточните|"
    r"received|arrived|landed|cleared|(?:come|came|gone|went|go)\s+through|reached\s+you|"
    r"(?:did|do|have|can|could|will)\s+you\s+(?:please\s+|kindly\s+)?(?:get|got|gotten|receive|received|see|seen|confirm|"
    r"check|verify)|please\s+(?:confirm|check|verify))(?!\w)", re.I)


def pay_asked(text):
    """Входящее клиента — об оплате? (K3-FIX шаг 3e, п.1) → bool. Да — хотя бы в одной его фразе: глагол СОСТОЯВШЕЙСЯ
    оплаты без отрицания в той же клаузе («оплатил», «перевёл 7790», «отправил чек», «I paid», «payment sent») либо слово
    оплаты вместе со сказуемым получения или просьбой проверить («деньги пришли?», «проверьте оплату», «did you get my
    transfer?») — в вопросе всегда, в утверждении без отрицания («оплата не прошла» — не об оплаченном). Смешанное
    входящее (оплата и документ) — да: сомнение — в сторону отказа. Текста нет или он не об оплате — нет."""
    s = str(text or "")
    pos = 0
    for brk in list(K._SENTENCE.finditer(s)) + [None]:
        sent, mark = (s[pos:], "") if brk is None else (s[pos:brk.start()], brk.group(0))
        pos = len(s) if brk is None else brk.end()
        did = [1 for part in _PAY_CUT.split(sent) if _ASK_DID.search(part) and _PAY_NOT.search(part) is None]
        got = _ASK_SUBJ.search(sent) is not None and _ASK_GOT.search(sent) is not None
        if did or (got and ("?" in mark or _PAY_NOT.search(sent) is None)):
            return True
    return False


def change_of(facts, handed=()):
    """Сдача кодом (K3-FIX шаг 3 п.2) → None (клиент не называл переданных наличных — сдачи в разговоре нет) |
    {state: ok, value, currency, total, tendered, paid, booking_id, basis} | {state: refused, why}.

    Только ПРОВЕРЕННЫЕ деньги одной аренды и одной валюты: аренда обращения одна (`rental_of`), её валюта известна
    (`rent_currency`), её итог назван листом «клиенты» (`to_pay` строки аренды), в кассе есть строки оплаты аренды ЭТОЙ
    аренды (`cash_split` → `cash_of_rental`, роль «оплата аренды»: залог и чужие деньги не складываются) только в её валюте
    (строка другой валюты этой аренды — отказ: пересчёта нет). Сдача = переданное − итог, когда касса оплатила итог
    ровно (переданное — слова клиента, кассой НЕ подтверждено: `basis` и `CHANGE_WORDS` это называют), либо оплачено по
    кассе − итог, когда касса записала больше итога (и клиент назвал ту же сумму). Иначе — отказ с причиной: сдачу код
    не выдумывает, называет её человек."""
    said = sorted({int(round(v)) for v in handed or () if _num(v) and v > 0})
    if not said:
        return None

    def no(why):
        return {"state": CHANGE_NO, "why": why, "handed": said}
    bk = rental_of(facts)
    if bk is None:
        return no("аренда обращения не одна или не установлена — сдачу не к чему привязать")
    cur = rent_currency(facts, bk)
    if cur is None:
        return no("валюта аренды %s неизвестна" % bk)
    totals = {f.get("to_pay") for f in facts if f["kind"] == "rental" and str(f.get("booking_id") or "") == bk
              and _num(f.get("to_pay")) and f.get("to_pay") > 0}
    if len(totals) != 1:
        return no("итог аренды %s листом «клиенты» не назван (или назван по-разному)" % bk)
    total = totals.pop()
    mine = [f for f in cash_split(facts)[0] if f["kind"] == "cash" and cash_of_rental(f, bk, facts)
            and f["role"] == R_RENT]
    alien = sorted({str(f.get("currency")) for f in mine if str(f.get("currency") or "").upper() != cur})
    if alien:
        return no("в кассе оплата аренды %s и в другой валюте (%s) — пересчёта валют код не делает" % (bk, "/".join(alien)))
    if not mine:
        return no("строки оплаты аренды %s в кассе нет — наличные со слов клиента оплатой не являются" % bk)
    paid = sum(f["amount"] for f in mine)
    if len(said) != 1:
        return no("клиент назвал разные суммы переданных наличных (%s) — какая передана, неизвестно"
                  % ", ".join(str(v) for v in said))
    t = said[0]
    if paid < total:
        return no("по кассе аренда %s оплачена на %s из %s %s — сдачи кодом нет" % (bk, _n(paid), _n(total), cur))
    if paid > total:
        if t != int(round(paid)):
            return no("по кассе оплачено %s %s, клиент называет %s — суммы не совпали" % (_n(paid), cur, t))
        value, basis = paid - total, "касса: оплачено %s при итоге %s" % (_n(paid), _n(total))
    elif t < total:
        return no("клиент назвал %s %s — меньше итога %s; сдачи нет, сумму сверяет человек" % (t, cur, _n(total)))
    else:
        value, basis = t - total, ("итог %s оплачен по кассе; переданные %s — со слов клиента, кассой не подтверждены"
                                   % (_n(total), t))
    return {"state": CHANGE_OK, "value": value, "currency": cur, "total": total, "tendered": t, "paid": paid,
            "booking_id": bk, "basis": basis, "handed": said}


def _n(v):
    return str(int(round(v))) if _num(v) and abs(v - round(v)) < 1e-9 else str(v)


def change_block(results, handed=()):
    """Блок «РАСЧЁТ КОДА» для модели (K3-FIX3 п.2): сдачу модель не считает — код подаёт результат или причину, почему
    его нет. Клиент не называл переданных наличных — блока нет (запрос прежний)."""
    if not handed:
        return ""
    try:
        ch = change_of(accepted(results), handed)
    except Exception as e:                                           # noqa: BLE001
        return CHANGE_HEAD + "\nсдача НЕ посчитана (расчёт упал: %s) — сумму сдачи не называй, передай человеку" % (
            type(e).__name__)
    if ch is None:
        return ""
    if ch["state"] != CHANGE_OK:
        return CHANGE_HEAD + "\nсдача НЕ посчитана: %s. Сумму сдачи не называй — передай человеку." % ch["why"]
    if ch["value"] == 0:
        return CHANGE_HEAD + "\nаренда %s: итог %s %s оплачен; передано ровно итог — сдачи нет (%s)." % (
            ch["booking_id"], _n(ch["total"]), ch["currency"], ch["basis"])
    return CHANGE_HEAD + ("\nаренда %s: итог %s %s, передано %s %s → сдача %s %s (%s). Сдача отдаётся в конце аренды, "
                          "вместе с возвратом залога; что передано именно %s, подтверждает человек." % (
                              ch["booking_id"], _n(ch["total"]), ch["currency"], ch["tendered"], ch["currency"],
                              _n(ch["value"]), ch["currency"], ch["basis"], ch["tendered"]))


_MONEY_WORD = re.compile(r"оплат|плат[её]ж|залог|депозит|сдач|возврат|вернём|вернем|сумм|стоимост|цен[аыу]|бат|"
                         r"\bpaid\b|payment|deposit|refund|\bchange\b|\btotal\b|price|cost|baht", re.I)
_BARE = re.compile(r"(?<![\w.,:/+-])(\d{1,3}(?:[ ,  ]\d{3})+|\d{2,6})(?!\w|%|[.,:/-]\d)"
                   r"(?!\s*(?:дн|сут|день|дня|дней|ноч|час|мин|шт|км|km|day|night|hour|cc|%))")
_MODEL_BEFORE = re.compile(r"[A-Za-z]{2,}\s*$")


def money_claims(text, price, known):
    """Опора = «ЦЕНА» ∪ факты ∪ расчёты. Сумма в батах и ЧИСЛО БЕЗ ВАЛЮТЫ в предложении с денежным словом
    судятся (имя модели «PCX 160», дни, км, проценты — нет). → [(вид, что)] без опоры."""
    s = str(text or "")
    out = [c for c in K.money_claims(s, None) if c[0] == "процент"]
    out += [("сумма", v) for v in K.thb_amounts(s) if v not in known]
    for sent in K._SENTENCE.split(s):
        if not _MONEY_WORD.search(sent):
            continue
        for m in _BARE.finditer(sent):
            if _MODEL_BEFORE.search(sent[:m.start()]):
                continue
            v = int(re.sub(r"\D", "", m.group(1)))
            if v not in known and ("сумма", v) not in out:
                out.append(("число", v))
    return out


# слово окна внутри клаузы: запятая, двоеточие, тире, скобка и конец предложения окно рвут; точка внутри слова
# (дата «05.10», сумма «2.5») — нет
_W = r"(?:(?:[^\s,;:.!?—–()]|\.(?=\S))+\s+)"
_PAY_AFFIRM = re.compile(r"оплат\w*\s+(?:\S+\s+){0,3}(?:получен|подтвержд|поступил|прошл|пришл)|"
                         r"получил[аи]?\s+(?:вашу\s+)?(?:оплату|деньги|перевод)|"
                         r"payment\s+(?:is\s+|has\s+been\s+)?(?:received|confirmed)|"
                         r"(?:we\s+)?received\s+(?:your\s+)?(?:payment|money|transfer)|paid\s+in\s+full|"
                         # K3-FIX3 N4 (real K15, K02): утвердительные формы — «в кассе вижу оплату…», «оплата … у нас
                         # отражена», «с оплатой всё в порядке»; окно — внутри клаузы, а не через запятую
                         r"оплат\w*\s+" + _W + r"{0,10}(?:получен|получил|подтвержд|поступил|прошл|пришл|отражен|"
                         r"отразил|вижу|видим|видна|видно|в\s+порядке)|"
                         r"(?:вижу|видим|видна|видно|отражен\w*|отразил\w*|в\s+порядке)\s+" + _W + r"{0,3}оплат|"
                         r"оплат\w*[^.!?…\n]{0,80}?вс[её]\s+в\s+порядке|"
                         r"(?:i|we)\s+(?:can\s+)?see\s+" + _W + r"{0,2}payment|"
                         r"payment\s+" + _W + r"{0,6}(?:reflected|recorded|registered|showing|in\s+order|all\s+good)",
                         re.I)
# не утверждение: отрицание и обещание будущей проверки / условие / вопрос В ТОЙ ЖЕ клаузе до конца совпадения
_PAY_NOT = re.compile(r"(?<!\w)(?:не|нет|ни|no|not|never|cannot)(?!\w)|n't(?!\w)", re.I)
_PAY_LATER = re.compile(r"(?<!\w)(?:будет|будут|станет|станут|как\s+только|когда|если|ли|проверю|проверим|"
                        r"проверит|проверят|сверю|сверим|сверит|сверят|уточню|уточним|уточнит|уточнят|подтвердим|"
                        r"подтвердит|подтвердят|посмотрю|посмотрим|посмотрит|увижу|увидим|will|once|after|when|if|"
                        r"whether|as\s+soon\s+as|going\s+to|shall|pending)(?!\w)", re.I)
_PAY_CUT = re.compile(r"[,;:—–(]|\s-\s")
_PAY_END = re.compile(r"[.!?…\n]")
# знак в конце краткой клаузы вместо точки: «Да, получили 👍» (смайлы и значки — диапазоны Юникода, заданы кодами;
# шаг 3e, поднято сюда шагом 3f — им пользуются и формы со знаком препинания перед сказуемым)
_PQ_EMO = ("[" + chr(0x1F000) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + chr(0x2B00) + "-" + chr(0x2BFF)
           + chr(0xFE0F) + chr(0x200D) + "]")
# K3-FIX шаг 3f (остаток О3 шага 3e и его соседи): ЗНАК ПРЕПИНАНИЯ между предметом и сказуемым получения клаузу не рвёт,
# когда сказуемое её и заканчивает: «7790 — получили.», «7790 бат — получены, спасибо!» (тире; слова между тире и
# сказуемым — `_PQ_DASH`), «Оплата: получена ✅», «Статус оплаты: подтверждена.», «Получено: 7790 бат.» (двоеточие).
# За сказуемым — конец клаузы (`_PQ_STOP`): «7790 бат — получена скидка 10 %», «Оплата: получена ссылка» — не об оплате.
_PQ_DASH = r"(?:(?:уже|вс[её]|вся|полностью|успешно|мы|we|already|fully|all)\s+){0,2}"
_PQ_STOP = r"(?=\s*(?:$|[.!,;…\n)]|" + _PQ_EMO + r"))"

# K3-FIX шаг 3b (D1 приёмки шага 3, 10.10.2026): утвердительные ФОРМЫ оплаты, а не список фраз приёмки — глагол или
# причастие оплаты в утвердительной клаузе. Три вида:
#   (1) причастие самой оплаты: «оплачен(а/о/ы)», «предоплачено»; англ. «was/were/been paid», «already/fully/all paid»,
#       «is/are paid» в конце клаузы (а не «is paid at pickup» — правило оплаты), «rent(al) paid»;
#   (2) предмет оплаты + сказуемое получения или учёта: «оплата/оплату/платёж/деньги/перевод/средства … есть/имеется/
#       получен(а)/получили/поступила/пришёл/прошёл/дошли/зафиксирована/отражена/учтена/зачислены/принята/внесена/
#       проведён/записана/подтверждена/видна/в порядке»; англ. «payment/money/transfer/funds … went through/came
#       through/cleared/arrived/credited/processed/received/confirmed/recorded/settled»;
#   (3) сказуемое + предмет: «получена ваша оплата», «зафиксировали платёж», «в кассе есть ваша оплата»; англ.
#       «got/received/credited … your transfer».
# Прежние формы `_PAY_AFFIRM` НЕ тронуты: расширение только добавляет второй проход ТЕМ ЖЕ определением (`_PayClaim`) —
# с теми же исключениями (отрицание, будущее/проверка, условие, вопрос в клаузе до конца совпадения) и с четырьмя своими
# (`_PayClaim.verdict`; до шага 3c — `_form_ok`): предмет после предлога («ссылку на оплату», «вопрос про платёж»)
# оплатой не является; «есть/имеется» — только при кассе/учёте/счёте или «ваша оплата» (а не «оплата картой тоже
# есть»); подлежащее — залог/депозит (без аренды раньше него) — роль залога `_DEP_CLAIM`, а не оплата аренды (новых
# ролей нет); долженствование и будущее в клаузе («должен быть проведён», «оплачено будет») — не утверждение.
_PF_NOUN_NOM = r"(?:(?:пред|до)?оплата|плат[её]ж|плат[её]жи|деньги|перевод|переводы|средства)"
_PF_NOUN_ACC = r"(?:(?:пред|до)?оплат[ау]|плат[её]ж|плат[её]жи|деньги|перевод|переводы|средства)"
_PF_PRED = (r"(?:получен[аоы]?|получил[аои]?|поступил[аои]?|пришл[ао]|пришёл|пришел|прошл[аои]|прошёл|прошел|"
            r"дошл[ао]|дошёл|дошел|зафиксирован[аоы]?|зафиксировал[аои]?|отражен[аоы]?|отражён|"
            r"отразил(?:ась|ось|ся|ись|[аои])?|учтен[аоы]?|учтён|учли|зачислен[аоы]?|зачислил[аои]?|принят[аоы]?|"
            r"принял[аои]?|внесен[аоы]?|внесён|проведен[аоы]?|проведён|записан[аоы]?|записали|подтвержден[аоы]?|"
            r"подтверждён|подтверждаю|подтверждаем|подтвердил[аои]?|видн[аоы]|виден|вижу|видим|в\s+порядке|"
            # шаг 3d (свой состязательный поиск): сказуемые-синонимы завершения и учёта оплаты
            r"завершен[аоы]?|завершён|произведен[аоы]?|произведён|выполнен[аоы]?|обработан[аоы]?|засчитан[аоы]?|"
            r"зачтен[аоы]?|зачтён|увидел[аи]?|отобража(?:ется|ются)|"
            r"есть|имеется|имеются)")
_PF_EN_NOUN = r"(?:payments?|money|transfers?|funds)"
_PF_EN_PRED = (r"(?:went\s+through|gone\s+through|came\s+through|come\s+through|cleared|arrived|credited|processed|"
               r"received|confirmed|recorded|registered|reflected|showing|settled|in\s+order|all\s+good|"
               r"successful|came\s+in|landed|(?:has|have)\s+been\s+made|was\s+made)")     # последняя строка — шаг 3d
_PAY_FORMS = re.compile(
    r"(?<!\w)(?P<pp>(?:пред|до)?оплачен[аоы]?)(?!\w)|"
    r"(?<!\w)(?P<pe>(?:was|were|been)\s+(?:already\s+|fully\s+)?paid|(?:already|fully|all)\s+paid|"
    r"(?:is|are)\s+(?:already\s+|fully\s+|now\s+)?paid(?=\s*(?:$|[.!?,;:…\n—–()])|\s+(?:in\s+full|for|up\s+to|until|"
    r"thank))|(?P<n5>rent|rental)\s+(?:already\s+|fully\s+)?paid|"
    # шаг 3d: краткое «Paid, thank you!» в начале предложения (близнец «Оплачено, спасибо!»)
    r"(?:^|(?<=[.!?…]\s)|(?<=yes,\s)|(?<=yes\s))paid(?=\s*(?:[,.!…]|$)))(?!\w)|"
    r"(?<!\w)(?P<n1>" + _PF_NOUN_NOM + r"|(?:пред|до)?оплату)\s+" + _W + r"{0,8}(?P<v1>" + _PF_PRED + r")(?!\w)|"
    # шаг 3f (сосед О3): слово оплаты, ДВОЕТОЧИЕ, сказуемое в конце клаузы — «Оплата: получена ✅», «Статус оплаты:
    # подтверждена.», «Payment: received.» («есть / вижу» здесь не сказуемое: «Оплата: есть картой и наличными»)
    r"(?<!\w)(?P<n12>(?:пред|до)?оплат[аы]|плат[её]ж|платежа|payments?(?:\s+status)?)\s*:\s+" + _PQ_DASH
    + r"(?P<v12>(?!есть|име[ею]тся|вижу|видим)(?:" + _PF_PRED + r"|" + _PF_EN_PRED + r"))(?!\w)" + _PQ_STOP + r"|"
    r"(?<!\w)(?P<n2>деньги|средства|плат[её]жи|переводы)\s+" + _W + r"{0,4}(?:пришли|дошли)(?!\w)|"
    r"(?<!\w)(?P<v3>" + _PF_PRED + r")\s+" + _W + r"{0,3}(?P<n3>" + _PF_NOUN_ACC + r")(?!\w)|"
    r"(?<!\w)(?P<n4>" + _PF_EN_NOUN + r")\s+" + _W + r"{0,5}" + _PF_EN_PRED + r"(?!\w)|"
    r"(?<!\w)(?:received|got|recorded|registered|credited|confirmed|processed|cleared)\s+" + _W + r"{0,3}"
    r"(?P<n6>" + _PF_EN_NOUN + r")(?!\w)",
    re.I)
# `_PAY_PASSES` — ниже, после `_PAY_SUMS` (шаг 3d: ОДНО определение, три прохода)
_PF_DET = re.compile(r"ваш\w*|наш\w*|эт\w+|тот|та|ту|те|the|a|an|your|our|my|this|that|these|those", re.I)
_PF_PREP = re.compile(r"на|за|по|про|о|об|обо|для|к|ко|от|до|из|с|со|в|во|у|при|без|через|после|перед|под|над|"
                      r"насч[её]т|for|about|of|on|to|with|without|after|before|regarding|via|by", re.I)
_PF_EXIST = re.compile(r"есть|имеется|имеются", re.I)
_PF_HELD = re.compile(r"касс|уч[её]т|сч[её]т|счету|выписк|систем|журнал|таблиц|(?<!\w)баз[еу](?!\w)|"   # систем… — 3d
                      r"(?<!\w)ваш[аеиу]?\s+(?:(?:пред|до)?оплат|плат[её]ж|деньг|перевод|средств)", re.I)
_PF_DEP = re.compile(r"залог|депозит|deposit", re.I)
_PF_RENT = re.compile(r"аренд|прокат|брон|rent|booking", re.I)
# шаг 3c: краткие формы «должен/должна/должно/должны» (а не «должным образом отражена» — это утверждение) и слова
# ожидания «требует/ожидает/ждёт (подтверждения)»
# шаг 3d: возможность («оплата может быть произведена наличными», «payment can be made in cash») — правило, а не факт
_PF_MUST = re.compile(r"(?<!\w)(?:должен|должн[аоы]|нужно|надо|необходимо|обязан\w*|будет|будут|станет|станут|"
                      r"требует(?:ся)?|требуют(?:ся)?|ожидает(?:ся)?|ожидают(?:ся)?|жд[её]т|ждут|"
                      r"может|могут|можно|"
                      r"must|should|need\s+to|has\s+to|have\s+to|will|shall|can|could|may|might)(?!\w)", re.I)
_PF_EN_NEXT = re.compile(r"\s+(?:links?|details|methods?|options?|receipts?|screenshots?|info|information|terms|"
                         r"deadline|date|requests?|reminders?|instructions?|page|button|plan|schedule|form|reference)"
                         r"(?!\w)", re.I)
_PF_TRANSL_NEXT = re.compile(r"\s+(?:договор|документ|текст|сообщени|правил|инструкци)", re.I)  # «перевод договора»

# K3-FIX шаг 3c (10.10.2026). ИСХОД совпадения НАЗВАН: определение отдаёт наверх не «да/нет», а имя — «утверждение» либо
# ПОЧЕМУ это не утверждение. До 3c исключения форм отдавали голое False, в двух ветках — оттого, что шаблон НЕ нашёл
# слова кассы или аренды: «не утверждение по правилу» и «шаблон промолчал» наверху не различались (храповик слепых
# читателей 72 → 74). Теперь каждая ветка называет себя, `explain` отдаёт имена наружу, тесты сверяют имя с фразой.
PC_CLAIM = "утверждение"
PC_WORD = "основа сказуемого — начало другого слова"
PC_NOT, PC_LATER, PC_ASKED = "отрицание", "будущее, проверка или условие", "вопрос"
PC_MUST = "долженствование или ожидание"
PC_PREP = "предмет после предлога"
PC_NEXT = "предмет — документ, а не оплата"
PC_EXIST = "«есть» без кассы, учёта, счёта или «ваша оплата»"
PC_DEP = "подлежащее — залог"
PC_THEIR = "получатель — клиент, а не мы"            # шаг 3d: «вы получили 210 бат» — не наше подтверждение
# Те же исключения — и у ПРЕЖНИХ форм `_PAY_AFFIRM` (сами формы не тронуты ни символом), одним определением (`verdict`):
#   * предмет прежней формы — её слово оплаты (`_PC_NOUN`); сразу после предлога ЦЕЛИ или ВРЕМЕНИ (`_PC_PREP_GOAL`,
#     `_PC_PREP_TIME`: «ссылку на оплату получили», «реквизиты для оплаты», «после оплаты бронь подтверждается», «без
#     оплаты …») он не подлежащее получения — в границах шага 3d (R1б, ниже).
#     Прочие предлоги (`_PF_PREP`) — только у форм 3b, где предмет стоит в им./вин. падеже: у прежних форм
#     «с оплатой всё в порядке», «по оплате вижу …», «подтверждение об оплате получено» — утверждения, их терять нельзя;
#   * основа сказуемого прежних форм («пришл», «прошл», «получен», «видим») бывает началом ДРУГОГО слова — «пришлём»,
#     «пришлите», «пришлось», «прошлую», «при получении», «видимо» (`_PC_WORD`). Тогда сказуемое ищется дальше в той же
#     клаузе целым словом (`_PC_AGAIN`: «оплаты за прошлую и эту недели получены» — утверждение); нет его — не утверждение.
_PC_NOUN = re.compile(r"оплат\w*|деньги|перевод|payment|money|transfer", re.I)
_PC_WORD = re.compile(r"(?:пришл|прошл)(?![аои](?!\w))\w*|получени\w+|видим\w+", re.I)
_PC_AGAIN = re.compile(r"\s+" + _W + r"{0,10}?(?:получен[аоы]?|получил[аи]?|подтвержд\w*|поступил[аои]?|прошл[аои]|"
                       r"пришл[аои]|отражен\w*|отразил\w*|вижу|видим|видн[ао]|в\s+порядке)(?!\w)", re.I)

# K3-FIX шаг 3d (10.10.2026; независимая проверка кругов 3b+3c — fix_review3c/VERDICT.md, R1 и R3).
# R1. Два исключения шага 3c у прежних форм судили шире своего места и теряли утверждения, которые ловили cbe186f и
# 6f6e754 (25 из 38 состязательных фраз проверяющего):
#   (а) долженствование искалось во ВСЕЙ клаузе до сказуемого, а клаузу режет только пунктуация — модальное слово
#       главной части («You should know that your payment has been received», «Надо сказать что оплата получена») и
#       слово при ПЕРВОМ из двух сказуемых («должна была поступить вчера и поступила») снимали утверждение. Теперь слово
#       долженствования судится при своём сказуемом (`_PayClaim._governs`): оно управляет сказуемым оплаты, когда между
#       ними только связка и обстоятельства («должна быть получена», «must be received», «требует подтверждения») либо
#       глагол проверки или ожидания («нужно проверить что оплата прошла» — обещание проверки, как в `_PAY_LATER`), и НЕ
#       управляет, когда у него свой глагол или дальше идёт придаточное («…сказать что …», «should know …», «need to
#       mention the payment is …»). Цель («чтобы оплата была подтверждена», «so that the payment is confirmed») —
#       ожидание, а не факт. Слово сразу ЗА сказуемым — только будущее или со связкой («оплачено будет», «оплачена
#       должна быть»), а не новое сказуемое («оплата получена нужно только подписать договор»).
#   (б) предлог перед ПЕРВЫМ словом оплаты снимал утверждение при любом слове перед ним. Теперь (`_after_prep`): предлог
#       цели («на», «для», for) — только когда перед ним слово ДОКУМЕНТА или ЗАПРОСА («ссылку на оплату получили», «link
#       for payment received»), а не сумма и не благодарность («7790 бат на оплату аренды получены», «Thank you for the
#       payment received»); предлог времени и условия («после», «до», «перед», «без», without) — как было, кроме «после
#       оплаты» с прошедшим сказуемым получения («После оплаты всё прошло успешно»); судится каждое слово оплаты
#       совпадения: свободное подлежащее дальше («Без оплаты залога оплата аренды получена») — утверждение.
_PC_PREP_GOAL = re.compile(r"на|для|for", re.I)
_PC_PREP_TIME = re.compile(r"после|до|перед|без|without", re.I)
_PC_DOC = re.compile(r"ссылк\w*|сч[её]т\w*|фактур\w*|реквизит\w*|запрос\w*|чек\w*|квитанци\w*|заявк\w*|инвойс\w*|"
                     r"напоминани\w*|уведомлени\w*|сообщени\w*|вопрос\w*|инструкци\w*|информаци\w*|документ\w*|"
                     r"qr|код\w*|links?|invoices?|requests?|receipts?|details|reminders?|instructions?|forms?|info|"
                     r"information|screenshots?|bills?|codes?", re.I)
_PC_PAST = re.compile(r"получил[аи]?|поступил[аои]?|прошл[аои]|пришл[аои]|прош[её]л|приш[её]л|дошл[аои]|дош[её]л", re.I)
_PC_AUX = re.compile(r"быть|be|been|have|get", re.I)               # связка: цепочка сказуемого продолжается
_PC_FUT = re.compile(r"будет|будут|станет|станут|will|shall", re.I)
_PC_SKIP = re.compile(r"был[аои]?|бы|же|уже|ещ[её]|только|лишь|обязательно|сначала|сперва|полностью|not|just|only|also|"
                      r"first|still|now|already|always|really|fully|definitely", re.I)
_PC_INF = re.compile(r"(?<!\w)[а-яё]{2,}(?:ть|ти|чь)(?:ся|сь)?(?!\w)", re.I)      # неопределённая форма глагола
_PC_INF_NOT = re.compile(r"быть|есть|\w*ость|\w*дцать|часть|части|опять|пять|шесть|девять|десять|память|мать|почти|"
                         r"пути|сети|чуть|ночь|пусть|треть|честь|кстати", re.I)   # связка и не-глаголы на -ть/-ти/-чь
_PC_VERIFY = re.compile(r"(?<!\w)(?:провер\w+|свер(?:ить|ять)\w*|уточн\w+|убедит\w+|удостовер\w+|дожд\w+|подожд\w+|"
                        r"ждать|выясн\w+|check|verify|ensure|make\s+sure|wait|double-check|find\s+out)(?!\w)", re.I)
_PC_THAT = re.compile(r"(?<!\w)(?:что|that)(?!\w)", re.I)
_PC_PURPOSE = re.compile(r"(?<!\w)(?:чтобы|чтоб|so\s+that|in\s+order\s+(?:that|for))(?!\w)", re.I)

# R3. Третий проход ТОГО ЖЕ определения — два семейства, которых не ловил ни один коммит (cbe186f, 6f6e754, f6ed7bd):
#   (i)  подтверждение получения, поступления или зачисления оплаты, платежа, денег, суммы, средств ОТГЛАГОЛЬНЫМ
#        существительным: «подтвердили поступление оплаты», «подтверждаю получение платежа», «зачисление средств
#        подтверждаем»; англ. «we confirm / confirmed receipt of your payment»;
#   (ii) сказуемое получения или поступления с ДЕНЕЖНОЙ СУММОЙ (число с валютой) либо словом суммы без слова «оплата»:
#        «получили 7790 бат», «7790 бат получили / получены / поступили», «сумма получена», «получили всю сумму», «деньги
#        у нас»; англ. «we received 7790 baht», «got your 7790 THB», «the full amount has been received», «we have your
#        payment».
# Исключения — те же, одним `verdict`: отрицание, будущее, проверка, условие, вопрос, долженствование; сумма или слово
# суммы после предлога («получили ваш запрос на 7790 бат», «счёт на сумму 7790 бат получили», «за 7790 бат …»); залог
# или депозит без аренды раньше него — роль залога, а не оплата аренды; получатель — клиент («вы получили 210 бат»).
# Сумма как цена, итог или сдача без сказуемого получения («итог 7790 бат», «с 8000 сдача 210 бат»), «получили ваш
# запрос / сообщение / фото / паспорт / договор» и слова клиента в пересказе («вы написали, что перевели 7790 бат») в
# проход не попадают вовсе. Число БЕЗ валюты проход не судит: в этом парке оно неотличимо от номера байка («90101»).
_PM_AMT = (r"(?:\d[\d   ]*(?:[.,]\d+)?\s?(?:бат(?:а|ов)?|baht|thb|руб(?:л\w+)?|rub|usd|доллар\w*|dollars?|"
           r"евро|eur)(?!\w)|\d[\d   ]*(?:[.,]\d+)?\s?[฿$€]|[฿$€]\s?\d[\d   ]*(?:[.,]\d+)?)")
_PM_RCPT = (r"(?:получен[аоы]?|получил[аи]?|поступил[аои]?|пришл[аои]|приш[её]л|дошл[аои]|дош[её]л|зачислен[аоы]?|"
            r"зачислил[аи]?|принят[аоы]?|принял[аи]?|received|arrived|credited|cleared|came\s+through|landed)")
_PM_GEN = r"(?:(?:пред|до)?оплаты|платежа|платежей|денег|средств|суммы|перевода)"
_PM_RNOUN = r"(?:поступлени[ея]|получени[ея]|зачислени[ея]|приход)"
_PM_CONF = (r"(?:подтвержда(?:ю|ем)|подтвердил[аи]?|подтверждено|подтвержд[её]н[аоы]?|"
            r"(?:могу|можем|рад[аы]?|хочу|хотим|спешу|спешим)\s+подтвердить|вижу|видим)")
_PM_BARE = r"(?:\d{1,3}(?:[   ,]\d{3})+|\d{3,6})(?![\w%]|[.,:/-]\d)"    # число без валюты (не дата и не время)
_PAY_SUMS = re.compile(
    # (ii) сумма + сказуемое получения · сказуемое + сумма · слово суммы + сказуемое · сказуемое + слово суммы
    r"(?<![\w.,])(?P<a1>" + _PM_AMT + r")\s+" + _W + r"{0,4}(?P<r1>" + _PM_RCPT + r")(?!\w)|"
    # шаг 3f (О3): сумма, тире, сказуемое в конце клаузы — «7790 бат — получили.»; сказуемое, двоеточие, сумма —
    # «Получено: 7790 бат.»
    r"(?<![\w.,])(?P<a6>" + _PM_AMT + r")\s+[—–-]\s+" + _PQ_DASH + r"(?P<r11>" + _PM_RCPT + r")(?!\w)" + _PQ_STOP + r"|"
    r"(?<!\w)(?P<r12>получено|получили|поступило|зачислено|принято|received)\s*:\s+(?:от\s+вас\s+|from\s+you\s+)?"
    r"(?P<a7>" + _PM_AMT + r")|"
    r"(?<!\w)(?P<r2>" + _PM_RCPT + r"|got)\s+" + _W + r"{0,3}(?P<a2>" + _PM_AMT + r")|"
    r"(?<!\w)(?P<n7>сумм[аыу]|amount|sum)\s+" + _W + r"{0,4}(?P<r3>" + _PM_RCPT + r")(?!\w)|"
    r"(?<!\w)(?P<r4>" + _PM_RCPT + r"|got)\s+" + _W + r"{0,3}(?P<n8>сумму|amount|sum)(?!\w)|"
    # (ii) число без валюты — только СРАЗУ за сказуемым получения и в конце клаузы: «Получили 7790, спасибо.»
    r"(?<!\w)(?P<r5>получил[аи]|получено|поступило|пришло|приняли|received|got)\s+(?:от\s+вас\s+|ваши\s+|your\s+|the\s+)?"
    r"(?P<a3>" + _PM_BARE + r")(?=\s*(?:$|[.!?,;…\n)]))|"
    # (ii) деньги или сумма у нас: «деньги у нас», «ваши 7790 бат у нас», «we have your payment / 7790 baht»
    r"(?<!\w)(?P<n9>деньги|средства|(?:пред|до)?оплата|плат[её]ж|перевод|сумма|" + _PM_AMT + r")\s+(?:уже\s+)?у\s+нас"
    r"(?=\s*(?:$|[.!?,;:…\n—–()]))|"
    r"(?<!\w)(?:we|i)\s+(?:now\s+|already\s+)?have\s+(?:your\s+|the\s+)(?:(?P<n10>payment|money|funds|transfer)(?!\w)|"
    + _PM_AMT + r")|"
    # (i) подтверждение получения отглагольным существительным (предмет — слово оплаты в родительном падеже или сумма)
    r"(?<!\w)(?P<c1>" + _PM_CONF + r")\s+" + _W + r"{0,3}" + _PM_RNOUN + r"\s+" + _W + r"{0,2}"
    r"(?:(?P<g1>" + _PM_GEN + r")(?!\w)|" + _PM_AMT + r")|"
    r"(?<!\w)" + _PM_RNOUN + r"\s+" + _W + r"{0,2}(?:(?P<g2>" + _PM_GEN + r")|" + _PM_AMT + r")\s+" + _W + r"{0,4}"
    r"(?P<c2>" + _PM_CONF + r"|зафиксирован[аоы]?)(?!\w)|"
    r"(?<!\w)(?P<c3>(?:we|i)\s+(?:hereby\s+|can\s+|now\s+|gladly\s+|happily\s+)*(?:confirm|acknowledge)|confirmed|"
    r"acknowledged|confirming|acknowledging)\s+" + _W + r"{0,3}(?:receipt|arrival)\s+of\s+" + _W + r"{0,3}"
    r"(?P<g3>payments?|money|funds|transfers?|amount|sum)(?!\w)|"
    r"(?<!\w)(?:receipt|arrival)\s+of\s+" + _W + r"{0,3}(?P<g4>payments?|money|funds|transfers?|amount|sum)\s+"
    + _W + r"{0,3}(?P<c4>confirmed|acknowledged)(?!\w)|"
    r"(?<!\w)payment\s+receipt\s+(?:is\s+|has\s+been\s+|was\s+)?(?P<c5>confirmed|acknowledged)(?!\w)|"
    # (iii, свой состязательный поиск) благодарность за оплату: «Спасибо за оплату!», «Thank you for your payment!» —
    # клиент читает её как подтверждение; «заранее спасибо» и «in advance» — будущее, не утверждение
    r"(?<!\w)(?<!заранее\s)(?P<t1>спасибо|благодар(?:им|ю))\s+(?:вам\s+|большое\s+|огромное\s+)*за\s+"
    r"(?:ваш\w*\s+|быстр\w+\s+|своевременн\w+\s+|оперативн\w+\s+|полн\w+\s+)*"
    r"(?:(?:пред|до)?оплату|плат[её]ж|перевод(?!\s+(?:договор|документ|текст|сообщени|правил|инструкци))|деньги)"
    r"(?!\w)(?!\s+заранее)|"
    r"(?<!\w)(?P<t2>thank\s+you|thanks|thank\s+u)\s+(?:so\s+much\s+|very\s+much\s+|a\s+lot\s+)?for\s+"
    r"(?:your\s+|the\s+|this\s+|prompt\s+|quick\s+|full\s+|timely\s+)*(?:payment|transfer|money)(?!\w)"
    r"(?!\s+(?:links?|details|methods?|options?|receipts?|screenshots?|info|information|terms|deadline|date|"
    r"requests?|reminders?|instructions?|page|button|plan|schedule|form|reference|confirmation|slip|proof|photo|"
    r"picture|image|notification|in\s+advance))",
    re.I)
_PC_CAUSE = re.compile(r"(?<!\w)(?:because|now\s+that|ведь|так\s+как|потому\s+что|поскольку)(?!\w)", re.I)

# K3-FIX шаг 3e (10.10.2026; решение координатора после круга 3d, пункты 1–3). Четвёртый проход ТОГО ЖЕ определения
# (`_PAY_CTX`) — три семейства, которых текст САМ оплатой не называет; их судит `_PayClaim._ctx` по контексту сверки:
#   (1) краткое утвердительное получение или подтверждение БЕЗ предмета — клауза из одних слов согласия и сказуемого
#       получения, подтверждения или «всё в порядке» («Да, всё пришло.», «Получили, спасибо.», «Всё в порядке,
#       получили.», «Да, всё в порядке.», «We got it, thanks!», «Yes, received.») и ответ из одних слов согласия («Да,
#       спасибо!»). Предмет такой клаузы задаёт ВОПРОС клиента: утверждение — только при признаке «входящее клиента — об
#       оплате» (`pay_asked`; смешанное входящее — тоже). Без признака (вопрос о документе, вопроса нет) — имя
#       `PC_NOASK`. Не утверждение и при признаке: вопрос; отрицание или обещание проверки в том же предложении
#       («Получили, договор проверим завтра»); ответ САМ говорит, что оплата не видна или проверяется (`unsettled`:
#       «Получили, спасибо. Оплату проверит коллега.», «Получили. Проверим и ответим.», «…в кассе пока не видим»);
#       предмет назван раньше в том же предложении («Спасибо за информацию, получили.»); за «да» — другой предмет («Да,
#       шлем дадим.»). Клауза с предметом («получили ваш паспорт / чек / фото») в проход не попадает вовсе. Туда же, по
#       своему свежему поиску: «оплата / деньги на месте» и «оплата есть» без кассы — утверждение только при признаке
#       (без него «оплата на месте» — правило оплаты, «есть оплата картой» — способ оплаты);
#   (2) «долга нет»: «долга / задолженности (по аренде) нет», «нет долга», «ничего не должны», «долг погашен», «всё
#       погашено», «счёт закрыт», «аренда закрыта», «всё закрыто» (при слове оплаты, аренды, счёта или долга в
#       предложении либо при вопросе об оплате; «заявка закрыта» в проход не попадает), «баланс нулевой», «к оплате
#       0», «доплачивать ничего не нужно», «с оплатой проблем нет», «вы всё оплатили»; англ. «no balance due», «nothing
#       owed», «you don't owe anything», «all settled», «balance is zero», «you've paid». Собственное «нет / не / no»
#       семейства (группы `_PC_OWN`) отрицанием утверждения не считается; постороннее («долг не погашен», «долга пока
#       нет?») — как везде. Речь о другой услуге без аренды раньше неё («за доставку вы ничего не должны») — `PC_ITEM`;
#       правило о сроке оплаты («сейчас вы ничего не должны — оплата при получении») — не утверждение; «вы оплатили» в
#       пересказе слов клиента — `PC_SAID`;
#   (3) число БЕЗ валюты при сказуемом получения, в том числе не вплотную («Да, 7790 получили.», «7790 пришли,
#       спасибо.», «В кассе вижу 7790.», «Yes, 7790 received.»): утверждение, когда число равно известной ДЕНЕЖНОЙ сумме
#       сверки (`pay_sums`: итог и цена аренды, строки кассы, названное в переписке и клиентом), стоит за кодом валюты
#       («THB 5000 received») либо входящее клиента — об оплате; иное число, номер байка или заказа, часть телефона —
#       имя `PC_NUM`. Число с валютой — прежние семейства; к ним — «вижу» вплотную к сумме («В кассе вижу 7790 бат»; в
#       бумаге клиента — «вижу 7790 бат в вашем чеке» — `PC_OTHER`).
PC_NOASK = "краткое подтверждение без вопроса клиента об оплате"
PC_HOLD = "ответ сам говорит: оплата не видна или проверяется"
PC_OTHER = "согласие относится к другому предмету"
PC_NUM = "число — не известная денежная сумма сверки"
PC_ITEM = "речь о другой услуге, а не об оплате аренды"
PC_NOMONEY = "«закрыто» без оплаты, аренды, счёта или долга"
PC_SAID = "слова клиента в пересказе"
_PQ_FILL = (r"(?:да(?:-да)?|ага|угу|конечно|верно|точно|именно|разумеется|действительно|вс[её]|все|это|уже|только\s+что|"
            r"недавно|сегодня|вчера|утром|дн[её]м|вечером|ночью|сейчас|спасибо|большое|огромное|благодар(?:ю|им)|мы|я|"
            r"у\s+нас|от\s+вас|вам|вас|е[её]|его|их|полностью|целиком|сполна|в\s+полном\s+(?:объ[её]ме|размере)|успешно|"
            r"благополучно|так|же|тоже|также|вполне|в\s+порядке|хорошо|отлично|замечательно|ок|окей|и|and|"
            r"на\s+(?:наш\s+)?(?:сч[её]т|карту)|в\s+касс[еу]|наличными|переводом|"
            r"yes|yeah|yep|yup|sure|indeed|certainly|absolutely|of\s+course|we(?:['’]ve)?|i(?:['’]ve)?|it(?:['’]s)?|"
            r"have|has|just|already|now|all|everything|that|this|them|thanks|thank\s+you|thank\s+u|so\s+much|"
            r"very\s+much|a\s+lot|safely|fully|in\s+full|successfully|good|great|fine|perfect|ok|okay|well|is|are|was|"
            r"been|here|today|yesterday|(?:this|in\s+the)\s+(?:morning|afternoon|evening)|last\s+night|earlier|too|"
            r"also|as\s+well|from\s+you|with\s+thanks|on\s+our\s+(?:side|end)|(?:in|into|to)\s+our\s+account)")
_PQ_GOT = (r"(?:получил[аи]?|получен[аоы]?|пришл[аои]|приш[её]л|поступил[аои]?|дошл[аои]|дош[её]л|прошл[аои]|прош[её]л|"
           r"зачислен[аоы]?|зачислил[аи]|отражен[аоы]?|принят[аы]?|упал[аои]|зашл[аои]|заш[её]л|есть|имеется|на\s+месте|"
           r"подтвержда(?:ю|ем)(?:\s+(?:получение|поступление|зачисление))?|подтвержд[её]н[аоы]?|вижу|видим|"
           r"received|got\s+(?:it|them|that|everything|all)|have\s+(?:it|them)|(?:we|i|it)\s+(?:did|have|has)|arrived|"
           r"came\s+through|come\s+through|went\s+through|gone\s+through|landed|cleared|confirmed|"
           r"(?:can\s+|could\s+)?confirm(?:\s+receipt)?)")
_PQ_STATE = (r"(?:вс[её]\s+(?:в\s+(?:полном\s+)?порядке|хорошо|отлично|ок|окей|супер|замечательно|в\s+норме|на\s+месте)|"
             r"(?:all|everything)(?:\s+is|['’]s|\s+looks)?\s+(?:good|fine|ok|okay|in\s+order|great|perfect|set)|"
             r"it(?:['’]s|\s+is)\s+all\s+(?:good|fine))")
# K3-FIX шаг 3f (10.10.2026; решение координатора после круга 3e, п.1 — остаток О1 шага 3e). На входящее клиента об
# оплате (`pay_asked`) утверждением оплаты судится и ответ БЕЗ сказуемого получения:
#   (а) слово согласия во главе предложения — как «да» (`_PQ_YES`, группа `q3`): «Конечно.», «Разумеется, спасибо.»,
#       «Of course.», «Sure.», «Certainly.», «Absolutely.»; за ним в предложении — одни слова согласия («Конечно, договор
#       пришлём.» — `PC_OTHER`);
#   (б) ответ, который ЦЕЛИКОМ состоит из согласия, одобрения, благодарности, принятия или знака (`_PQ_AGREE`,
#       `_PQ_SIGN`; группа `q5` — первое такое слово или знак): «Принято.», «Хорошо, спасибо!», «Отлично 👍», «Верно.»,
#       «Great, thank you!», «👍», «🙏»; между словами — только знаки препинания и значки (`_PQ_GAP`), рядом допустимы
#       приветствие и прощание (`_PQ_POLITE`: «Здравствуйте! Спасибо!», «Thanks, have a nice day!»). Ответ с содержанием
#       (реквизиты, вопрос, инструкция, «проверим», «уточню», «договор пришлём») под это правило не попадает вовсе — его
#       судят прежние проходы. Без признака входящего об оплате — `PC_NOASK`.
#   Словари закрытые; каждое слово — отдельной строкой кортежа (сначала дословно словарь решения, затем близкие слова).
#   Разбор ответа на слова ОДНОЗНАЧЕН (иначе перебор вариантов на длинном тексте растёт взрывом): слово словаря не
#   бывает началом или концом другой строки словаря, годной самой по себе («спасибо большое» — слово «спасибо» и слово
#   вежливости «большое», а не одна строка; «да-да» — два «да» через дефис), а слово словаря именем не считается.
_PQ_YES_MORE = (r"конечно(?:\s+же)?", r"разумеется", r"безусловно", r"естественно",
                r"sure(?:\s+thing)?", r"of\s+course", r"certainly", r"absolutely", r"definitely", r"indeed")
_PQ_YES = r"(?:да(?:-да)?|ага|угу|yes|yeah|yep|yup|" + "|".join(_PQ_YES_MORE) + r")"
_PQ_NOD_RU = (r"верно", r"точно", r"именно", r"так\s+и\s+есть", r"принято", r"получено", r"хорошо",
              r"отлично", r"супер", r"спасибо", r"благодар(?:ю|им)",
              r"вс[её]\s+(?:верно|так|точно|правильно)", r"правильно", r"совершенно\s+верно",
              r"абсолютно", r"несомненно", r"принял[аи]?", r"понял[аи]?", r"понятно", r"ясно",
              r"прекрасно", r"замечательно", r"великолепно", r"здорово", r"ок", r"окей")
_PQ_NOD_EN = (r"right", r"correct", r"received", r"got\s+it", r"great", r"perfect",
              r"(?:many\s+)?thanks(?:\s+a\s+lot|\s+so\s+much|\s+very\s+much)?",
              r"thank\s+(?:you|u)(?:\s+so\s+much|\s+very\s+much)?",
              r"exactly", r"that['’]?s\s+(?:right|correct)", r"for\s+sure", r"well\s+received", r"noted", r"understood",
              r"acknowledged", r"awesome", r"wonderful", r"excellent", r"brilliant", r"lovely", r"nice", r"good", r"fine",
              r"super", r"cool", r"ok", r"okay", r"all\s+right", r"alright", r"much\s+appreciated", r"appreciated",
              r"cheers")
_PQ_AGREE = r"(?:да|ага|угу|yes|yeah|yep|yup|" + "|".join(_PQ_YES_MORE + _PQ_NOD_RU + _PQ_NOD_EN) + r")"
# знаки согласия — закрытый набор (коды Юникода): 👍 ✅ 👌 🙏 и близкие ✔ ☑ 🆗 🤝
_PQ_SIGN_CODES = (0x1F44D, 0x2705, 0x1F44C, 0x1F64F, 0x2714, 0x2611, 0x1F197, 0x1F91D)
_PQ_SIGN = "[" + "".join(chr(c) for c in _PQ_SIGN_CODES) + "]"
_PQ_GAP = r"(?:[\s,.!…—–;:()-]|" + _PQ_EMO + r")"          # между словами ответа-согласия: препинание и значки
_PQ_GAPN = r"(?:(?!" + _PQ_SIGN + r")" + _PQ_GAP + r")"     # то же, но не знак согласия (перед первым словом ответа)
# слова вежливости рядом с согласием (сами согласием не считаются): приветствие, прощание, «большое / вам / так»
_PQ_POLITE_RU = (r"здравствуйте", r"здравствуй", r"добрый\s+(?:день|вечер)", r"доброе\s+утро", r"привет(?:ствую)?",
                 r"хорошего\s+(?:вам\s+)?(?:дня|вечера|отдыха)", r"всего\s+(?:доброго|хорошего)",
                 r"до\s+(?:встречи|завтра|свидания)", r"большое", r"огромное", r"вам", r"вас", r"так")
_PQ_POLITE_EN = (r"hello", r"hi", r"hey", r"good\s+(?:morning|afternoon|evening|day)",
                 r"have\s+a\s+(?:nice|great|good|lovely)\s+(?:day|evening|trip|ride)",
                 r"see\s+you(?:\s+(?:soon|tomorrow|then|later))?", r"bye", r"goodbye", r"take\s+care")
_PQ_POLITE = r"(?:" + "|".join(_PQ_POLITE_RU + _PQ_POLITE_EN) + r")"
# обращение по имени ПОСЛЕ слова ответа-согласия: запятая и одно-два слова с заглавной буквы — «Спасибо, Алексей!»,
# «Thank you, John!», «Принято, Иван Петрович, спасибо.» (имя ПЕРЕД словом от начала предложения неотличимо — не
# судится; слово словаря именем не считается — разбор однозначен)
_PQ_NAME = (r"(?:,\s*(?!(?:" + _PQ_POLITE + r"|" + _PQ_AGREE + r")(?!\w))"
            r"(?-i:[А-ЯЁA-Z][а-яёa-z]+)(?:\s+(?-i:[А-ЯЁA-Z][а-яёa-z]+))?(?!\w))")
_PN_NUM = (r"(?:\d{1,3}(?:[   ,.]\d{3})+|\d{3,6})(?![\w%]|[.,:/-]\d)"
           r"(?!\s?(?:бат|baht|thb|руб|rub|usd|доллар|dollar|евро|eur|[฿$€]))"
           r"(?!\s*(?:дн|сут|день|дня|дней|ноч|час|мин|шт|км|km|days?|nights?|hours?|cc|сс|фото|photos?|файл|files?))")
_PN_GOT = _PM_RCPT
_PN_SEE = r"(?:вижу|видим)"                               # «В кассе вижу 7790 (бат)» — только вплотную к сумме
_PD_DEBT = r"(?:долг(?:а|у|ом|е|и|ов|ам|ами|ах)?|задолженност(?:ь|и|ей|ью|ям|ями|ях))"
_PD_NONE = r"(?:нет|не\s+имеется|не\s+числится|не\s+осталось|отсутству(?:ет|ют))"
_PD_DONE = r"(?:(?:полностью\s+|целиком\s+|уже\s+)*(?:погашен[аоы]?|закрыт[аоы]?|выплачен[аоы]?))"
_PAY_CTX = re.compile(
    # шаг 3f (О1): ответ ЦЕЛИКОМ из согласия, одобрения, благодарности, принятия или знака — первым, от начала текста
    # (до первого слова согласия или знака — вежливость; дальше — слова словарей через промежутки; до конца текста)
    r"\A" + _PQ_GAPN + r"*(?:" + _PQ_POLITE + r"(?!\w)" + _PQ_NAME + r"?" + _PQ_GAPN + r"+)*"
    r"(?P<q5>" + _PQ_AGREE + r"(?!\w)|" + _PQ_SIGN + r")" + _PQ_NAME + r"?"
    r"(?:" + _PQ_GAP + r"+(?:" + _PQ_POLITE + r"|" + _PQ_AGREE + r")(?!\w)" + _PQ_NAME + r"?)*" + _PQ_GAP + r"*\Z|"
    # (1) краткое получение или подтверждение без предмета: клауза из слов согласия и сказуемого · ответ-согласие
    r"(?:^|(?<=[.!?…\n,;:—–(]))\s*(?:" + _PQ_FILL + r"\s+)*(?:(?P<q1>" + _PQ_GOT + r")|(?P<q2>" + _PQ_STATE + r"))"
    r"(?:\s+(?:" + _PQ_FILL + r"|" + _PQ_GOT + r"))*(?=\s*(?:$|[.!?…\n,;:—–)]|" + _PQ_EMO + r"))"
    r"(?!\s*[,:—–]\s*(?:что|как|когда|где|that|how|when|where)(?!\w))|"
    r"(?:^|(?<=[.!?…\n]))\s*(?P<q3>" + _PQ_YES + r")(?=\s*(?:$|[,.!…\n]|" + _PQ_EMO + r"))|"
    # предмет назван, но получен ли он, говорит только вопрос: «оплата / деньги на месте» (иначе — «оплата на месте»)
    r"(?<!\w)(?P<q4>(?:пред|до)?оплата|плат[её]ж|деньги|перевод|средства)\s+(?:уже\s+|ваш\w*\s+)*на\s+месте(?!\w)|"
    # (3) число без валюты при сказуемом получения: число … сказуемое · сказуемое … число · «N у нас» · «we have your N»
    r"(?<![\w.,:/+-])(?P<b1>" + _PN_NUM + r")\s+" + _W + r"{0,3}(?P<r6>" + _PN_GOT + r")(?!\w)(?!\s+бы(?!\w))|"
    # шаг 3f (О3): число, ТИРЕ и сказуемое получения в конце клаузы — «7790 — получили.» (такое тире клаузу не рвёт)
    r"(?<![\w.,:/+-])(?P<b7>" + _PN_NUM + r")\s+[—–-]\s+" + _PQ_DASH + r"(?P<r10>" + _PN_GOT + r")(?!\w)" + _PQ_STOP + r"|"
    r"(?<!\w)(?P<r7>" + _PN_GOT + r"|got)\s+" + _W + r"{0,3}(?P<b2>" + _PN_NUM + r")|"
    r"(?<![\w.,:/+-])(?P<b3>" + _PN_NUM + r")\s+(?:уже\s+)?у\s+нас(?=\s*(?:$|[.!?,;:…\n—–()]))|"
    r"(?<!\w)(?:we|i)\s+(?:now\s+|already\s+)?have\s+(?:your\s+|the\s+)(?P<b4>" + _PN_NUM + r")|"
    # «вижу» вплотную к сумме, с валютой или без: «В кассе вижу 7790 бат», «Вижу ваши 7790», «7790 бат в кассе вижу»
    r"(?<!\w)(?P<r8>" + _PN_SEE + r"|see)\s+(?:ваш\w*\s+|эт\w+\s+|от\s+вас\s+|your\s+|the\s+)*"
    r"(?:(?P<a4>" + _PM_AMT + r")|(?P<b5>" + _PN_NUM + r"))|"
    r"(?<![\w.,:/+-])(?:(?P<a5>" + _PM_AMT + r")|(?P<b6>" + _PN_NUM + r"))\s+(?:в\s+кассе\s+|у\s+нас\s+|от\s+вас\s+)?"
    r"(?P<r9>" + _PN_SEE + r")(?!\w)|"
    # (2) «долга нет»: предмет + «нет» · предмет + «погашен / закрыт» · «нет долга» · «ничего не должны» · «всё погашено»
    # · «всё закрыто» · «счёт / аренда / оплата закрыт(а)»; англ. no balance · nothing owed · don't owe · all settled
    r"(?<!\w)(?P<d1>" + _PD_DEBT + r")\s+" + _W + r"{0,4}(?P<x1>" + _PD_NONE + r")(?!\w)|"
    r"(?<!\w)(?P<d2>" + _PD_DEBT + r")\s+" + _W + r"{0,4}" + _PD_DONE + r"(?!\w)|"
    r"(?<!\w)(?P<x3>нет)\s+(?:никак\w+\s+|у\s+вас\s+|за\s+вами\s+)*(?P<d3>долга|долгов|задолженности|задолженностей)"
    r"(?!\w)|"
    r"(?<!\w)(?P<x4>ничего\s+(?:нам\s+|больше\s+|уже\s+)*не\s+должн[ыа]|ничего\s+(?:нам\s+|больше\s+)*не\s+должен|"
    r"не\s+должн[ыа]\s+(?:нам\s+)?(?:больше\s+)?ничего|не\s+должен\s+(?:нам\s+)?(?:больше\s+)?ничего)"
    r"(?=\s*(?:$|[.!?,;:…\n—–()]))|"
    r"(?<!\w)(?P<x5>ничего\s+(?:больше\s+)?доплачивать\s+не\s+(?:нужно|надо|требуется|придётся)|"
    r"доплачивать\s+(?:больше\s+)?ничего\s+не\s+(?:нужно|надо|требуется|придётся)|"
    r"доплат[аы]\s+не\s+(?:нужна|нужно|требуется)|"
    r"больше\s+(?:ничего\s+)?(?:платить|оплачивать)\s+(?:ничего\s+)?не\s+(?:нужно|надо|требуется|придётся)|"
    r"(?:платить|оплачивать)\s+больше\s+(?:ничего\s+)?не\s+(?:нужно|надо|требуется|придётся))(?!\w)|"
    # «с оплатой проблем нет», «по оплате вопросов нет», «no issues with your payment» — «с оплатой всё в порядке»
    r"(?<!\w)(?P<x6>(?:с\s+оплатой|с\s+платежом|по\s+оплате|по\s+платежу|по\s+расч[её]там)\s+(?:у\s+вас\s+|никаких\s+)*"
    r"(?:проблем|вопросов|претензий|замечаний)\s+нет|(?:проблем|вопросов|претензий|замечаний)\s+(?:с\s+оплатой|"
    r"с\s+платежом|по\s+оплате|по\s+платежу|по\s+расч[её]там)\s+нет|нет\s+(?:никаких\s+)?(?:проблем|вопросов|претензий)\s+"
    r"(?:с\s+оплатой|по\s+оплате)|no\s+(?:issues?|problems?)\s+with\s+(?:the\s+|your\s+)?payment)(?!\w)"
    r"(?!\s+(?:links?|details|methods?|options?))|"
    # «вы всё оплатили», «вы полностью рассчитались», «you've paid» — то же «всё оплачено» действительным залогом
    r"(?<!\w)(?P<u1>вы|ты)\s+(?:уже\s+|полностью\s+|вс[её]\s+|нам\s+|давно\s+)*(?:(?:пред|до)?оплатил[аи]?|заплатил[аи]?|"
    r"рассчитал(?:ись|ся|ась)|расплатил(?:ись|ся|ась)|погасил[аи]?)(?!\w)(?!\s+бы(?!\w))|"
    r"(?<!\w)(?P<u2>you)(?:['’]ve|\s+have)?\s+(?:already\s+|fully\s+|now\s+)*(?:paid|settled\s+up)(?!\w)|"
    r"(?<!\w)(?P<d14>остаток|к\s+оплате|доплата|долг|задолженность|баланс)\s*(?:[—–:-]\s*|составляет\s+|"
    r"рав(?:ен|на|но)\s+)?(?:0|ноль|нол[ьяю]|нулю|нулев(?:ой|ая|ое))(?![\d.,]\d)(?!\w)|"
    r"(?<!\w)(?P<d5>вс[её])\s+(?:уже\s+|полностью\s+|давно\s+)*погашено(?!\w)|"
    r"(?<!\w)(?P<d6>вс[её])\s+(?:уже\s+|полностью\s+|давно\s+)*закрыто(?!\w)|"
    r"(?<!\w)(?P<d7>сч[её]т|аренда|оплата|расч[её]т|баланс)\s+" + _W + r"{0,3}" + _PD_DONE + r"(?!\w)|"
    r"(?<!\w)(?P<x9>no)\s+(?:outstanding\s+|remaining\s+|unpaid\s+|open\s+)?(?:(?P<d9>balance|debt|dues)|"
    r"(?:amount|payments?)\s+(?:is\s+|are\s+)?(?:due|owed|owing|outstanding))(?!\w)|"
    r"(?<!\w)(?P<x10>nothing)\s+(?:(?:is\s+|more\s+is\s+|else\s+is\s+)?(?:owed|owing|due|outstanding)|"
    r"(?:more|else|left)\s+to\s+pay)(?!\w)|"
    r"(?<!\w)(?:you|u)\s+(?P<x11>(?:do\s+not|don['’]?t)\s+owe\s+(?:us\s+)?anything|owe\s+(?:us\s+)?nothing)(?!\w)|"
    r"(?<!\w)(?P<d12>all|everything(?:\s+is|['’]s)?|it(?:['’]s|\s+is)\s+all|you(?:['’]re|\s+are)\s+all)\s+"
    r"(?:now\s+|fully\s+)?(?:settled(?:\s+up)?|squared\s+away|paid\s+up|paid\s+off)(?!\w)(?!\s+in(?!\w))|"
    r"(?<!\w)(?P<d13>balance|account|bill|invoice)\s+" + _W + r"{0,3}(?:settled|cleared|paid\s+off|zero|nil)(?!\w)|"
    r"(?<!\w)(?P<d15>balance(?:\s+due)?|amount\s+due)\s*(?:is\s+|:\s*|[—–-]\s*)?(?:0|zero|nil)(?![\d.,]\d)(?!\w)|"
    r"(?<!\w)(?P<d16>zero|nil)\s+(?:balance|debt)(?!\w)",
    re.I)
_PQ_ONLY = re.compile(r"(?:(?:[\s,]|" + _PQ_EMO + r")*" + _PQ_FILL + r")*(?:[\s,]|" + _PQ_EMO + r")*", re.I)   # за «да» — одни слова согласия
# слова клиента в пересказе: «по вашим словам, вы оплатили вчера» — не наше утверждение
_PU_SAID = re.compile(r"(?<!\w)(?:по\s+вашим\s+словам|с\s+ваших\s+слов|как\s+вы\s+(?:пишете|написали|сказали|говорите|"
                      r"сообщили)|вы\s+(?:пишете|написали|сказали|говорите|сообщили|указали)|you\s+(?:said|say|wrote|"
                      r"mentioned|told)|according\s+to\s+you(?:r\s+message)?|as\s+you\s+(?:said|wrote|mentioned))(?!\w)",
                      re.I)
# обещание ПРОВЕРКИ (а не слово будущего вообще): «Получили, проверим и сообщим» — получено сообщение, не оплата
_PQ_CHECK = re.compile(r"(?<!\w)(?:провер(?:ю|им|ит|ят|яю|яем|яет|ить|ять|ка|ки|ку)\w*|свер(?:ю|им|ит|ят|яю|яем|ить|ять)"
                       r"\w*|уточн(?:ю|им|ит|ят|яю|яем|ить|ять)\w*|выясн\w+|посмотр(?:ю|им|ит|ят|еть)|убед(?:имся|юсь|иться)|"
                       r"подтверд(?:им|ит|ят)|подтвержу|check|verify|look\s+into|double-check|find\s+out|make\s+sure|"
                       r"get\s+back|will\s+confirm|(?:i|we)['’]ll\s+confirm)(?!\w)", re.I)
# слова успокоения — не отрицание получения: «Да, получили, не волнуйтесь.»
_PQ_CALM = re.compile(r"(?<!\w)(?:не\s+(?:волнуйтесь|переживайте|беспокойтесь|за\s+что)|без\s+проблем|ничего\s+страшного|"
                      r"no\s+worries|don['’]?t\s+worry|do\s+not\s+worry|no\s+problem|not\s+a\s+problem|not\s+at\s+all)"
                      r"(?!\w)", re.I)
_PQ_PAYWORD = re.compile(r"(?<!\w)(?:(?:пред|до)?оплат\w*|плат[её]ж\w*|перевод(?!\w*\s+(?:договор|документ|текст|сообщени))"
                         r"\w*|деньг\w*|денег|средств\w*|поступлени\w*|payments?|transfers?|money|funds)(?!\w)", re.I)
_PN_CODE = re.compile(r"(?<![A-Za-z])(?:thb|usd|eur|rub|baht)\s*$", re.I)   # код валюты перед числом: «THB 5000»
_PF_METHOD = re.compile(r"(?<!\w)(?:карт(?:ой|у|а|е|ы)|наличн\w+|переводом|онлайн|терминал\w*|qr|cards?|cash|online)(?!\w)",
                        re.I)                                                # способ оплаты, а не её получение
# число на месте НОМЕРА: за названием модели («NMAX 90101»), словом «байк / номер / заказ», знаком «№ / #»
_PN_MODEL = re.compile(r"(?<![A-Za-z])(?!THB|USD|EUR|RUB)[A-Z]{2,}[A-Za-z0-9]*(?:\s+\d{2,3}(?:cc|сс)?)?\s*$")
_PN_WORD = re.compile(r"(?:байк\w*|скутер\w*|мотоцикл\w*|номер\w*|заказ\w*|брон\w+|договор\w*|код\w*|пин\w*|bike|scooter|"
                      r"order|booking|contract|code|pin|№|#)\s*$", re.I)
_PD_MONEY = re.compile(r"оплат|аренд|сч[её]т|счету|счете|долг|задолженн|плат[её]ж|расч[её]т|деньг|денег|баланс|rent|payment|"
                       r"bill|invoice|balance", re.I)
_PD_ITEM = re.compile(r"доставк\w*|шлем\w*|страхов\w*|топлив\w*|бензин\w*|ремонт\w*|царапин\w*|повреждени\w*|штраф\w*|"
                      r"мойк\w*|отмен\w*|опоздани\w*|просрочк\w*|delivery|helmets?|insurance|fuel|petrol|gasoline|"
                      r"damages?|repairs?|scratch\w*|fines?|wash\w*|cancel\w*|late\s+fee", re.I)
# «ничего не должны» как правило о СРОКЕ оплаты, а не состояние расчётов: «сейчас / пока / до получения байка …»
_PD_WHEN = re.compile(r"(?<!\w)(?:сейчас|пока|заранее|предварительно|до\s+(?:получени\w+|выдач\w+|встреч\w+|приезд\w+|"
                      r"начал\w+)|при\s+(?:получени\w+|выдач\w+|встреч\w+|брониров\w+)|now|yet|upfront|in\s+advance|until|"
                      r"before|at\s+pickup|for\s+now)(?!\w)", re.I)
_PD_WE = re.compile(r"(?<!\w)(?:мы|я)(?!\w)", re.I)
_PD_IF = re.compile(r"(?<!\w)(?:если|при\s+условии|if|as\s+long\s+as|provided|unless)(?!\w)", re.I)
# сумма видна В БУМАГЕ клиента, а не в кассе: «вижу 7790 бат в вашем чеке / на скриншоте / in the invoice»
_PN_INDOC = re.compile(r"(?<!\w)(?:(?:в|из|in|from)\s+(?:ваш\w*\s+|эт\w+\s+|присланн\w+\s+|the\s+|your\s+|this\s+)*"
                       r"(?:сч[её]т[еа]|invoice)|(?:в|на|из|in|on|from)\s+(?:ваш\w*\s+|эт\w+\s+|присланн\w+\s+|the\s+|"
                       r"your\s+|this\s+)*(?:чек[еа]|скрин\w*|фото\w*|договор\w*|квитанци\w*|сообщени\w*|заявк\w*|письм\w+|"
                       r"receipt|screenshot|photo|picture|contract|message|email))(?!\w)", re.I)
# названный в том же предложении предмет получения — документ, сообщение, фото: «…payment request, received» — не оплата
_PQ_THINGS = (_PC_DOC.pattern + r"|фото\w*|паспорт\w*|водительск\w+|договор\w*|скрин\w*|письм\w+|photos?|pictures?|"
              r"passports?|licen[cs]es?|contracts?|messages?|emails?|documents?")
_PQ_THING = re.compile(r"(?<!\w)(?:" + _PQ_THINGS + r")(?!\w)", re.I)
# иной предмет обещанной проверки («договор проверим», «уточним детали доставки») — тогда проверяют не оплату
_PQ_TOPIC = re.compile(r"(?<!\w)(?:" + _PQ_THINGS + r"|" + _PD_ITEM.pattern + r"|байк\w*|скутер\w*|мотоцикл\w*|"
                       r"адрес\w*|детал\w+|наличи\w+|состояни\w+|бронь|брони|bikes?|scooters?|address|availability|"
                       r"booking)(?!\w)", re.I)
# бумага ОБ ОПЛАТЕ: её проверка — проверка оплаты («Чек проверим и подтвердим»)
_PQ_PROOF = re.compile(r"(?<!\w)(?:чек\w*|квитанци\w*|скрин\w*|receipts?|screenshots?|slip)(?!\w)", re.I)
# касса и видимость: «в кассе пока не видим», «на счёт не поступило» — ответ сам говорит, что денег не видно
_PQ_SEEN = re.compile(r"(?<!\w)(?:касс\w*|вижу|видим|видно|видна|виден|поступил\w*|поступлени\w*|зачисл\w+|"
                      r"на\s+сч[её]т[еу]?|see|seen|show(?:s|ing|ed)?\s+up|arrived|landed|reflected)(?!\w)", re.I)
# ОДНО определение, четыре прохода: прежние формы, формы 3b, семейства 3d, семейства 3e (контекст сверки)
_PAY_PASSES = (_PAY_AFFIRM, _PAY_FORMS, _PAY_SUMS, _PAY_CTX)
_PC_SUBJ = ("n1", "n2", "n3", "n4", "n5", "n6", "a1", "a2", "n7", "n8", "n10",   # предмет совпадения: именные группы
            "b1", "b2", "b3", "b4", "a4", "b5", "a5", "b6", "d1", "d2", "d7",    # шаг 3e: число, сумма при «вижу», долг
            "a6", "b7", "n12")                                                   # шаг 3f: предмет перед тире, двоеточием
_PC_PREDS = ("v1", "v3", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9")   # сказуемое совпадения
_PC_RCPT = ("r1", "r2", "r3", "r4", "r5", "r6", "r7", "r10", "r11", "r12")      # шаг 3f: сказуемое за тире, перед двоеточием
_PC_OWN = ("x1", "x3", "x4", "x5", "x6", "x9", "x10", "x11", "q1")   # шаг 3e: собственные «нет / не / no», связка
# шаг 3f: `q5` — ответ целиком из согласия (судится той же дорогой краткого подтверждения); `b7` — число перед тире
_PC_BARE, _PC_NUMS = ("q1", "q2", "q3", "q4", "q5"), ("b1", "b2", "b3", "b4", "b5", "b6", "b7")
# слова при сумме, которые сами стоят после предлога: «ссылку на ОПЛАТУ 7790 бат получили» — предлог судится у них
_PC_OF = re.compile(r"(?:пред|до)?оплат\w*|плат[её]ж\w*|аренд\w*|брон\w*|продлени\w*|payment|rent\w*|booking", re.I)
_PC_YOU = re.compile(r"(?<!\w)(?:вы|ты|you)(?:\s+(?:уже|тоже|также|have|had|already|also))*\s*$", re.I)
_PC_LEAD = ("a1", "b1", "a6", "b7")        # шаг 3e: сумма и число ПЕРЕД сказуемым получения — получатель стоит до них
_PC_THANK = re.compile(r"(?<!\w)thanks?\s+(?:to\s+)?(?:you|u)\s*$", re.I)


class _PayClaim:
    """ОДНО определение «текст утверждает, что оплата получена» (K3-FIX3 N4; им живут `money_roles` и `pay_claimed`,
    т.е. ремонт F3 шага 1 — то же место, не второе). Утверждение — совпадение `_PAY_AFFIRM` или (шаг 3b, D1) формы
    `_PAY_FORMS`, в клаузе которого (от начала клаузы до конца совпадения) нет отрицания и нет будущей проверки, условия
    или вопроса, а предложение не кончается «?», и к которому не приложимо ни одно исключение не-утверждений (шаг 3c —
    одни на оба прохода, `verdict`). Отрицание («оплату пока не вижу», «не поступила») и обещание проверки («сверит и
    подтвердит», «как только отразится», «будет зафиксирована») ложного подтверждения не дают — и ложной блокировки
    тоже. `search` → совпадение | None; `explain` → названные исходы всех совпадений. Шаг 3e: экземпляр несёт КОНТЕКСТ
    сверки — `asked` (входящее клиента об оплате, `pay_asked`) и `sums` (известные денежные суммы, `pay_sums`); у
    экземпляра модуля `_PAY_CLAIM` контекста нет (вопроса нет, сумм нет) — как было."""

    def __init__(self, asked=False, sums=()):
        self.asked, self.sums = bool(asked), frozenset(sums or ())

    @staticmethod
    def _matches(s):
        for rx in _PAY_PASSES:
            for m in rx.finditer(s):
                yield rx, m

    @staticmethod
    def verdict(s, rx, m, asked=False, sums=(), hold=False):
        """Исход ОДНОГО совпадения: `PC_CLAIM` либо ИМЯ того, почему это не утверждение (шаг 3c; пустым исход не бывает).
        Клауза — от разрыва/начала предложения `a` до конца совпадения, как было. Исключения форм (до 3c — `_form_ok`,
        только у форм 3b) судят любое совпадение: долженствование или ожидание ПРИ сказуемом (шаг 3d: `_governs`) либо
        сразу за ним («оплачено будет»; слово дальше — уже другое сказуемое: «оплата получена и договор будет отправлен»
        — утверждение); предмет после предлога (шаг 3d: `_after_prep`); документ вместо оплаты («payment link/details»,
        «перевод договора»); «есть/имеется» без кассы/учёта/счёта/«ваша оплата»; подлежащее — залог/депозит (формы 3b и
        семейства 3d); получатель суммы — клиент (семейства 3d). Шаг 3e: совпадение четвёртого прохода судит ещё и
        контекст сверки (`_ctx`): `asked` — входящее клиента об оплате (`pay_asked`), `sums` — известные денежные суммы
        (`pay_sums`), `hold` — ответ сам говорит, что оплата не видна или проверяется (`unsettled`)."""
        head = s[:m.start()]
        # шаг 3d: причинный союз без запятой («…because / now that your payment has been received», «…ведь оплата
        # получена») открывает свою клаузу — будущее и отрицание ГЛАВНОЙ части утверждение придаточного не снимают
        a = max([x.end() for x in _PAY_CUT.finditer(head)] + [x.end() for x in K._SENTENCE.finditer(head)]
                + [x.end() for x in _PC_CAUSE.finditer(head)] + [0])
        e = m.end()
        we = e + len(re.match(r"\w*", s[e:]).group(0))             # конец последнего слова совпадения
        last = re.search(r"[^\W\d_]+$", s[a:we])
        # (у четвёртого прохода сказуемое задано целыми словами — «подтверждаем получение» основой другого слова не бывает)
        if rx is not _PAY_CTX and last is not None and _PC_WORD.fullmatch(last.group(0)):
            again = _PC_AGAIN.match(s, we)                         # настоящее сказуемое дальше в той же клаузе
            if again is None:
                return PC_WORD
            e = we = again.end()
        gd = m.groupdict()
        # шаг 3e: собственное «нет / не / no» семейства «долга нет» и связка краткого подтверждения («can confirm») —
        # часть САМОГО утверждения: отрицание и долженствование судятся по тексту `t`, где эти группы закрыты пробелами
        # (у прежних проходов таких групп нет — `t` тот же текст)
        t = s
        for k in _PC_OWN:
            if gd.get(k):
                t = t[:m.start(k)] + " " * (m.end(k) - m.start(k)) + t[m.end(k):]
        clause = t[a:e]
        end = _PAY_END.search(s, e)
        if _PAY_NOT.search(clause):
            return PC_NOT
        if _PAY_LATER.search(clause):
            return PC_LATER
        if end is not None and end.group(0) == "?" and not _PAY_CUT.search(s[e:end.start()]):
            return PC_ASKED
        if rx is _PAY_CTX:                                         # шаг 3e: семейства контекста сверки
            why = _PayClaim._ctx(s, m, gd, a, asked, sums, hold)
            if why != PC_CLAIM:
                return why
        # шаг 3d (R1а): долженствование — при СВОЁМ сказуемом, а не где угодно в клаузе до него
        ws = we - len(re.search(r"[^\W\d_]*$", s[a:we]).group(0))    # начало последнего слова совпадения
        if _PC_PURPOSE.search(s, a, we) or [1 for x in _PF_MUST.finditer(t, a, ws)
                                            if _PayClaim._governs(t, x.start(), x.end(), ws)]:
            return PC_MUST
        after = re.match(r"\s+([^\W\d_]+)", s[we:])
        if after is not None and _PF_MUST.fullmatch(after.group(1)):
            nxt = [w for w in re.findall(r"[^\W\d_]+", s[we + after.end():]) if not _PC_SKIP.fullmatch(w)][:1]
            if _PC_FUT.fullmatch(after.group(1)) or [1 for w in nxt if _PC_AUX.fullmatch(w)]:
                return PC_MUST
        forms = rx is not _PAY_AFFIRM
        spans = [m.span(k) for k in _PC_SUBJ if gd.get(k)]
        if not spans and not forms:
            spans = [x.span() for x in _PC_NOUN.finditer(s, m.start(), we)]
        # шаг 3d (R1б): предлог судится у КАЖДОГО слова оплаты совпадения; свободное (не после предлога) — предмет
        preds = [gd[k] for k in _PC_PREDS if gd.get(k)] + [s[ws:we]]
        free = [sp for sp in spans if not _PayClaim._after_prep(s, a, sp[0], forms, preds)]
        if spans and not free:
            return PC_PREP
        for n0, n1 in free[:1]:
            n1 += len(re.match(r"\w*", s[n1:]).group(0))
            if (re.fullmatch(_PF_EN_NOUN, s[n0:n1], re.I) and _PF_EN_NEXT.match(s[n1:])) or \
                    (s[n0:n1].lower().startswith("перевод") and _PF_TRANSL_NEXT.match(s[n1:])):
                return PC_NEXT
        stop = [x.start() for x in (_PAY_CUT.search(s, e), _PAY_END.search(s, e)) if x is not None]
        wide = s[a:min(stop) if stop else len(s)]                  # клауза совпадения до разрыва/конца предложения
        # шаг 3e: «оплата есть» без кассы — утверждение, только когда входящее клиента об оплате («Да, оплата есть.»), а
        # клауза не о СПОСОБЕ оплаты («есть оплата картой и наличными»)
        if _PF_EXIST.fullmatch(gd.get("v1") or gd.get("v3") or "") and not _PF_HELD.search(wide) \
                and not (asked and not hold and _PF_METHOD.search(wide) is None):
            return PC_EXIST
        dep = _PF_DEP.search(wide) if forms else None
        if dep is not None:
            rent = _PF_RENT.search(wide)
            if rent is None or dep.start() < rent.start():
                return PC_DEP
        # шаг 3d (R3): получатель суммы — клиент («вы получили 210 бат») — не наше подтверждение; шаг 3e: у суммы или
        # числа ПЕРЕД сказуемым («вы 7790 получили обратно», «вы 210 бат получили») получатель стоит перед ними — клауза
        # читается до них («Thank you 7790 received» — благодарность, а не получатель)
        lead = min([m.start(k) for k in _PC_LEAD if gd.get(k)] + [len(s)])
        for k in _PC_RCPT:
            if gd.get(k):
                pre = s[a:min(m.start(k), lead)]
                if _PC_YOU.search(pre) and not (lead < m.start(k) and _PC_THANK.search(pre)):
                    return PC_THEIR
        return PC_CLAIM

    @staticmethod
    def _governs(s, m0, m1, ws):
        """Шаг 3d (R1а): управляет ли слово долженствования s[m0:m1] сказуемым совпадения (его последнее слово начинается
        у `ws`). Да — между ними только связка и обстоятельства («должна быть получена», «must be received», «требует
        подтверждения») либо глагол проверки или ожидания («нужно проверить что оплата прошла»). Нет — у слова
        долженствования свой глагол или дальше придаточное: «should know that …», «need to mention the payment is …»,
        «надо сказать что …», «должна была поступить вчера и поступила»."""
        b = s[m1:ws]
        if _PC_VERIFY.search(b):
            return True
        if _PC_THAT.search(b):
            return False
        if re.match(r"[a-z]", s[m0:m1], re.I):                     # английское: за модальным — связка или другой глагол
            own = [w for w in re.findall(r"[^\W\d_]+", b) if not _PC_SKIP.fullmatch(w)][:2]
            return len(own) == 0 or len([w for w in own if _PC_AUX.fullmatch(w)]) > 0
        return len([w for w in _PC_INF.findall(b) if not _PC_INF_NOT.fullmatch(w)]) == 0

    @staticmethod
    def _after_prep(s, a, n0, forms, preds):
        """Шаг 3d (R1б): стоит ли предмет (начало `n0`) после предлога так, что он НЕ то, что получено. Предлог цели
        («на», «для», for) — только при слове документа или запроса перед ним; предлог времени и условия («после», «до»,
        «перед», «без», without) — да, кроме «после оплаты» с прошедшим сказуемым получения; прочие предлоги — только у
        форм с предметом в именительном или винительном падеже (`forms`), как было. Шаг 3e: предлог, который управляет
        не суммой, а словом ПРИ ней («за АРЕНДУ 7790 получили», «по оплате 7790 бат получили»), снимает утверждение тоже
        только при слове документа перед ним («счёт за аренду 7790 бат получили»)."""
        before = re.findall(r"[^\W\d_]+", s[a:n0])
        of = 0                                                     # слов при сумме между предлогом и ней («за АРЕНДУ 7790»)
        while before and (_PF_DET.fullmatch(before[-1]) or (s[n0:n0 + 1].isdigit() and _PC_OF.fullmatch(before[-1]))):
            of += len([1 for w in (before.pop(),) if _PF_DET.fullmatch(w) is None])
        prep = before[-1].lower() if before else ""
        doc = len(before) > 1 and bool(_PC_DOC.fullmatch(before[-2]))
        if _PC_PREP_GOAL.fullmatch(prep):
            return doc
        if _PC_PREP_TIME.fullmatch(prep):
            return not (prep == "после" and [1 for p in preds if _PC_PAST.fullmatch(p)])
        return bool(forms and _PF_PREP.fullmatch(prep) and (doc or of == 0))

    @staticmethod
    def _ctx(s, m, gd, a, asked, sums, hold):
        """Шаг 3e: исход совпадения четвёртого прохода (`_PAY_CTX`) по КОНТЕКСТУ сверки → `PC_CLAIM` (дальше — общие
        исключения `verdict`) либо имя того, почему это не утверждение. Вопросительное предложение — вопрос.
        (1) Краткое подтверждение без предмета (шаг 3f: и ответ ЦЕЛИКОМ из согласия, одобрения, благодарности или знака —
        группа `q5`, та же дорога): без признака `asked` — `PC_NOASK`; ответ сам говорит, что оплата не видна
        или проверяется, — `PC_HOLD`; обещание проверки в том же предложении — «будущее, проверка или условие»; предмет
        назван раньше в предложении или за «да» не одни слова согласия — `PC_OTHER`. (3) Число без валюты: за кодом
        валюты — утверждение; на месте номера (модель, «байк», «№», соседняя группа цифр) — `PC_NUM`; равно известной
        денежной сумме — утверждение; иначе — только при `asked`. «Вижу N (бат)» в бумаге клиента — `PC_OTHER`.
        (2) «Долга нет»: «всё закрыто» без слова денег в предложении — только при `asked`, иначе `PC_NOMONEY`; «вы
        оплатили» в пересказе слов клиента — `PC_SAID`, при `hold` — `PC_HOLD`; речь о другой услуге без аренды раньше
        неё — `PC_ITEM`; «ничего не должны» как правило о сроке оплаты — «будущее…», о нас самих — `PC_OTHER`."""
        b0 = max([x.end() for x in K._SENTENCE.finditer(s[:m.start()])] + [0])
        fin = _PAY_END.search(s, m.end())
        sent = s[b0:len(s) if fin is None else fin.end()]            # предложение совпадения со знаком конца
        if sent.rstrip().endswith("?"):
            return PC_ASKED

        def brief(start):
            """Дорога краткого подтверждения без предмета (сказуемое или согласие начинается у `start`)."""
            if not asked:
                return PC_NOASK
            if hold:
                return PC_HOLD
            if _PQ_CHECK.search(sent):                               # «Получили, договор проверим завтра»
                return PC_LATER
            if _PQ_THING.search(s[b0:start]):                        # предмет назван раньше в том же предложении
                return PC_OTHER
            return PC_CLAIM
        if [1 for k in _PC_BARE if gd.get(k)]:
            why = brief(m.start())
            if why == PC_CLAIM and gd.get("q3") \
                    and _PQ_ONLY.fullmatch(s[m.end("q3"):len(s) if fin is None else fin.start()]) is None:
                return PC_OTHER
            return why
        cut = [x.start() for x in (_PAY_CUT.search(s, m.end()), fin) if x is not None]
        wide = s[a:min(cut) if cut else len(s)]                      # клауза совпадения до разрыва или конца предложения
        if (gd.get("r8") or gd.get("r9")) and _PN_INDOC.search(wide):
            return PC_OTHER                                          # «вижу 7790 бат в вашем чеке» — видна бумага, не деньги
        nums = [k for k in _PC_NUMS if gd.get(k)]
        if nums:
            n0, n1 = m.span(nums[0])
            left = s[a:n0]
            if _PN_CODE.search(left):                                # «THB 5000 received» — код валюты ПЕРЕД числом
                return PC_CLAIM
            if _PN_MODEL.search(left) or _PN_WORD.search(left) or re.search(r"[\d+]\s*$", left) \
                    or re.match(r"\s*\d", s[n1:]):
                # шаг 3f: число на месте номера перед ТИРЕ («NMAX 90101 — получили.») — сказуемое за тире остаётся
                # прежним кратким подтверждением: при входящем об оплате его судит та же дорога, что и до шага
                return brief(m.start("r10")) if gd.get("b7") and asked else PC_NUM
            if int(re.sub(r"\D", "", gd[nums[0]])) in set(sums or ()):
                return PC_CLAIM
            if not asked:
                return PC_NUM
            return PC_HOLD if hold else PC_CLAIM
        if gd.get("d6") and _PD_MONEY.search(sent) is None:           # «всё закрыто» — о деньгах ли?
            if not asked:
                return PC_NOMONEY
            if hold:
                return PC_HOLD
        if gd.get("u1") or gd.get("u2"):                             # «вы всё оплатили», «you've paid»
            if _PU_SAID.search(sent):                                # «по вашим словам, вы оплатили вчера»
                return PC_SAID
            if hold:                                                 # «вы оплатили, но в кассе оплату пока не вижу»
                return PC_HOLD
        item = _PD_ITEM.search(wide)
        if item is not None:
            rent = _PF_RENT.search(wide)
            if rent is None or item.start() < rent.start():
                return PC_ITEM
        # условие ПОСЛЕ утверждения в том же предложении: «долга нет, если оплатите сегодня», «доплата не нужна, если
        # вернёте вовремя» — правило, а не состояние расчётов
        if _PD_IF.search(s, m.end(), len(s) if fin is None else fin.start()):
            return PC_LATER
        if gd.get("x4") or gd.get("x5") or gd.get("x10") or gd.get("x11"):   # «ничего не должны», «nothing owed»
            if _PD_WHEN.search(wide):                  # правило о СРОКЕ оплаты: «сейчас вы ничего не должны — оплата при
                return PC_LATER                        # получении», «nothing is due until pickup»
            if gd.get("x4") and _PD_WE.search(s[a:m.start()]):
                return PC_OTHER                        # «мы вам ничего не должны» — не об оплате клиентом
        return PC_CLAIM

    @staticmethod
    def unsettled(text):
        """Шаг 3e: говорит ли ответ САМ, что оплата не видна, не получена или проверяется, — тогда краткое «получили» в
        нём не об оплате. Да — у совпадения прежних проходов исход «отрицание» либо «будущее, проверка или условие»
        («оплату пока не вижу», «как только оплата поступит, подтвердим»); в ответе есть обещание проверки — при слове
        оплаты («оплату проверит коллега», «он сверит поступления») или без иного предмета («Проверим и ответим.»; «Договор
        проверим и пришлём» — проверка договора, не оплаты); отрицание при слове кассы или видимости («В кассе пока не
        видим.»)."""
        s = str(text or "")
        for rx in (_PAY_AFFIRM, _PAY_FORMS, _PAY_SUMS):
            for m in rx.finditer(s):
                if _PayClaim.verdict(s, rx, m) in (PC_NOT, PC_LATER):
                    return True
        for sent in K._SENTENCE.split(s):
            calm = _PQ_CALM.sub(" ", sent)
            # обещание проверки: при слове оплаты либо без иного предмета («Проверим и ответим.», но не «Договор проверим»)
            if _PQ_CHECK.search(calm) and (_PQ_PAYWORD.search(calm) or _PQ_PROOF.search(calm)
                                           or _PQ_TOPIC.search(calm) is None):
                return True
            if _PAY_NOT.search(calm) and _PQ_SEEN.search(calm):      # «В кассе пока не видим.»
                return True
        return False

    def explain(self, text, asked=None, sums=None, hold=None):
        """Названные исходы ВСЕХ совпадений текста → [(совпадение, исход)]: почему фраза утверждение или почему нет.
        Шаг 3e: `asked`, `sums` — контекст сверки (`verdict`); не заданы — контекст экземпляра; `hold` не задан —
        считается по этому тексту (`unsettled`)."""
        s = str(text or "")
        asked = self.asked if asked is None else asked
        sums = self.sums if sums is None else sums
        if hold is None:
            hold = self.unsettled(s)
        return [(m.group(0), self.verdict(s, rx, m, asked, sums, hold)) for rx, m in self._matches(s)]

    def search(self, text, asked=None, sums=None, hold=None):
        s = str(text or "")
        asked = self.asked if asked is None else asked
        sums = self.sums if sums is None else sums
        if hold is None:
            hold = self.unsettled(s)
        for rx, m in self._matches(s):
            if self.verdict(s, rx, m, asked, sums, hold) == PC_CLAIM:
                return m
        return None


_PAY_CLAIM = _PayClaim()
_DEP_CLAIM = re.compile(r"(?:залог|депозит)\w*\s+(?:\S+\s+){0,3}(?:получен|принят|внес|оплачен)|"
                        r"deposit\s+(?:is\s+|has\s+been\s+)?(?:received|paid)", re.I)
_REFUND_PROMISE = re.compile(r"\bверн[её]м\b|\bвернут\b|\bвозвратим\b|will\s+(?:refund|return)|"
                             r"we'?ll\s+(?:refund|return)", re.I)
# «сдача» — деньги сдачи; «сдача байка» — возврат техники, не деньги
_CHANGE = re.compile(r"\bсдач\w*\b(?!\s+(?:байк|мотоцикл|скутер|транспорт))|\b(?:your|the|small)\s+change\b", re.I)
_CHANGE_OK = re.compile(r"в\s+конце|с\s+возврат\w*\s+залог|вместе\s+с\s+(?:возврат\w*\s+)?залог|"
                        r"at\s+the\s+end|with\s+the\s+deposit", re.I)


def pay_sums(facts, handed=()):
    """Известные ДЕНЕЖНЫЕ суммы сверки (K3-FIX шаг 3e, п.3) → множество целых: итог («к оплате») и цена аренды, суммы
    строк кассы (любой роли и привязки), суммы, названные в переписке (факт history), и переданные наличные со слов
    клиента (`cash_said`). С ними сверяется число БЕЗ валюты при сказуемом получения («Да, 7790 получили.»): номер байка,
    заказа или иное число денежной суммой не станет. Это не опора подтверждения (она — `pay_backing`), а лишь признак
    «число — деньги»."""
    out = set()
    for f in facts:
        vals = [f.get(k) for k in ("to_pay", "price", "amount")] + list(f.get("amounts") or ())
        out.update(abs(int(round(v))) for v in vals if _num(v))
    out.update(abs(int(round(v))) for v in handed or () if _num(v))
    out.discard(0)
    return out


def pay_claimed(text, asked=False, sums=()):
    """Суммы, которые текст называет полученной оплатой (T4BFACTS0410): числа предложений с подтверждением оплаты —
    в батах и голые, как в `money_claims` (имя модели, дни, км, проценты суммами не считаются). Шаг 3e: `asked`, `sums`
    — контекст сверки того же определения (`_PayClaim.verdict`); «ответ сам говорит: оплата проверяется» судится по
    ВСЕМУ тексту, а не по одному предложению; предложение судится со СВОИМ знаком конца — вопрос («Вы 7790 получили?»)
    сумм полученной оплаты не называет."""
    out = set()
    s = str(text or "")
    hold = _PAY_CLAIM.unsettled(s)
    pos = 0
    for brk in list(K._SENTENCE.finditer(s)) + [None]:
        sent, mark = (s[pos:], "") if brk is None else (s[pos:brk.start()], brk.group(0))
        pos = len(s) if brk is None else brk.end()
        if not _PAY_CLAIM.search(sent + mark, asked, sums, hold):
            continue
        out.update(abs(int(round(v))) for v in K.thb_amounts(sent))
        for m in _BARE.finditer(sent):
            if not _MODEL_BEFORE.search(sent[:m.start()]):
                out.add(int(re.sub(r"\D", "", m.group(1))))
    out.discard(0)                                    # шаг 3e: «остаток к оплате — 0 бат» — ноль не сумма оплаты
    return out


def pay_backing(facts):
    """Чем подтверждается сумма полученной оплаты (T4BFACTS0410): деньги АРЕНДЫ ОБРАЩЕНИЯ — её строки кассы и их итоги,
    разность с её ценой, сама цена. Строки других аренд и «не привязано» опорой подтверждения не бывают."""
    bk = rental_of(facts)
    rows = cash_split(facts)[0]
    figures = calc(facts)
    # K3-FIX F3: опора подтверждения — деньги ВАЛЮТЫ АРЕНДЫ (сумма и валюта совпадают); строки и итоги другой валюты —
    # не опора; валюта аренды неизвестна — сравнивать не с чем (без аренды обращения — как было)
    cur = rent_currency(facts, bk) if bk is not None else None
    rows = [f for f in rows if bk is None or str(f.get("currency") or "").upper() == cur]
    out = {abs(int(round(f["amount"]))) for f in rows}
    out.update(abs(int(round(v))) for k, v in figures["sums"].items() if bk is None or k.endswith(" %s" % cur))
    out.update(abs(int(round(d["value"]))) for d in figures["diffs"] if bk is None or d["currency"] == cur)
    out.update(abs(int(round(f["price"]))) for f in facts if f["kind"] == "rental" and bk is not None
               and str(f.get("booking_id") or "") == bk and isinstance(f.get("price"), (int, float)))
    return out


def money_roles(text, facts, asked=False, handed=()):
    """Денежные роли текста против принятых фактов → [(слова причины, что)]: оплата аренды ≠ залог, записанный
    возврат запрещает «вернём», сдача — «в конце, с возвратом залога». Сумма подтверждения и залог — деньгами аренды
    обращения (T4BFACTS0410): чужая оплата подтверждением не бывает. Шаг 3e: `asked` — входящее клиента об оплате
    (`pay_asked`): краткое «Да, получили.» судится как утверждение оплаты на тех же основаниях; `handed` — суммы со слов
    клиента (`cash_said`): вместе с суммами фактов (`pay_sums`) они отличают денежное число от номера."""
    s = str(text or "")
    out = []
    bound = cash_split(facts)[0]
    paid, why = pay_verdict(facts)
    sums = pay_sums(facts, handed)
    # шаг 3e: то же ОДНО определение — с контекстом сверки этого черновика (вопрос клиента и суммы фактов); имя прежнее,
    # чтобы две проверки ниже остались дословно прежними (их строки правят мутанты наборов T4BFACTS0410)
    _PAY_CLAIM = _PayClaim(asked, sums)
    if _PAY_CLAIM.search(s) and not paid:
        # K3-FIX F3: причина словами — та, что вынес `pay_verdict` (в т.ч. «валюта не совпала» / «валюта неизвестна»)
        out.append((PAY_WORDS, "текст подтверждает оплату без кассы и второго источника: %s" % why))
    elif _PAY_CLAIM.search(s):
        alien = sorted(pay_claimed(s, asked, sums) - pay_backing(facts))
        if alien:
            out.append((PAY_WORDS, "текст подтверждает оплату %s, у аренды обращения %s такой суммы нет"
                        % (", ".join(str(v) for v in alien), rental_of(facts))))
    if _DEP_CLAIM.search(s) and not any(f["kind"] == "cash" and f["role"] == R_DEPOSIT for f in bound):
        out.append((ROLE_WORDS, "текст говорит о залоге, в кассе строки залога нет (оплата аренды ≠ залог)"))
    if _REFUND_PROMISE.search(s) and any(f["kind"] == "cash" and f["role"] == R_REFUND for f in facts):
        out.append((ROLE_WORDS, "возврат уже записан в кассе — «вернём» запрещено"))
    if _CHANGE.search(s) and not _CHANGE_OK.search(s):
        out.append((ROLE_WORDS, "сдача — только «в конце, с возвратом залога»"))
    return out


_roles = money_roles          # шаг 3e: `judge` зовёт то же определение под прежним именем, но с контекстом сверки


# ------------------------------- открытая тема оплаты (K3-FIX шаг 3g) -------------------------------
# Решение круга 3g (блокеры D1 и D2 независимой проверки 3d+3e+3f). На входящем БЕЗ слов общей причины оплаты
# (`K.handoff`, выражение R_MONEY) единственной защитой кода оставался словарь утверждений N4, а класса он не закрывает:
# «Деньги пришли?» — «Да, с оплатой всё хорошо.»; «Проверили?» — «Да, всё пришло.»; «Sent!» — «Спасибо, получили!».
# ПРАВИЛО КЛАССА: тема оплаты ОТКРЫТА и оплата кодом НЕ подтверждена (`pay_verdict`; фактов нет, сверка не звалась или
# не завершена — тоже не подтверждена) ⇒ причина кода «нужен человек» ВСЕГДА, при любом тексте ответа. Словари
# утверждений (`_PAY_AFFIRM`, `_PAY_FORMS`, `_PAY_SUMS`, `_PAY_CTX`) и `pay_asked` не меняются ни на слово: тема считается
# ТЕМИ ЖЕ определениями на более широком входе. ТЕМА — СОСТОЯНИЕ ПЕРЕПИСКИ, а не окно в один обмен (вторая часть шага:
# при окне тема терялась на любом промежуточном ответе вне словаря — «Still checking», «Спасибо, минуту», обмен о шлеме).
# ОТКРЫВАЕТ тему:
#   (1) хвост — неотвеченные сообщения клиента: `pay_asked`;
#   (2) блок сообщений клиента в истории (перед нашим последним ответом и раньше): `pay_asked`;
#   (3) наш ответ в истории (не автоприветствие) — об оплате: обещал проверку или сказал «не видим» (`unsettled`),
#       подтвердил оплату (`_PAY_CLAIM.search` без контекста сверки) либо назвал оплату предметом — существующим словом
#       оплаты (`_PQ_PAYWORD` либо группа оплаты выражения R_MONEY, `K.money_labels`): способ, реквизиты, сумма к оплате.
# ДЕРЖИТ: открытая тема остаётся открытой для всех следующих сообщений, какими бы они ни были (ожидание, реплика без
# слов оплаты, обмен о другом предмете), пока её не закроет положительное событие. ЗАКРЫВАЮТ тему ровно два события:
#   (а) НАШЕ более раннее подтверждение оплаты в переписке (`_PAY_CLAIM.search` без контекста): вопрос решён — сообщения
#       клиента и наши ответы ДО него тему больше не открывают. Подтверждение, которое и есть наш ПОСЛЕДНИЙ ответ перед
#       хвостом, тему по-прежнему открывает (часть (3): его ещё не проверил код);
#   (б) ДАВНОСТЬ: открывающее сообщение старше `PAY_TOPIC_HOURS` относительно времени суждения; у сообщения нет времени —
#       оно считается свежим (сомнение — в сторону причины). Обмен ПЕРЕД хвостом (блок клиента и наш последний ответ)
#       давностью не судится — он открывает тему, как в первой части шага: вторая часть причин только добавляет.
# Новое сообщение клиента об оплате или новый наш ответ об оплате ПОСЛЕ закрывающего события открывают тему заново:
# история судится от хвоста назад обмен за обменом (наш ответ и блок клиента перед ним), решает первое найденное событие.
# Исключения «ответ сам говорит: проверяется / не видна» у этой причины НЕТ (осознанно): без причины проверку никто из
# людей не начнёт, и «проверим» останется пустым обещанием. Причина называет себя СУЩЕСТВУЮЩИМИ словами `K.MONEY_WORDS`
# (теми же, что у общей причины по входящему, — слияние дубля не даёт): тему открыл клиент — смысл его слов
# (`K.payment_mode`: заявил оплату — «…поступление не проверено», спросил — «вопрос об оплате»), открыл наш ответ —
# нейтральное «оплата». `PAY_WORDS` этим правилом не ставится: её по-прежнему ставит только N4 (`money_roles`). У каждой
# ветки — ИМЯ исхода (пустым не бывает). ГРАНИЦА: код видит тему, только если в переписке за срок давности хотя бы одна
# сторона назвала оплату существующим словом (и после этого мы её в переписке не подтверждали).
PAY_TOPIC_HOURS = 168          # давность темы: открывающее сообщение старше 7 суток тему не открывает
PT_TAIL = "тема оплаты открыта: клиент сейчас сообщает об оплате или спрашивает о поступлении"
PT_PREV = "тема оплаты открыта: клиент сообщал об оплате или спрашивал о поступлении перед нашим последним ответом"
PT_OURS = "тема оплаты открыта: наш последний ответ — об оплате"
PT_BACK = "тема оплаты открыта раньше, чем один обмен назад: клиент сообщал об оплате или спрашивал о поступлении"
PT_BACK_OURS = "тема оплаты открыта раньше, чем один обмен назад: наш ответ был об оплате"
PT_SHUT = "тема оплаты закрыта: после неё мы подтвердили оплату в переписке"
PT_OLD = "тема оплаты закрыта давностью: об оплате говорили больше 168 ч назад"
PT_NONE = "тема оплаты не открыта"
PT_PAID = "тема оплаты открыта, оплата подтверждена кодом — причины класса нет"
PT_OPEN = (PT_TAIL, PT_PREV, PT_OURS, PT_BACK, PT_BACK_OURS)
PT_CLOSED = (PT_SHUT, PT_OLD)


def _topic_ours(text):
    """Наш ответ и тема оплаты (K3-FIX шаг 3g) → (подтвердил оплату, об оплате). Подтвердил — `_PAY_CLAIM.search` без
    контекста сверки. Об оплате (часть (3) определения темы) — подтвердил, обещал проверку или сказал «не видим»
    (`unsettled`) либо назвал оплату предметом: слово оплаты `_PQ_PAYWORD` или группа оплаты выражения R_MONEY."""
    s = str(text or "")
    claim = _PAY_CLAIM.search(s) is not None
    named = _PQ_PAYWORD.search(s) is not None or bool(
        [key for key, _words in K.money_labels(s, trusted=False) if K._FAMILY.get(key, key) == K.MONEY_PAYMENT])
    return claim, bool(named or _PayClaim.unsettled(s) or claim)


def pay_topic(tail="", prev="", ours="", blocks=None, now=None):
    """ОДНО определение «тема оплаты открыта» (K3-FIX шаг 3g) → (ИМЯ исхода, слова причины). `tail` — неотвеченные
    сообщения клиента. `blocks` — история ПЕРЕД хвостом блоками, от нашего последнего ответа назад: [(кто, текст, время |
    None)], кто — «мы» | «клиент» (собирает адаптер, `ModelAdapter._blocks`); `now` — время суждения. Блоки не заданы —
    история из одного обмена без времени: `prev` — блок клиента перед нашим последним ответом, `ours` — сам ответ.
    Тему открывает первое событие от хвоста назад: хвост — `PT_TAIL`; обмен перед хвостом — `PT_PREV` (блок клиента) либо
    `PT_OURS` (наш последний ответ об оплате); обмен раньше — `PT_BACK` либо `PT_BACK_OURS`. Закрывают: наше более
    раннее подтверждение оплаты (не последний ответ) — `PT_SHUT`; давность обмена раньше предыдущего (`PAY_TOPIC_HOURS`
    от `now`; времени нет — сообщение свежее) — `PT_OLD`, если открывающее сообщение есть, но старше предела. Ни одного
    события — `PT_NONE`.
    Слова — из `K.MONEY_WORDS`: открыл клиент — смысл его слов (`K.payment_mode`), открыл наш ответ — нейтральное
    «оплата» (у закрытой и не открытой темы — оно же: причиной слова не становятся)."""
    if pay_asked(tail):
        return PT_TAIL, K.MONEY_WORDS[K.payment_mode(tail)]
    plain = K.MONEY_WORDS[K.MONEY_PAYMENT_UNCLEAR]
    if blocks is None:
        blocks = (("мы", ours, None), ("клиент", prev, None))
    seq = [tuple(b) for b in blocks]
    edge = None if now is None else now - PAY_TOPIC_HOURS * 3600
    old, first, i = False, True, 0
    while i < len(seq):
        mine = seq[i] if seq[i][0] == "мы" else None            # обмен: наш ответ и блок клиента перед ним
        j = i + (mine is not None)
        theirs = seq[j] if j < len(seq) and seq[j][0] == "клиент" else None
        claim, about = _topic_ours(mine[1]) if mine is not None else (False, False)
        if claim and not first:                                 # (а) наше более раннее подтверждение: до него — закрыто
            return (PT_OLD if old else PT_SHUT), plain
        if theirs is not None and pay_asked(theirs[1]):
            if first or not theirs[2] or edge is None or theirs[2] >= edge:
                return (PT_PREV if first else PT_BACK), K.MONEY_WORDS[K.payment_mode(theirs[1])]
            old = True                                          # (б) открывающее сообщение есть, но старше предела
        if about:
            if first or not mine[2] or edge is None or mine[2] >= edge:
                return (PT_OURS if first else PT_BACK_OURS), plain
            old = True
        i, first = max(j + (theirs is not None), i + 1), False
    return (PT_OLD if old else PT_NONE), plain


def topic_reason(topic, facts):
    """Правило класса (K3-FIX шаг 3g) → (ИМЯ исхода, [слова причины кода «нужен человек»]). `topic` — исход `pay_topic`,
    `facts` — принятые факты сверки (`sift`; у незавершённой сверки — пусто). Тема открыта и `pay_verdict(facts)` оплату
    не подтверждает — причина есть ВСЕГДА (текст ответа не судится вовсе); подтверждает (касса аренды обращения и второй
    источник) — `PT_PAID`, причины нет; тема закрыта (нашим подтверждением в переписке, давностью) — её имя, причины
    нет; тема не открыта — `PT_NONE`, причины нет."""
    pair = tuple(topic or ())
    name, words = pair[:2] if len(pair) >= 2 else (PT_NONE, "")
    if name in PT_CLOSED:
        return name, []
    if name not in PT_OPEN:
        return PT_NONE, []
    if pay_verdict(facts)[0]:
        return PT_PAID, []
    return name, [words]


def conflicts(facts, figures):
    out = []
    for d in figures["diffs"]:
        if d["value"] != 0:
            out.append("%s: %s %s" % (d["what"], d["value"], d["currency"]))
    bikes = {plate_of(f.get("bike")) or str(f.get("bike") or "").strip().lower()      # по номеру, как дверь
             for f in facts if f["kind"] in ("rental", "contract")}
    bikes.discard("")
    if len(bikes) > 1:
        out.append("байк аренды и договора расходится")
    return out


# ------------------------------- журнал -------------------------------

class Journal:
    """Журнал одного черновика: вызовы (имя, вход без ПД, источник, время, итог), принятые факты, конфликты,
    отказы. Текста модели и её рассуждений здесь нет — только то, что делал код."""

    def __init__(self, number_tail=""):
        self.calls, self.facts, self.conflicts, self.refusals = [], [], [], []
        self.unbound = []                                 # наличность не аренды обращения (T4BFACTS0410)
        self.asked = False                                # шаг 3e: входящее клиента — об оплате (`pay_asked`)
        self.number_tail = number_tail

    def call(self, i, tool, args, res, sec):
        self.calls.append({"n": i, "tool": tool, "in": masked(args), "source": res["source"], "at": res["at"],
                           "outcome": res["outcome"], "reason": res["reason"][:200], "sec": round(sec, 2),
                           # K3-FIX3: время данных (у снимка — время снимка) и поиск, который поставил КОД (договор)
                           "read_at": res.get("read_at"), "query": res.get("query") or ""})
        if res["outcome"] != FACT:
            self.refusals.append("%s: %s (%s)" % (tool, res["outcome"], res["reason"][:160]))

    def lines(self):
        head = "сверка …%s: вызовов %d, фактов %d, конфликтов %d, отказов %d" % (
            self.number_tail, len(self.calls), len(self.facts), len(self.conflicts), len(self.refusals))
        out = [head]
        out += ["  вызов %(n)d %(tool)s %(in)s → %(outcome)s · %(source)s · %(sec)sс · %(reason)s" % c
                for c in self.calls]
        out += ["  факт %s" % json.dumps(_fact_ref(f), ensure_ascii=False) for f in self.facts]
        out += ["  %s, в сумму не входит: %s" % (UNBOUND_WORDS, json.dumps(u, ensure_ascii=False))
                for u in self.unbound]
        out += ["  конфликт %s" % c for c in self.conflicts]
        out += ["  отказ %s" % r for r in self.refusals]
        return out


def _fact_ref(f):
    keep = ("kind", "row", "msg_id", "link", "at", "booking_id", "role", "amount", "currency", "signed_at",
            "pdf_id", "id", "size", "sha256", "items", "rule_0310")
    return {k: f[k] for k in keep if k in f and f[k] is not None}


# ------------------------------- цикл -------------------------------

TOOLS_BLOCK = """ИНСТРУМЕНТЫ (только чтение). Прежде чем писать о деньгах, оплате, залоге, аренде или договоре — проверь.
Один ответ = РОВНО один JSON. Вызов инструмента: {"tool": "<имя>", "args": {…}}. Имена и вход:
history {} — переписка; rental {} — аренда по номеру клиента; cash {"bike": "...", "booking_id": "...", "date_from": "ГГГГ-ММ-ДД", "date_to": "ГГГГ-ММ-ДД"} — касса;
contract {} — подписанный договор ЭТОГО обращения: номер клиента и срок аренды код подставит сам, фильтры не нужны (чужой номер, байк или период — отказ с причиной); contract_pdf {"file_id": "<pdf_id из факта contract>"} — метаданные PDF;
delivery {} — доставка; rules {} — правила владельца.
Не больше %d вызовов. Когда хватит — итоговый черновик обычным JSON ответа (text, handoff, lang, why).
Суммы, разности и сдачу не считай сам — их посчитает код (блок «РАСЧЁТ КОДА»). Оплату не подтверждай без кассы и договора."""


def parse_turn(raw):
    """Ответ модели → ("tool", имя, args) | ("final", None, None) | None (не JSON)."""
    s = str(raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
    try:
        data = json.loads(s)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict) and isinstance(data.get("tool"), str):
        args = data.get("args") if isinstance(data.get("args"), dict) else {}
        return ("tool", data["tool"].strip(), args)
    return ("final", None, None) if isinstance(data, dict) else None


def render(results):
    out = []
    for i, r in enumerate(results, 1):
        out.append("%d) %s → %s · %s · %s · окно %s%s" % (
            i, r["tool"], r["outcome"], r["source"] or "—", r["ref"] or "—", r["window"] or "—",
            (" · " + r["reason"]) if r["reason"] else ""))
        for f in r["facts"][:10] if r["outcome"] == FACT else []:
            out.append("   %s" % json.dumps(_fact_ref(f), ensure_ascii=False))
    return "РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ (код; «не факт» — не опора):\n" + "\n".join(out) if out else ""


def run(call, system, user, doors, number="", clock=time.time, fresh=None, spend=None,
        max_calls=MAX_CALLS, max_sec=MAX_SEC, reserve=FALLBACK_SEC, handed=None, asked=None):
    """Сверка одного черновика → {state, raw, usage, results, journal, calls, doors, sec, deadline, asked}.
    state: DONE — модель дала итог; OVER — предел вызовов или секунд, итога нет; ABORTED — новое входящее.
    Общий предел (AGENTDEDUP0410): `deadline` = t0 + max_sec на ВСЮ сверку с запасным вызовом; новых вызовов модели и
    дверей сверка не начинает после deadline − reserve (остаток — запасному вызову вызывающего). `handed` (K3-FIX3 п.2)
    — суммы переданных наличных со слов клиента (`cash_said`): к каждому ходу модели код прикладывает свой расчёт сдачи
    по уже принятым фактам (`change_block`); нет сумм — запрос прежний байт-в-байт. `asked` (шаг 3e) — признак «входящее
    клиента — об оплате» (`pay_asked`): сверка только ЗАПИСЫВАЕТ его в журнал и итог (судит по нему `judge`); запрос
    модели от него не зависит."""
    t0 = clock()
    deadline = t0 + max_sec
    stop = deadline - max(0.0, min(reserve, max_sec))
    jr = Journal(re.sub(r"\D", "", str(number))[-4:])
    jr.asked = bool(asked)
    results, n = [], {"calls": 0, "doors": 0}

    def may_call():
        return clock() < stop

    def counted(fn):
        def door(**kw):
            n["doors"] += 1
            return fn(**kw)
        return door
    doors = {k: (counted(v) if callable(v) else v) for k, v in (doors or {}).items()}
    ctx = bind_ctx(number, doors, results, clock, may_call)
    head = (TOOLS_BLOCK % max_calls) + "\n\n" + user

    def out(state, raw=None, usage=None):
        return {"state": state, "raw": raw, "usage": usage, "results": results, "journal": jr, "calls": n["calls"],
                "doors": n["doors"], "sec": clock() - t0, "deadline": deadline, "asked": jr.asked}
    while True:
        if fresh is not None and fresh():
            return out(ABORTED)
        if n["calls"] >= max_calls or not may_call():
            return out(OVER)
        block = render(results)
        # K3-FIX3 п.2: расчёт сдачи — кодом, когда касса уже прочитана (до неё отказ «оплаты в кассе нет» был бы ложным)
        sums = change_block(results, handed) if any(r.get("tool") == "cash" for r in results) else ""
        if sums:
            block = (block + "\n\n" + sums) if block else sums
        raw, usage = call(system, head + ("\n\n" + block if block else ""))
        n["calls"] += 1
        if spend is not None:
            spend(usage)
        turn = parse_turn(raw)
        if turn is None or turn[0] == "final":
            if clock() > deadline:
                return out(OVER, usage=usage)
            return out(DONE, raw, usage)
        _, tool, args = turn
        if not may_call():                                # модель просит дверь, а времени на новый вызов нет
            return out(OVER, usage=usage)
        t1 = clock()
        res = call_tool(tool, args, doors, clock, ctx)
        results.append(res)
        jr.call(len(results), tool, args, res, clock() - t1)


def judge(text, price, results, jr, since=None, handed=(), asked=False):
    """Итоговый текст + исход цены + результаты → [слова причин] и заполненный журнал (факты, конфликты).
    Опора — отсеянное `sift` (AGENTDEDUP0410): каждый факт один раз, последняя версия, без снятых и устаревших
    (`since` — время последнего входящего клиента). `handed` (K3-FIX3 п.2) — суммы переданных наличных со слов клиента
    (`cash_said`): сдача кодом (`change_of`) кладётся в `figures["change"]` — её числа опора ответа; сдача по словам
    клиента, названная текстом, — причина `CHANGE_WORDS` (сумму подтверждает человек). `asked` (шаг 3e) — входящее
    клиента об оплате (`pay_asked`): краткое подтверждение без предмета («Да, получили.») судится как утверждение оплаты
    на тех же основаниях (`money_roles`)."""
    facts, dropped = sift(results, since)
    figures = calc(facts)
    figures["change"] = change_of(facts, handed)
    jr.asked = bool(asked)
    jr.facts = facts
    jr.unbound = [{k: v for k, v in u.items() if k != "why"} for u in figures["unbound"]]
    jr.refusals.extend(d for d in dropped if d not in jr.refusals)
    jr.conflicts = conflicts(facts, figures)
    words = []
    if money_claims(text, price, known_amounts(price, facts, figures)):
        words.append(K.MONEY_CLAIM_WORDS)
    def money_roles(text, facts):
        """Те же денежные роли (`_roles` — определение модуля) с контекстом сверки ЭТОГО черновика (шаг 3e): вопрос
        клиента и его суммы. Имя и строка вызова ниже — прежние (её правит мутант набора AGENTDEDUP0410)."""
        return _roles(text, facts, asked=bool(asked), handed=handed)

    for w, why in money_roles(text, facts):
        if w not in words:
            words.append(w)
        jr.conflicts.append(why)
    for r in results:                                     # договор не этого клиента / не этой аренды (AGENTFIX0410)
        if r["outcome"] == CONFLICT:
            jr.conflicts.append("%s: %s" % (r["tool"], r["reason"]))
            if CONTRACT_WORDS not in words:
                words.append(CONTRACT_WORDS)
    if jr.conflicts and any(c.startswith("цена аренды") or "расходится" in c for c in jr.conflicts):
        words.append(SUMS_WORDS)
    ch = figures["change"] or {}
    if (ch.get("state") == CHANGE_OK and ch.get("value") and int(round(ch["paid"])) != ch["tendered"]
            and _CHANGE.search(str(text or ""))):
        words.append(CHANGE_WORDS)                # сдача по словам клиента — эскалация, а не факт
    return words, figures
