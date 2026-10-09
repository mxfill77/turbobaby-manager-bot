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
# (`_PayClaim._form_ok`): предмет после предлога («ссылку на оплату», «вопрос про платёж») оплатой не является; «есть/
# имеется» — только при кассе/учёте/счёте или «ваша оплата» (а не «оплата картой тоже есть»); подлежащее — залог/депозит
# (без аренды раньше него) — роль залога `_DEP_CLAIM`, а не оплата аренды (новых ролей нет); долженствование и будущее
# в клаузе («должен быть проведён», «оплачено будет») — не утверждение.
_PF_NOUN_NOM = r"(?:(?:пред|до)?оплата|плат[её]ж|плат[её]жи|деньги|перевод|переводы|средства)"
_PF_NOUN_ACC = r"(?:(?:пред|до)?оплат[ау]|плат[её]ж|плат[её]жи|деньги|перевод|переводы|средства)"
_PF_PRED = (r"(?:получен[аоы]?|получил[аои]?|поступил[аои]?|пришл[ао]|пришёл|пришел|прошл[аои]|прошёл|прошел|"
            r"дошл[ао]|дошёл|дошел|зафиксирован[аоы]?|зафиксировал[аои]?|отражен[аоы]?|отражён|"
            r"отразил(?:ась|ось|ся|ись|[аои])?|учтен[аоы]?|учтён|учли|зачислен[аоы]?|зачислил[аои]?|принят[аоы]?|"
            r"принял[аои]?|внесен[аоы]?|внесён|проведен[аоы]?|проведён|записан[аоы]?|записали|подтвержден[аоы]?|"
            r"подтверждён|подтверждаю|подтверждаем|подтвердил[аои]?|видн[аоы]|виден|вижу|видим|в\s+порядке|"
            r"есть|имеется|имеются)")
_PF_EN_NOUN = r"(?:payments?|money|transfers?|funds)"
_PF_EN_PRED = (r"(?:went\s+through|gone\s+through|came\s+through|come\s+through|cleared|arrived|credited|processed|"
               r"received|confirmed|recorded|registered|reflected|showing|settled|in\s+order|all\s+good)")
_PAY_FORMS = re.compile(
    r"(?<!\w)(?P<pp>(?:пред|до)?оплачен[аоы]?)(?!\w)|"
    r"(?<!\w)(?P<pe>(?:was|were|been)\s+(?:already\s+|fully\s+)?paid|(?:already|fully|all)\s+paid|"
    r"(?:is|are)\s+(?:already\s+|fully\s+|now\s+)?paid(?=\s*(?:$|[.!?,;:…\n—–()])|\s+(?:in\s+full|for|up\s+to|until|"
    r"thank))|(?P<n5>rent|rental)\s+(?:already\s+|fully\s+)?paid)(?!\w)|"
    r"(?<!\w)(?P<n1>" + _PF_NOUN_NOM + r"|(?:пред|до)?оплату)\s+" + _W + r"{0,8}(?P<v1>" + _PF_PRED + r")(?!\w)|"
    r"(?<!\w)(?P<n2>деньги|средства|плат[её]жи|переводы)\s+" + _W + r"{0,4}(?:пришли|дошли)(?!\w)|"
    r"(?<!\w)(?P<v3>" + _PF_PRED + r")\s+" + _W + r"{0,3}(?P<n3>" + _PF_NOUN_ACC + r")(?!\w)|"
    r"(?<!\w)(?P<n4>" + _PF_EN_NOUN + r")\s+" + _W + r"{0,5}" + _PF_EN_PRED + r"(?!\w)|"
    r"(?<!\w)(?:received|got|recorded|registered|credited|confirmed|processed|cleared)\s+" + _W + r"{0,3}"
    r"(?P<n6>" + _PF_EN_NOUN + r")(?!\w)",
    re.I)
_PAY_PASSES = (_PAY_AFFIRM, _PAY_FORMS)            # ОДНО определение, два прохода: прежние формы, затем формы шага 3b
_PF_DET = re.compile(r"ваш\w*|наш\w*|эт\w+|тот|та|ту|те|the|a|an|your|our|my|this|that|these|those", re.I)
_PF_PREP = re.compile(r"на|за|по|про|о|об|обо|для|к|ко|от|до|из|с|со|в|во|у|при|без|через|после|перед|под|над|"
                      r"насч[её]т|for|about|of|on|to|with|without|after|before|regarding|via|by", re.I)
_PF_EXIST = re.compile(r"есть|имеется|имеются", re.I)
_PF_HELD = re.compile(r"касс|уч[её]т|сч[её]т|счету|выписк|(?<!\w)ваш[аеиу]?\s+(?:(?:пред|до)?оплат|плат[её]ж|деньг|"
                      r"перевод|средств)", re.I)
_PF_DEP = re.compile(r"залог|депозит|deposit", re.I)
_PF_RENT = re.compile(r"аренд|прокат|брон|rent|booking", re.I)
_PF_MUST = re.compile(r"(?<!\w)(?:должен|должн\w*|нужно|надо|необходимо|обязан\w*|будет|будут|станет|станут|must|should|"
                      r"need\s+to|has\s+to|have\s+to|will|shall)(?!\w)", re.I)
_PF_EN_NEXT = re.compile(r"\s+(?:links?|details|methods?|options?|receipts?|screenshots?|info|information|terms|"
                         r"deadline|date|requests?|reminders?|instructions?|page|button|plan|schedule|form|reference)"
                         r"(?!\w)", re.I)
_PF_TRANSL_NEXT = re.compile(r"\s+(?:договор|документ|текст|сообщени|правил|инструкци)", re.I)  # «перевод договора»


class _PayClaim:
    """ОДНО определение «текст утверждает, что оплата получена» (K3-FIX3 N4; им живут `money_roles` и `pay_claimed`,
    т.е. ремонт F3 шага 1 — то же место, не второе). Утверждение — совпадение `_PAY_AFFIRM` или (шаг 3b, D1) формы
    `_PAY_FORMS`, в клаузе которого (от начала клаузы до конца совпадения) нет отрицания и нет будущей проверки, условия
    или вопроса, а предложение не кончается «?»; у форм шага 3b — ещё `_form_ok`. Отрицание («оплату пока не вижу»,
    «не поступила») и обещание проверки («сверит и подтвердит», «как только отразится», «будет зафиксирована») ложного
    подтверждения не дают — и ложной блокировки тоже. `search` → совпадение | None."""

    @staticmethod
    def _matches(s):
        for rx in _PAY_PASSES:
            for m in rx.finditer(s):
                yield rx, m

    @staticmethod
    def _form_ok(s, m, a):
        """Формы шага 3b (D1): клауза совпадения от `a` до разрыва/конца предложения. Не утверждение — долженствование
        или будущее в клаузе; предмет оплаты после предлога («ссылку на оплату») или англ. «payment link/details»,
        «перевод договора»; «есть/имеется» без кассы/учёта/счёта/«ваша оплата»; подлежащее — залог/депозит."""
        stop = [x.start() for x in (_PAY_CUT.search(s, m.end()), _PAY_END.search(s, m.end())) if x is not None]
        clause = s[a:min(stop) if stop else len(s)]
        if _PF_MUST.search(clause):
            return False
        gd = m.groupdict()
        for k in ("n1", "n2", "n3", "n4", "n5", "n6"):
            if gd.get(k):
                before = re.findall(r"[^\W\d_]+", s[a:m.start(k)])
                while before and _PF_DET.fullmatch(before[-1]):
                    before.pop()
                if before and _PF_PREP.fullmatch(before[-1]):
                    return False
                nxt = s[m.end(k):]
                if (k in ("n4", "n6") and _PF_EN_NEXT.match(nxt)) or \
                        (gd[k].lower().startswith("перевод") and _PF_TRANSL_NEXT.match(nxt)):
                    return False
                break
        if _PF_EXIST.fullmatch(gd.get("v1") or gd.get("v3") or "") and not _PF_HELD.search(clause):
            return False
        dep = _PF_DEP.search(clause)
        if dep is not None:
            rent = _PF_RENT.search(clause)
            if rent is None or dep.start() < rent.start():
                return False
        return True

    def search(self, text):
        s = str(text or "")
        for rx, m in self._matches(s):
            head = s[:m.start()]
            a = max([x.end() for x in _PAY_CUT.finditer(head)] + [x.end() for x in K._SENTENCE.finditer(head)] + [0])
            clause = s[a:m.end()]
            end = _PAY_END.search(s, m.end())
            asked = end is not None and end.group(0) == "?" and not _PAY_CUT.search(s[m.end():end.start()])
            if _PAY_NOT.search(clause) or _PAY_LATER.search(clause) or asked:
                continue
            if rx is _PAY_FORMS and not self._form_ok(s, m, a):
                continue
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


def pay_claimed(text):
    """Суммы, которые текст называет полученной оплатой (T4BFACTS0410): числа предложений с подтверждением оплаты —
    в батах и голые, как в `money_claims` (имя модели, дни, км, проценты суммами не считаются)."""
    out = set()
    for sent in K._SENTENCE.split(str(text or "")):
        if not _PAY_CLAIM.search(sent):
            continue
        out.update(abs(int(round(v))) for v in K.thb_amounts(sent))
        for m in _BARE.finditer(sent):
            if not _MODEL_BEFORE.search(sent[:m.start()]):
                out.add(int(re.sub(r"\D", "", m.group(1))))
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


def money_roles(text, facts):
    """Денежные роли текста против принятых фактов → [(слова причины, что)]: оплата аренды ≠ залог, записанный
    возврат запрещает «вернём», сдача — «в конце, с возвратом залога». Сумма подтверждения и залог — деньгами аренды
    обращения (T4BFACTS0410): чужая оплата подтверждением не бывает."""
    s = str(text or "")
    out = []
    bound = cash_split(facts)[0]
    paid, why = pay_verdict(facts)
    if _PAY_CLAIM.search(s) and not paid:
        # K3-FIX F3: причина словами — та, что вынес `pay_verdict` (в т.ч. «валюта не совпала» / «валюта неизвестна»)
        out.append((PAY_WORDS, "текст подтверждает оплату без кассы и второго источника: %s" % why))
    elif _PAY_CLAIM.search(s):
        alien = sorted(pay_claimed(s) - pay_backing(facts))
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
        max_calls=MAX_CALLS, max_sec=MAX_SEC, reserve=FALLBACK_SEC, handed=None):
    """Сверка одного черновика → {state, raw, usage, results, journal, calls, doors, sec, deadline}.
    state: DONE — модель дала итог; OVER — предел вызовов или секунд, итога нет; ABORTED — новое входящее.
    Общий предел (AGENTDEDUP0410): `deadline` = t0 + max_sec на ВСЮ сверку с запасным вызовом; новых вызовов модели и
    дверей сверка не начинает после deadline − reserve (остаток — запасному вызову вызывающего). `handed` (K3-FIX3 п.2)
    — суммы переданных наличных со слов клиента (`cash_said`): к каждому ходу модели код прикладывает свой расчёт сдачи
    по уже принятым фактам (`change_block`); нет сумм — запрос прежний байт-в-байт."""
    t0 = clock()
    deadline = t0 + max_sec
    stop = deadline - max(0.0, min(reserve, max_sec))
    jr = Journal(re.sub(r"\D", "", str(number))[-4:])
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
                "doors": n["doors"], "sec": clock() - t0, "deadline": deadline}
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


def judge(text, price, results, jr, since=None, handed=()):
    """Итоговый текст + исход цены + результаты → [слова причин] и заполненный журнал (факты, конфликты).
    Опора — отсеянное `sift` (AGENTDEDUP0410): каждый факт один раз, последняя версия, без снятых и устаревших
    (`since` — время последнего входящего клиента). `handed` (K3-FIX3 п.2) — суммы переданных наличных со слов клиента
    (`cash_said`): сдача кодом (`change_of`) кладётся в `figures["change"]` — её числа опора ответа; сдача по словам
    клиента, названная текстом, — причина `CHANGE_WORDS` (сумму подтверждает человек)."""
    facts, dropped = sift(results, since)
    figures = calc(facts)
    figures["change"] = change_of(facts, handed)
    jr.facts = facts
    jr.unbound = [{k: v for k, v in u.items() if k != "why"} for u in figures["unbound"]]
    jr.refusals.extend(d for d in dropped if d not in jr.refusals)
    jr.conflicts = conflicts(facts, figures)
    words = []
    if money_claims(text, price, known_amounts(price, facts, figures)):
        words.append(K.MONEY_CLAIM_WORDS)
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
