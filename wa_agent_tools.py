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

Ответ каждого инструмента: tool · outcome · source · ref · at (время чтения) · version · window · reason · facts.
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


def result(tool, outcome, source="", ref="", at=None, version="", window="", reason="", facts=None):
    return {"tool": tool, "outcome": outcome, "source": source, "ref": ref, "at": at, "version": version,
            "window": window, "reason": reason, "facts": list(facts or [])}


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
    bound = dict(fact, booking_id=rent.get("booking_id"), bound_by=by)
    return result("contract", FACT, src, ref, at, version=str(fact.get("signed_at") or ""),
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


def rental_result(resp, at=None):
    src = "снимок броней (лист «клиенты»)"
    if not (isinstance(resp, dict) and resp.get("ok")):
        return _refusal("rental", resp, src, at)
    rows = [r for r in resp.get("rows") or [] if isinstance(r, dict)]
    live = [r for r in rows if not _CANCEL.search(str(r.get("status") or ""))]
    if rows and not live:
        return result("rental", CANCELLED, src, at=at, reason="аренды по номеру отменены")
    if not live:
        return result("rental", EMPTY, src, at=at,
                      reason="по номеру аренда не найдена — это «не знаю», а не «аренды нет»")
    if len(live) > 1:
        return result("rental", AMBIGUOUS, src, at=at, reason="аренд по номеру %d — выбрать нельзя" % len(live))
    r = live[0]
    return result("rental", FACT, src, ref=str(r.get("booking_id") or r.get("bike") or ""), at=at,
                  window="%s…%s" % (r.get("date_start") or "?", r.get("date_end") or "?"), facts=[{
                      "kind": "rental", "booking_id": r.get("booking_id"), "bike": r.get("bike"),
                      "date_start": r.get("date_start"), "date_end": r.get("date_end"), "status": r.get("status"),
                      "price": r.get("price") if isinstance(r.get("price"), (int, float)) else None,
                      "currency": str(r.get("currency") or "THB").upper()}])


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
        return result("rules", REFUSED, src, at=at, reason="узел не прочитан")
    text = str(node["text"])
    return result("rules", FACT, src, ref="business_rules", at=at, version="%d симв." % len(text), facts=[{
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


def call_tool(tool, args, doors, clock=time.time, ctx=None):
    """Имя + вход → результат по контракту, с тождеством запроса `req` (AGENTDEDUP0410)."""
    res = _read(tool, args, doors, clock, ctx)
    res["req"] = request_key(tool, args)
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
    try:
        raw = door(**(args or {}))
    except TimeoutError:
        return result(tool, TIMEOUT, at=at, reason="таймаут двери")
    except Exception as e:                                          # noqa: BLE001
        if "timeout" in type(e).__name__.lower():
            return result(tool, TIMEOUT, at=at, reason="таймаут двери")
        return result(tool, REFUSED, at=at, reason="дверь упала: %s" % type(e).__name__)
    ctx = ctx or {}
    if tool == "contract":
        rental = ctx["rental"]() if callable(ctx.get("rental")) else None
        return contract_result(raw, at, number=ctx.get("number") or "", rental=rental)
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
    return {"number": number, "rental": rental, "results": results}


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


def pay_confirmed(facts):
    """Оплата подтверждена, только если аренда обращения одна, в кассе есть строка оплаты ЭТОЙ аренды И второй
    независимый источник ТОЙ ЖЕ аренды: договор, привязанный к ней кодом, либо её строка листа «клиенты» вместе с той
    же суммой в переписке (правило 03.10.2026-1; привязка — AGENTDEDUP0410)."""
    bk = rental_of(facts)
    if bk is None:
        return False
    rent = [f for f in facts if f["kind"] == "cash" and f["role"] == R_RENT and cash_of_rental(f, bk, facts)]
    if not rent:
        return False
    if any(f["kind"] == "contract" and str(f.get("booking_id") or "") == bk for f in facts):
        return True
    said = {a for f in facts if f["kind"] == "history" for a in f["amounts"]}
    return (any(f["kind"] == "rental" and str(f.get("booking_id") or "") == bk for f in facts)
            and any(f["amount"] in said for f in rent))


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
    return out


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


_PAY_CLAIM = re.compile(r"оплат\w*\s+(?:\S+\s+){0,3}(?:получен|подтвержд|поступил|прошл|пришл)|"
                        r"получил[аи]?\s+(?:вашу\s+)?(?:оплату|деньги|перевод)|"
                        r"payment\s+(?:is\s+|has\s+been\s+)?(?:received|confirmed)|"
                        r"(?:we\s+)?received\s+(?:your\s+)?(?:payment|money|transfer)|paid\s+in\s+full", re.I)
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
    out = {abs(int(round(f["amount"]))) for f in rows}
    out.update(abs(int(round(v))) for v in list(figures["sums"].values()) + [d["value"] for d in figures["diffs"]])
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
    if _PAY_CLAIM.search(s) and not pay_confirmed(facts):
        out.append((PAY_WORDS, "текст подтверждает оплату без кассы и второго источника"))
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
                           "outcome": res["outcome"], "reason": res["reason"][:200], "sec": round(sec, 2)})
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
contract {"phone": "...", "name": "...", "bike": "..."} — подписанный договор; contract_pdf {"file_id": "..."} — метаданные PDF;
delivery {} — доставка; rules {} — правила владельца.
Не больше %d вызовов. Когда хватит — итоговый черновик обычным JSON ответа (text, handoff, lang, why).
Суммы и разности не считай сам — их посчитает код. Оплату не подтверждай без кассы и договора."""


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
        max_calls=MAX_CALLS, max_sec=MAX_SEC, reserve=FALLBACK_SEC):
    """Сверка одного черновика → {state, raw, usage, results, journal, calls, doors, sec, deadline}.
    state: DONE — модель дала итог; OVER — предел вызовов или секунд, итога нет; ABORTED — новое входящее.
    Общий предел (AGENTDEDUP0410): `deadline` = t0 + max_sec на ВСЮ сверку с запасным вызовом; новых вызовов модели и
    дверей сверка не начинает после deadline − reserve (остаток — запасному вызову вызывающего)."""
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


def judge(text, price, results, jr, since=None):
    """Итоговый текст + исход цены + результаты → [слова причин] и заполненный журнал (факты, конфликты).
    Опора — отсеянное `sift` (AGENTDEDUP0410): каждый факт один раз, последняя версия, без снятых и устаревших
    (`since` — время последнего входящего клиента)."""
    facts, dropped = sift(results, since)
    figures = calc(facts)
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
    return words, figures
