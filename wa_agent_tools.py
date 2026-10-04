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
одного клиента держит остальных не дольше MAX_SEC (+ один обычный вызов при превышении). Новое входящее посреди
сверки (`fresh()`) обрывает её сразу: черновика нет, служба повторит позже — как и сегодня после модели.
"""

import json
import re
import time

import wa_agent_knowledge as K
import wa_book_read as B

MAX_CALLS = 8                 # вызовов модели на один черновик
MAX_SEC = 90.0                # секунд на сверку одного черновика

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
        facts.append({"kind": "cash", "row": it.get("row"), "msg_id": it.get("msg_id"), "link": it.get("link"),
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


def call_tool(tool, args, doors, clock=time.time, ctx=None):
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


def bind_ctx(number, doors, results, clock=time.time):
    """Контекст привязки одной сверки: номер обращения и аренда, которую код читает САМ (дверь rental без аргументов
    модели), один раз на сверку."""
    memo = {}

    def rental():
        if "r" not in memo:
            memo["r"] = call_tool("rental", {}, doors, clock)
        return memo["r"]
    return {"number": number, "rental": rental, "results": results}


# ------------------------------- код считает -------------------------------

def accepted(results):
    return [f for r in results if r["outcome"] == FACT for f in r["facts"]]


def calc(facts):
    """Суммы по ролям и валютам — только из принятых строк кассы; разность с ценой аренды, если она названа."""
    sums = {}
    for f in facts:
        if f["kind"] == "cash":
            key = "%s %s" % (f["role"], f["currency"])
            sums[key] = sums.get(key, 0) + f["amount"]
    out = {"sums": sums, "diffs": []}
    for f in facts:
        if f["kind"] == "rental" and f.get("price") is not None:
            paid = sums.get("%s %s" % (R_RENT, f["currency"]))
            if paid is not None:
                out["diffs"].append({"what": "цена аренды минус оплата", "currency": f["currency"],
                                     "value": f["price"] - paid})
    return out


def pay_confirmed(facts):
    """Оплата подтверждена, только если в кассе есть строка оплаты аренды И второй независимый источник:
    подписанный договор либо аренда из листа «клиенты» вместе с той же суммой в переписке (правило 03.10.2026-1)."""
    rent = [f for f in facts if f["kind"] == "cash" and f["role"] == R_RENT]
    if not rent:
        return False
    if any(f["kind"] == "contract" for f in facts):
        return True
    said = {a for f in facts if f["kind"] == "history" for a in f["amounts"]}
    return any(f["kind"] == "rental" for f in facts) and any(f["amount"] in said for f in rent)


def known_amounts(price, facts, figures):
    out = set(K.thb_amounts(price.get("line") if isinstance(price, dict) else None))
    for f in facts:
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


def money_roles(text, facts):
    """Денежные роли текста против принятых фактов → [(слова причины, что)]: оплата аренды ≠ залог, записанный
    возврат запрещает «вернём», сдача — «в конце, с возвратом залога»."""
    s = str(text or "")
    out = []
    if _PAY_CLAIM.search(s) and not pay_confirmed(facts):
        out.append((PAY_WORDS, "текст подтверждает оплату без кассы и второго источника"))
    if _DEP_CLAIM.search(s) and not any(f["kind"] == "cash" and f["role"] == R_DEPOSIT for f in facts):
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
        max_calls=MAX_CALLS, max_sec=MAX_SEC):
    """Сверка одного черновика → {state, raw, usage, results, journal, calls, sec}.
    state: DONE — модель дала итог; OVER — предел вызовов или секунд, итога нет; ABORTED — новое входящее."""
    t0 = clock()
    jr = Journal(re.sub(r"\D", "", str(number))[-4:])
    results, calls = [], 0
    ctx = bind_ctx(number, doors, results, clock)
    head = (TOOLS_BLOCK % max_calls) + "\n\n" + user
    while True:
        if fresh is not None and fresh():
            return {"state": ABORTED, "raw": None, "usage": None, "results": results, "journal": jr,
                    "calls": calls, "sec": clock() - t0}
        if calls >= max_calls or clock() - t0 > max_sec:
            return {"state": OVER, "raw": None, "usage": None, "results": results, "journal": jr,
                    "calls": calls, "sec": clock() - t0}
        block = render(results)
        raw, usage = call(system, head + ("\n\n" + block if block else ""))
        calls += 1
        if spend is not None:
            spend(usage)
        turn = parse_turn(raw)
        if turn is None or turn[0] == "final":
            if clock() - t0 > max_sec:
                return {"state": OVER, "raw": None, "usage": usage, "results": results, "journal": jr,
                        "calls": calls, "sec": clock() - t0}
            return {"state": DONE, "raw": raw, "usage": usage, "results": results, "journal": jr,
                    "calls": calls, "sec": clock() - t0}
        _, tool, args = turn
        t1 = clock()
        res = call_tool(tool, args, doors, clock, ctx)
        results.append(res)
        jr.call(len(results), tool, args, res, clock() - t1)


def judge(text, price, results, jr):
    """Итоговый текст + исход цены + результаты → [слова причин] и заполненный журнал (факты, конфликты)."""
    facts = accepted(results)
    figures = calc(facts)
    jr.facts = facts
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
