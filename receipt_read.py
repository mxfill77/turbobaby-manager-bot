"""ЧЕК В ТЕМЕ ОБСЛУЖИВАНИЯ — ПРОЧИТАТЬ ИТОГ И РАБОТЫ, НЕЯСНОЕ ПЕРЕСПРОСИТЬ (27.09.2026, 0054-74w).

Слова владельца 27.09: «А на картинке не читает сумму и задачи по тексту а надо ведь и если что
уточнять». Разведка #91 (SPLINTERCHEK2709): чек в ветке обслуживания читался промптом БАЙКА
(`kind=receipt`, полей суммы и работ нет), содержимое уходило только свободной заметкой зрения.

Чистая функция «разбор зрения → вердикт + одно сообщение RU+TH». Импорт ровно один — `re`.
Ни файлов, ни сети, ни моста: писать модуль не умеет физически.

ИСХОДОВ ТРИ: CLEAR (всё сходится — «верно?» всё равно спрашивается, запись только после «да»
доверенного) · ASK (что-то не сходится — сомнение НАЗВАНО словами) · UNREADABLE (не читается —
сказать, что видно, и попросить ровнее).

СУММА — ТОЛЬКО ПОКАЗАТЬ. Итог чека называется в сообщении и НИКУДА не пишется: деньги — решение
владельца. `works()` отдаёт работы БЕЗ сумм (число суммы строки вычищается из текста работы).
"""
import re

CLEAR, ASK, UNREADABLE = "clear", "ask", "unreadable"

# Промпт чека обслуживания — отдельный от денежного (`VISION_RECEIPT_SYSTEM`) и от промпта байка.
VISION_SERVICE_RECEIPT_SYSTEM = (
    "Ты читаешь фото ЧЕКА/КВИТАНЦИИ сервиса мотобайков (Таиланд, чек часто на тайском). "
    "Верни СТРОГО JSON без пояснений:\n"
    '{"readable": true|false, "total": число|null, "total_confidence": "high"|"medium"|"low", '
    '"currency": "THB"|"EUR"|"USD"|null, "lines": [{"text": "работа/деталь как на чеке", "amount": число|null}], '
    '"shop": "мастерская"|null, "date": "ДД.ММ.ГГГГ"|null, "plate": "номер байка на чеке"|null}\n'
    "Правила: total — ИТОГ чека (ยอดรวม/รวม/Total), не сумма одной строки. lines — каждая строка работ/"
    "деталей как на чеке, тайский допустим, не переводи. Не уверен в цифре — total_confidence low. "
    "Не видно чека или он размыт — readable false. Ничего не выдумывай."
)

_CYR = re.compile(r"[А-Яа-яЁё]")
_NUM = re.compile(r"\d[\d\s.,]*")
_CUR_WORDS = re.compile(r"(฿|บาท|thb|бат\w*)", re.IGNORECASE)
ASK_DIFF = 1          # итог и сумма строк расходятся на 1 ฿ и больше — сомнение


def _num(x):
    if x is None or x == "":
        return None
    try:
        return float(str(x).replace(" ", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def _money(x):
    v = _num(x)
    if v is None:
        return ""
    return str(int(v)) if v == int(v) else f"{v:.2f}"


def parse(raw):
    """Нормализовать разбор зрения. Не dict → None (разбор не удался)."""
    if not isinstance(raw, dict) or not raw:
        return None
    lines = []
    for ln in raw.get("lines") or []:
        if isinstance(ln, dict):
            t = str(ln.get("text") or "").strip()
            if t:
                lines.append({"text": t, "amount": _num(ln.get("amount"))})
        elif str(ln).strip():
            lines.append({"text": str(ln).strip(), "amount": None})
    return {
        "readable": raw.get("readable") is not False,
        "total": _num(raw.get("total")),
        "total_confidence": str(raw.get("total_confidence") or "").strip().lower(),
        "currency": (str(raw.get("currency")).strip().upper() if raw.get("currency") else None),
        "lines": lines,
        "shop": str(raw.get("shop") or "").strip(),
        "date": str(raw.get("date") or "").strip(),
        "plate": str(raw.get("plate") or "").strip(),
    }


def _digits(s):
    return "".join(re.findall(r"\d", str(s or "")))


def _plate_tail(bike):
    """Номер байка темы — последняя группа из 3–4 цифр имени («ADV 350 RED 9890» → 9890)."""
    g = re.findall(r"\d{3,4}", str(bike or ""))
    return g[-1] if g else ""


def work_text(line):
    """Текст работы без суммы: сумма строки и валютные слова вычищаются, модели/объёмы остаются."""
    t = str(line.get("text") or "")
    a = line.get("amount")
    if a is not None:
        for form in {_money(a), f"{a:,.0f}", f"{a:.2f}"}:
            if form:
                t = t.replace(form, " ")
    t = _CUR_WORDS.sub(" ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -—:·,;")
    return t


def works(rec):
    """Работы чека без сумм, порядок чека, повторы убраны."""
    out = []
    for ln in (rec or {}).get("lines") or []:
        w = work_text(ln)
        if w and w not in out:
            out.append(w)
    return out


def verdict(rec, bike=""):
    """→ {state, why:[(ru, th)], total, works}. Сомнение называется, а не угадывается."""
    if rec is None or not rec.get("readable") or (rec.get("total") is None and not rec.get("lines")):
        return {"state": UNREADABLE, "why": [], "total": (rec or {}).get("total"), "works": works(rec)}
    why = []
    total = rec.get("total")
    if total is None:
        why.append(("итог не читается", "อ่านยอดรวมไม่ได้"))
    elif rec.get("total_confidence") != "high":
        why.append((f"итог {_money(total)} читаю неуверенно", f"ยอดรวม {_money(total)} อ่านไม่ชัด"))
    amts = [ln.get("amount") for ln in rec.get("lines") or []]
    if total is not None and amts and all(a is not None for a in amts):
        s = sum(amts)
        if abs(s - total) >= ASK_DIFF:
            why.append((f"итог {_money(total)}, а строки дают {_money(s)} — какая сумма верна?",
                        f"ยอดรวม {_money(total)} แต่รวมรายการได้ {_money(s)} ยอดไหนถูก?"))
    cur = rec.get("currency")
    if cur and cur != "THB":
        why.append((f"валюта на чеке {cur}, не баты", f"สกุลเงินในใบเสร็จ {cur} ไม่ใช่บาท"))
    if not rec.get("lines"):
        why.append(("строк работ не вижу — что делали?", "ไม่เห็นรายการงาน ทำอะไรบ้าง?"))
    pl, tail = _digits(rec.get("plate")), _plate_tail(bike)
    if pl and tail and tail not in pl:
        why.append((f"номер на чеке {rec.get('plate')}, а тема — {bike}",
                    f"ทะเบียนในใบเสร็จ {rec.get('plate')} ไม่ตรงกับรถ {tail}"))
    return {"state": ASK if why else CLEAR, "why": why, "total": total, "works": works(rec)}


def _th_safe(s):
    """TH-половина без кириллицы: строка с кириллицей в тайский блок не идёт."""
    return "" if _CYR.search(str(s)) else str(s)


def message(v, bike=""):
    """(th, ru) — ОДНО сообщение: что видно + сомнение + «верно?». Сумма — только названа."""
    ws = v.get("works") or []
    tot = _money(v.get("total"))
    b = f" по {bike}" if bike else ""
    if v["state"] == UNREADABLE:
        seen_ru = (" Вижу: " + "; ".join(ws) + ".") if ws else ""
        seen_th = " เห็น: " + "; ".join(x for x in (_th_safe(w) for w in ws) if x) + "." \
            if any(_th_safe(w) for w in ws) else ""
        return (f"🧾 ใบเสร็จอ่านไม่ออก{seen_th} ถ่ายใหม่ให้ชัด หรือพิมพ์งานกับยอดเงินมานะครับ",
                f"🧾 Чек{b} не читается.{seen_ru} Пришли ровнее или напиши работы и сумму.")
    ru_w = "; ".join(ws) if ws else "работ не вижу"
    th_items = [x for x in (_th_safe(w) for w in ws) if x]
    th_w = "; ".join(th_items) if th_items else f"{len(ws)} รายการ"
    ru = f"🧾 Вижу чек{b}: {ru_w}" + (f"; итог {tot} ฿" if tot else "") + "."
    th = f"🧾 เห็นใบเสร็จ: {th_w}" + (f"; รวม {tot} บาท" if tot else "") + "."
    if v.get("why"):
        ru += " Сомнение: " + "; ".join(w[0] for w in v["why"]) + "."
        th += " ไม่แน่ใจ: " + "; ".join(w[1] for w in v["why"]) + "."
    ru += " Верно? Работы запишу после «Верно» от Пыма или владельца; сумму никуда не пишу."
    th += " ถูกต้องไหมครับ? บันทึกงานหลังพี่ป๋อมหรือเจ้าของกด «ถูก» ยอดเงินไม่บันทึก"
    return th, ru


def event_note(work, shop="", date=""):
    """Заметка строки «события» по работе чека — БЕЗ суммы."""
    tail = ", ".join(x for x in (shop, date) if x)
    return (f"{work} (по чеку" + (f": {tail}" if tail else "") + ", подтверждено)")[:200]
