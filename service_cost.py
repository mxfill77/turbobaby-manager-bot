"""ЧЕК И СТОИМОСТЬ ОБСЛУЖИВАНИЯ — чистая функция «текст или разбор снимка → позиции, итог,
строка истории, слова ответа» (25.10.2026, SVCRECEIPT2510).

КЛАСС: деньги за обслуживание лежали в теме байка и не доходили до его истории.

ЖИВЫЕ СЛУЧАИ (группа «Обслуживание»):
  * 01.10.2026 11:19, XADV 750 GREY 2478 — фото чека PRASUTBIGBIKE CO.,LTD: «Pirelli Diablo Rosso
    Scoo…» 5,600.00 и тайская строка болтов 2 × 25.00 = 50.00, GRAND TOTAL 5,650.00, дата
    «01/10/2569» (буддийский год). Разбор снимка (`splinter.VISION_BIKE_SYSTEM`) назвал вид
    `receipt` — и всё: в истории байка нет ни суммы, ни магазина, ни позиций; бот промолчал;
  * 15.10.2026 VULCAN — FM204 250, грипсы Daytona GGD-Duel 790, работа 300 = 1,340;
  * 19.10.2026 — FM204 250, регулировка цепи 0, работа 200 = 450;
  * цена, набранная механиком текстом («Передняя шина — 980 бат», фикстура
    `tests/works_batch_harness.py`), терялась целиком: разборщик забирает работу, а число рядом
    с «бат» не видит никто — или, хуже, видит как пробег (вопрос о пробеге берёт первое число в
    4+ цифр, `splinter.handle_mileage_confirm`; «Total 2,290 bath» стал бы одометром 2290).

ЧТО РЕШАЕТ МОДУЛЬ (и только это):
  * `parse_cost_text` — есть ли в тексте СТОИМОСТЬ и какая: позиции [{name, qty, unit, price}] и
    итог. Число становится деньгами только с ПРИЗНАКОМ: валюта рядом (бат/บาท/฿/bath/baht/THB),
    слово итога (итого/total/รวม), а без них — слово цены («работа 300») или ответ на наш вопрос о
    чеке. Число с «км/กม/пробег» деньгами не бывает никогда, «на 37480» — тоже;
  * `money_numbers` / `is_money_km` — замок для детекторов пробега: число, названное деньгами,
    пробегом не бывает;
  * `normalize_receipt` — разбор снимка чека → позиции и итог; буддийский год (2569 → 2026),
    порядок дд/мм; сомнение (итог не прочитан, разбор не уверен, позиции не сходятся с итогом) →
    `ok=False`, и тогда руки НИЧЕГО не пишут, а спрашивают итог цифрами;
  * `receipt_note` — текст `notes` строки истории, урезанный под `NOTE_CAP` (итог не режется
    никогда). Длинного тире «—» в строке нет НАМЕРЕННО: карточка байка разбирает историю шаблоном
    `splinter._SVC_HIST_RE` = «<работа> — <км> км», и строка чека не имеет права прочитаться
    работой на пробеге;
  * слова ответа (RU + TH) и одна строка просьбы о чеке, которую руки приклеивают к уже уходящему
    подтверждению (`attach`).

ТРИ ИСХОДА ЗАПИСИ, А НЕ ДВА (тот же замок, что у `service_receipt`): записано · уже было (ключ
моста) · не записалось. Чек, прочитанный неуверенно, — четвёртое слово: «прочитал вот это, ничего
не записал, пришлите итог цифрами».

ИМПОРТЫ — ТОЛЬКО `re` и `datetime`. Ни сети, ни файлов, ни часов: дату сообщения приносят руки
(`splinter.handle_service_cost`, `splinter._svc_receipt_photos`). Откат — `SVC_RECEIPT=0`
строкой файла настроек + рестарт splinter: ни разбора, ни строки просьбы, ни замков пробега.
Тесты `tests/test_service_receipt_cost.py`.
"""
import datetime
import re

FLAG_ENV = "SVC_RECEIPT"        # ручка отката: «0» → прежний путь целиком
EVENT_TYPE = "чек"              # вид строки «событий»: и снимок чека, и набранная стоимость
NOTE_CAP = 200                  # столько же, сколько у соседних дверей (`work_name.NOTE_CAP`)

TH = 0
RU = 1
MARK = "🧾"

#: Строка просьбы — ОДНА на визит, приклеивается к подтверждению, которое бот и так шлёт.
ASK = ("🧾 ส่งรูปใบเสร็จหรือค่าใช้จ่ายมาด้วยครับ", "🧾 Пришлите фото чека или стоимость работ")

#: Подтверждение, что просьба запрашивала ЕЩЁ И пробег: голое число в ответ на неё — пробег.
_KM_REQUEST = re.compile(r"пришли(?:те)?\s+пробег|какой сейчас одометр|ส่งเลขไมล์|เลขไมล์ตอนนี้",
                         re.IGNORECASE)

_CUR_SIGN = {"THB": "฿", "EUR": "€", "USD": "$"}

# --- числа и признаки денег ------------------------------------------------------------------
_N = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_NSP = r"\d{1,3}(?: \d{3})+(?:\.\d{1,2})?"            # «5 650 бат» — пробел тысяч, только при валюте
_CUR_AFTER = r"(?:฿|บาท|бат(?:ов|а|ы)?\b|baht\b|bath\b|thb\b)"
_MONEY_RE = re.compile(rf"(?P<n>{_NSP}|{_N})\s*{_CUR_AFTER}|(?:฿|\bthb)\s*(?P<n2>{_N})", re.IGNORECASE)
_TOTAL_RE = re.compile(
    rf"(?:итого|итог|всего|сумма|grand\s*total|total|รวมทั้งสิ้น|รวมเงิน|ยอดรวม|ยอดสุทธิ|รวม|ทั้งหมด)"
    rf"\s*[:=\-–—]?\s*(?:฿\s*)?(?P<n>{_N})", re.IGNORECASE)
_QTY_RE = re.compile(rf"(?<![\d.,])(?P<q>\d{{1,2}})\s*[x×х\*]\s*(?P<u>{_N})(?:\s*=\s*(?P<p>{_N}))?",
                     re.IGNORECASE)
_PLAIN_RE = re.compile(rf"(?<![\d.,])(?:{_N})(?![\d])")
_KM_RE = re.compile(r"\d\s*(?:км|km|กม|กิโล)|пробег|одометр|mileage|\bodo|ไมล์", re.IGNORECASE)
_PREP_TAIL = re.compile(r"(?:\bна|\bat|@|ที่)\s*$", re.IGNORECASE)
#: Слово цены: без валюты и без итога число деньгами делает только оно (или ответ на наш вопрос).
#: «service/сервис» сюда НЕ входит намеренно: «first service 1000» — это пробег, а не цена.
_COST_WORD = re.compile(r"\bработа\b|\bза работу\b|стоимост|\bцена\b|\bоплат|\blabou?r\b|\bcost\b|"
                        r"\bprice\b|ค่าแรง|ค่าบริการ|ค่าซ่อม|ราคา", re.IGNORECASE)
#: Вопрос и план — не стоимость сделанного («будет стоить 3000 бат?», «сколько?»).
_NOT_FACT = re.compile(r"\?|\bбудет\b|\bбудут\b|\bнадо\b|\bнужно\b|\bнужен\b|\bсколько\b|\bстоить\b|"
                       r"\bесли\b|\bwill\b|\bneed\b|how much|จะ|ต้อง|ไหม|เท่าไหร่|เท่าไร", re.IGNORECASE)
#: Глагол сделанной работы: «Замена ремня … — 850 бат» — это ОТЧЁТ о работе с ценой, а не одна цена.
#: Такое сообщение обязано дойти до двери работ (она пишет работу), стоимость пишется рядом.
_WORK_VERB = re.compile(r"замен|помен|сменил|поставил|установ|почист|чистк|регулир|ремонт|сделал|починил|"
                        r"подтянул|прокач|долил|долив|залил|chang|replac|install|fixed|repair|adjust|"
                        r"clean|เปลี่ยน|ซ่อม|ล้าง|ปรับ|เติม", re.IGNORECASE)
_RECEIPT_WORD = re.compile(r"\bчек|ใบเสร็จ|receipt|\bbill\b|invoice|\bсч[её]т\b", re.IGNORECASE)
_SEG_SPLIT = re.compile(r"[\n;+]+|[,.](?=\s|$)")
_LETTERS = re.compile(r"[^\W\d_]{2,}")
_CYR = re.compile(r"[а-яё]", re.IGNORECASE)
_THAI = re.compile(r"[฀-๿]")
_HEAD_WORDS = ("чек", "receipt", "ใบเสร็จ", "стоимость", "цена", "cost", "price", "расходы", "оплата")
_SHOP_TAIL = re.compile(r"[\s,.]*(?:co\.?\s*,?\s*ltd\.?|company\s+limited|part\.?\s*,?\s*ltd\.?|"
                        r"limited|ltd\.?|inc\.?|จำกัด)\s*$", re.IGNORECASE)
_SHOP_HEAD = re.compile(r"^(?:บริษัท|ห้างหุ้นส่วนจำกัด|หจก\.?|บจก\.?)\s*", re.IGNORECASE)


def enabled(raw):
    """Ветка жива? Пусто/не задано → ДА (дефолт 1). «0/false/no/off» → нет (парсер `work_name`)."""
    return str(raw if raw is not None else "1").strip().lower() not in ("0", "false", "no", "off")


def num(x):
    """«5,650.00» / «5 650» / 5650 / 52.5 → float; не число → None (не ноль: ноль — это сумма)."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x if x is not None else "").strip().replace(" ", "").replace(" ", "")
    for ch in "฿$€":
        s = s.replace(ch, "")
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def fmt(x):
    """Сумма словами для человека: целое без «.0», копейки — как есть (52.5)."""
    v = num(x)
    if v is None:
        return "?"
    return str(int(round(v))) if abs(v - round(v)) < 0.005 else ("%.2f" % v).rstrip("0").rstrip(".")


def sign(currency):
    return _CUR_SIGN.get(str(currency or "THB").upper(), str(currency or "฿"))


def _clean(s, cap=80):
    """Слово для строки истории: без длинного тире (шаблон карточки), без «;» (разделитель позиций)."""
    t = str(s if s is not None else "")
    for a, b in (("—", "-"), ("–", "-"), (";", ","), ("\n", " "), ("\r", " "), ("\t", " ")):
        t = t.replace(a, b)
    t = " ".join(t.split()).strip(" -:=,.*•")
    return t[:cap].rstrip()


def shop_short(shop):
    """«PRASUTBIGBIKE CO.,LTD» → «PRASUTBIGBIKE»: хвост формы собственности истории не нужен."""
    t = _clean(shop, cap=60)
    t = _SHOP_HEAD.sub("", t)
    t = _SHOP_TAIL.sub("", t)
    return t.strip(" ,.-") or _clean(shop, cap=60)


# --- дата чека --------------------------------------------------------------------------------
def be_date(raw):
    """Дата КАК НАПЕЧАТАНА → `datetime.date` или None. Порядок дд/мм (тайский чек), год: буддийский
    (≥ 2400) минус 543 — «01/10/2569» → 01.10.2026; двузначный «69» — буддийский (2569), «26» — наш."""
    s = str(raw if raw is not None else "").strip()
    m = re.search(r"(\d{1,4})[./\-](\d{1,2})[./\-](\d{2,4})", s)
    if not m:
        return None
    a, b, c = m.groups()
    if len(a) == 4:
        y, mo, d = int(a), int(b), int(c)
    else:
        d, mo, y = int(a), int(b), int(c)
    if y < 100:
        y = y + 2500 if y >= 50 else y + 2000
    if y >= 2400:
        y -= 543
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def _date_plausible(d, ref):
    """Дата чека не из будущего и не старше ~13 месяцев от даты сообщения. Нет опоры — верим."""
    if d is None or ref is None:
        return d is not None
    return (ref - datetime.timedelta(days=400)) <= d <= (ref + datetime.timedelta(days=1))


# --- стоимость текстом ------------------------------------------------------------------------
def _name_of(seg, span):
    """Имя позиции = сегмент без числа (и валюты); после «:» — правая часть. Возврат (имя, хвост-лишнее)."""
    left = seg[:span[0]] + " " + seg[span[1]:]
    left = _MONEY_RE.sub(" ", left)
    left = re.sub(rf"(?<![^\W\d_]){_CUR_AFTER}", " ", left, flags=re.IGNORECASE)   # «… = 50 бат»
    left = re.sub(r"\d[\d\s,.]*\s*(?:км|km|กม)\b", " ", left, flags=re.IGNORECASE)
    extra = False
    if ":" in left:
        head, _, tail = left.rpartition(":")
        if _LETTERS.search(tail):
            h = _clean(head).lower()
            extra = bool(_LETTERS.search(h)) and h not in _HEAD_WORDS
            left = tail
    left = re.sub(r"^\s*\d{1,2}[.)]\s+", "", left)                 # «1) …» / «2. …» — нумерация
    left = re.sub(r"\s(?:за|for|на|at|ที่)\s*$", " ", " " + left.rstrip(" -–—:="), flags=re.IGNORECASE)
    return _clean(left, cap=60), extra


def _segment(seg):
    """Один сегмент текста → {'kind': total|item|bare|km|text|noise, ...}."""
    s = seg.strip(" \t-–—:•*")
    if not s:
        return {"kind": "noise"}
    km = bool(_KM_RE.search(s))
    tm = None
    for tm in _TOTAL_RE.finditer(s):
        pass
    if tm is not None and not km:
        return {"kind": "total", "amount": num(tm.group("n")), "marked": True}
    q = _QTY_RE.search(s)
    if q is not None and not km:
        qty, unit = num(q.group("q")), num(q.group("u"))
        price = num(q.group("p")) if q.group("p") else (qty or 1) * (unit or 0)
        name, extra = _name_of(s, q.span())
        return {"kind": "item", "name": name or "позиция", "qty": qty or 1, "unit": unit, "price": price,
                "marked": bool(_MONEY_RE.search(s)), "extra": extra}
    mm = None
    for mm in _MONEY_RE.finditer(s):
        pass
    if mm is not None:
        amount = num(mm.group("n") or mm.group("n2"))
        name, extra = _name_of(s, mm.span())
        if km:
            name = _clean(_KM_RE.sub(" ", name), cap=60)
        if _LETTERS.search(name or ""):
            return {"kind": "item", "name": name, "qty": 1, "unit": amount, "price": amount,
                    "marked": True, "extra": extra, "km": km}
        return {"kind": "bare", "amount": amount, "marked": True, "extra": extra, "km": km}
    if km:
        return {"kind": "km"}
    pm = None
    for pm in _PLAIN_RE.finditer(s):
        pass
    if pm is None:
        return {"kind": "text" if _LETTERS.search(s) else "noise"}
    if _PREP_TAIL.search(s[:pm.start()]):
        return {"kind": "km"}                                         # «на 37480» — пробег, не цена
    amount = num(pm.group(0))
    name, extra = _name_of(s, pm.span())
    if _LETTERS.search(name or ""):
        return {"kind": "item", "name": name, "qty": 1, "unit": amount, "price": amount,
                "marked": False, "extra": extra}
    return {"kind": "bare", "amount": amount, "marked": False, "extra": False}


#: ОКНО ПРАВДОПОДОБНОГО ОДОМЕТРА (r2, 25.10.2026): число без признака денег, лежащее в
#: [последний пробег − 150, последний пробег + 3000], может быть показанием одометра этого байка — и
#: деньгами не становится. Механики отвечают боту пробегом цифрами постоянно, а у новых байков он
#: мал (живьём ADV160 6470 на 1631 км, замена масла на 1200 км 21.10): «1650» в ответ на просьбу о
#: чеке легло бы в историю «итого 1650 ฿» — ложная запись хуже пропущенной стоимости. Границы — те же,
#: что у правдоподобия пробега со снимка (`topic_decider.PHOTO_DOWN_TOL` = 150, потолок роста без
#: даты `PHOTO_UP_NO_DATE` = 3000): одна мера «похоже на этот одометр» на обе двери.
ODO_BELOW = 150
ODO_ABOVE = 3000


def could_be_odometer(n, odo_km):
    """Число может быть показанием одометра байка с последним известным пробегом `odo_km`?
    Пробег не известен → ответа нет (None): решать за незнание вызывающий обязан сам."""
    v, o = num(n), num(odo_km)
    if v is None or o is None:
        return None
    return (o - ODO_BELOW) <= v <= (o + ODO_ABOVE)


def parse_cost_text(text, asked="", odo_km=None):
    """Стоимость в тексте → dict или None.

    `asked` — что спрашивало сообщение бота, на которое это ответ: "" (не ответ на просьбу) ·
    "cost" (просили чек/стоимость) · "cost+km" (в той же просьбе просили и пробег — тогда голое
    число остаётся пробегом). Без признака денег число деньгами не становится:
      * валюта рядом или слово итога → деньги всегда;
      * без них — только слово цены («работа 300, фильтр 250») или ответ на просьбу, и сумма
        строки не больше 9999 (дальше начинаются одометры).
    ОТВЕТ НА ПРОСЬБУ БЕЗ ПРИЗНАКА ДЕНЕГ И БЕЗ СЛОВА ЦЕНЫ (r2): число в окне одометра
    (`could_be_odometer`, `odo_km` — последний известный пробег темы) деньгами не бывает; ГОЛОЕ число
    деньгами становится только при ИЗВЕСТНОМ пробеге и вне окна — пробег не известен → не стоимость
    (fail-closed: ложная запись хуже пропущенной стоимости).
    Вопрос и план («будет стоить», «сколько», «?») — не стоимость сделанного → None.

    Возврат: {items, total, total_explicit, currency, marked, has_km, extra, numbers}.
    `has_km`/`extra` — в тексте есть пробег / слова сверх цен: такое сообщение СМЕШАННОЕ, и руки
    отдают его дальше по прежнему пути, записав только стоимость."""
    t = str(text if text is not None else "")
    if not t.strip() or _NOT_FACT.search(t):
        return None
    items, totals, bares = [], [], []
    has_km = extra = False
    for seg in _SEG_SPLIT.split(t):
        r = _segment(seg)
        k = r["kind"]
        if k == "km":
            has_km = True
        elif k == "text":
            extra = True
        elif k == "total" and r["amount"] is not None:
            totals.append(r["amount"])
        elif k == "item" and r["price"] is not None:
            items.append(r)
            extra = extra or r.get("extra", False)
            has_km = has_km or r.get("km", False)
        elif k == "bare" and r["amount"] is not None:
            bares.append(r)
            extra = extra or r.get("extra", False)
            has_km = has_km or r.get("km", False)
    marked = bool(totals) or any(r["marked"] for r in items + bares)
    if items or totals:
        bares = [r for r in bares if r["marked"]]   # «1.» / «2.» нумерации деньгами не бывают
    if marked:
        items = [r for r in items if r["marked"] or (r["price"] or 0) <= 99999]
    else:
        amounts = [r["price"] if "price" in r else r["amount"] for r in items + bares]
        small = all(a <= 9999 for a in amounts)
        cost_word = bool(_COST_WORD.search(t))
        odo_known = num(odo_km) is not None
        near_odo = (not cost_word) and any(could_be_odometer(a, odo_km) for a in amounts)
        if asked == "cost":
            # голое число — только при известном пробеге и вне его окна; позиция с именем — вне окна
            accept = small and not near_odo and (bool(items) or (bool(bares) and (cost_word or odo_known)))
        elif asked == "cost+km":
            accept = bool(items) and small and not near_odo
            bares = []
        else:
            accept = bool(items) and small and bool(_COST_WORD.search(t))
            bares = []
        if not accept:
            return None
    if not (items or totals or bares):
        return None
    if totals:
        total, explicit = totals[-1], True
    elif items:
        total, explicit = sum(r["price"] for r in items) + sum(r["amount"] for r in bares), False
    else:
        total, explicit = sum(r["amount"] for r in bares), False
    out_items = [{"name": r["name"], "orig": "", "qty": r["qty"], "unit": r["unit"], "price": r["price"]}
                 for r in items]
    numbers = set()
    for v in [total] + [i["price"] for i in out_items] + [i["unit"] for i in out_items] + \
             [r["amount"] for r in bares] + totals:
        if v is not None:
            numbers.add(int(round(v)))
    return {"items": out_items, "total": total, "total_explicit": explicit, "currency": "THB",
            "marked": marked, "has_km": has_km, "extra": extra, "numbers": numbers,
            "shop": "", "date": None}


def money_numbers(text):
    """Все числа текста, названные ДЕНЬГАМИ (валюта рядом, слово итога, принятая стоимость)."""
    t = str(text if text is not None else "")
    out = set()
    for m in _MONEY_RE.finditer(t):
        v = num(m.group("n") or m.group("n2"))
        if v is not None:
            out.add(int(round(v)))
    for m in _TOTAL_RE.finditer(t):
        v = num(m.group("n"))
        if v is not None:
            out.add(int(round(v)))
    c = parse_cost_text(t)
    if c is not None:
        out |= c["numbers"]
    return out


def is_money_km(text, km):
    """Замок детекторов пробега: это число в тексте названо деньгами → пробегом оно не бывает."""
    v = num(km)
    return v is not None and int(round(v)) in money_numbers(text)


def work_verb(text):
    """В тексте глагол сделанной работы (замена/поменял/регулировка/เปลี่ยน …)."""
    return bool(_WORK_VERB.search(str(text or "")))


def caption_says_receipt(text):
    """Подпись к фото называет чек (чек/ใบเสร็จ/receipt/bill/invoice/счёт)."""
    return bool(_RECEIPT_WORD.search(str(text or "")))


def ask_kind(replied_text):
    """Сообщение бота, на которое ответили, — наша просьба о чеке? None · "cost" · "cost+km"."""
    s = str(replied_text or "")
    if MARK not in s:
        return None
    if not (ASK[RU] in s or ASK[TH] in s or "цифрами" in s or "ตัวเลข" in s):
        return None
    return "cost+km" if _KM_REQUEST.search(s) else "cost"


# --- чек со снимка ----------------------------------------------------------------------------
def normalize_receipt(v, ref_date=None):
    """Разбор снимка чека (JSON модели) → {shop, date, items, total, currency, ok, why}.

    ДАТА СЧИТАЕТСЯ КОДОМ, а не моделью: модель приносит дату КАК НАПЕЧАТАНА, пересчёт буддийского
    года и порядок дд/мм делает `be_date`. Дата вне правдоподобного окна не пишется (позиции и итог
    от этого не сомнительны — сомнительна только дата).
    СОМНЕНИЕ → ok=False, и руки не пишут ничего: итог не прочитан · разбор не уверен · у позиции
    нет цены · позиции не сходятся с итогом (допуск 1 ฿, либо итог = позиции + НДС 7 %)."""
    v = v if isinstance(v, dict) else {}
    shop = _clean(v.get("shop"), cap=60)
    raw_date = str(v.get("date") or "").strip()
    d = be_date(raw_date)
    date_note = ""
    if d is not None and not _date_plausible(d, ref_date):
        date_note = f"дата «{raw_date}» вне окна — не пишу её"
        d = None
    items = []
    for it in (v.get("items") or []):
        if not isinstance(it, dict):
            continue
        name = _clean(it.get("name") or it.get("name_orig"), cap=60)
        orig = _clean(it.get("name_orig"), cap=60)
        qty, unit, price = num(it.get("qty")), num(it.get("unit_price")), num(it.get("price"))
        if qty is None or qty <= 0:
            qty = 1.0
        if price is None and unit is not None:
            price = unit * qty
        if unit is None and price is not None:
            unit = price / qty
        if price is None and not name:
            continue
        items.append({"name": name or "позиция", "orig": orig, "qty": qty, "unit": unit, "price": price})
    total = num(v.get("total"))
    cur = str(v.get("currency") or "THB").strip().upper()
    if cur not in _CUR_SIGN:
        cur = "THB"
    conf = str(v.get("confidence") or "").strip().lower()
    priced = [i["price"] for i in items if i["price"] is not None]
    s = sum(priced)
    why = []
    if (total is None or total <= 0) and items and len(priced) == len(items) and conf == "high" and s > 0:
        total = s
    if total is None or total <= 0:
        why.append("итог не прочитан")
    if conf != "high":
        why.append("разбор не уверен")
    if len(priced) != len(items):
        why.append("не у всех позиций прочитана цена")
    if total and priced and abs(s - total) > 1 and abs(s * 1.07 - total) > 2:
        why.append(f"позиции {fmt(s)} не сходятся с итогом {fmt(total)}")
    return {"shop": shop, "date": d, "items": items, "total": total, "currency": cur,
            "ok": not why, "why": "; ".join(why), "date_note": date_note, "raw_date": raw_date}


# --- строка истории ---------------------------------------------------------------------------
def _item_note(i, cur):
    q = i.get("qty") or 1
    if q and abs(q - 1) > 1e-9 and i.get("unit") is not None:
        return f"{_clean(i['name'], 60)} {fmt(q)}×{fmt(i['unit'])} {cur}"
    return f"{_clean(i['name'], 60)} {fmt(i.get('price'))} {cur}"


def receipt_note(rc, typed=False):
    """`notes` строки истории (≤ NOTE_CAP). Чек: «чек SHOP 01.10.2026: поз; поз; итого N ฿»;
    набранная стоимость: «стоимость: поз; итого N ฿». Позиции режутся С КОНЦА («…»), итог — никогда."""
    cur = sign(rc.get("currency"))
    if typed:
        head = "стоимость: "
    else:
        shop = shop_short(rc.get("shop") or "")
        d = rc.get("date")
        head = "чек" + (f" {shop[:40]}" if shop else "") + (f" {d.strftime('%d.%m.%Y')}" if d else "") + ": "
    tail = f"итого {fmt(rc.get('total'))} {cur}"
    parts = [_item_note(i, cur) for i in (rc.get("items") or [])]
    room = NOTE_CAP - len(head) - len(tail)
    kept = []
    for k, p in enumerate(parts):
        rest = len(parts) - k - 1
        need = len("; ".join(kept + [p])) + 2 + (len("…; ") if rest else 0)
        if need > room:
            kept.append("…")
            break
        kept.append(p)
    body = "; ".join(kept + [tail]) if kept else tail
    note = head + body
    if len(note) > NOTE_CAP:                    # голова сама длиннее места — режем голову, не итог
        note = head[:max(0, NOTE_CAP - len(tail) - 3)].rstrip() + ": " + tail
    return note[:NOTE_CAP]


# --- слова ответа -----------------------------------------------------------------------------
def _name_for(i, lang, k):
    """Имя позиции на нужном языке: тайская половина без кириллицы, русская — без тайского."""
    if lang == TH:
        for cand in (i.get("orig"), i.get("name")):
            if cand and not _CYR.search(cand):
                return cand
        return f"รายการ {k}"
    for cand in (i.get("name"), i.get("orig")):
        if cand and not _THAI.search(cand):
            return cand
    return f"позиция {k}"


def _item_lines(items, cur, lang, limit=8):
    out = []
    for k, i in enumerate(items[:limit], 1):
        nm = _name_for(i, lang, k)
        q = i.get("qty") or 1
        if abs(q - 1) > 1e-9 and i.get("unit") is not None:
            out.append(f"   — {nm} {fmt(q)} × {fmt(i['unit'])} = {fmt(i.get('price'))} {cur}")
        else:
            out.append(f"   — {nm} {fmt(i.get('price'))} {cur}")
    if len(items) > limit:
        out.append("   — …" + (f" (อีก {len(items) - limit})" if lang == TH else f" (ещё {len(items) - limit})"))
    return out


def _head(rc, lang):
    shop = shop_short(rc.get("shop") or "")
    d = rc.get("date")
    ds = d.strftime("%d.%m.%Y") if d else ""
    word = "🧾 ใบเสร็จ" if lang == TH else "🧾 Чек"
    return " ".join(x for x in (word, shop, ds) if x)


_DONE = {
    "written": ("บันทึกลงประวัติแล้วครับ", "записал в историю байка"),
    "dup": ("บันทึกไว้แล้วครับ ไม่บันทึกซ้ำ", "уже был в истории — второй раз не пишу"),
    "failed": ("⚠️ ยังบันทึกไม่สำเร็จ — ส่งใหม่อีกครั้งภายหลังนะครับ",
               "⚠️ в историю НЕ легло ({err}) — пришлите ещё раз позже"),
}


def receipt_reply(outcomes):
    """Исходы по снимкам чеков → (тайская половина, русская). `outcomes` = [{state, rc, error}],
    state ∈ written · dup · failed · unsure. Половины рендерит ОДНА функция из ОДНИХ исходов."""
    th, ru = [], []
    for o in outcomes or []:
        rc, st = o.get("rc") or {}, o.get("state")
        cur = sign(rc.get("currency"))
        if st == "unsure":
            th.append("🧾 อ่านใบเสร็จได้ไม่ชัดครับ" + (f" — {shop_short(rc.get('shop'))}" if rc.get("shop") else ""))
            ru.append("🧾 Чек прочитал неуверенно (" + (rc.get("why") or "не разобрал") + ")"
                      + (f" — {shop_short(rc.get('shop'))}" if rc.get("shop") else ""))
            th += _item_lines(rc.get("items") or [], cur, TH, limit=4)
            ru += _item_lines(rc.get("items") or [], cur, RU, limit=4)
            if rc.get("total"):
                th.append(f"   รวม {fmt(rc['total'])} {cur} ?")
                ru.append(f"   итого {fmt(rc['total'])} {cur} ?")
            th.append("   ยังไม่บันทึก — พิมพ์ยอดรวมเป็นตัวเลขให้หน่อยครับ เช่น «รวม 1340 บาท» 🙏")
            ru.append("   Ничего не записал — пришлите итог цифрами, например «итого 1340 бат» 🙏")
            continue
        done_th, done_ru = _DONE.get(st, _DONE["failed"])
        done_ru = done_ru.replace("{err}", str(o.get("error") or "мост не ответил"))
        th.append(_head(rc, TH))
        ru.append(_head(rc, RU))
        th += _item_lines(rc.get("items") or [], cur, TH)
        ru += _item_lines(rc.get("items") or [], cur, RU)
        th.append(f"   รวม {fmt(rc.get('total'))} {cur} — {done_th}")
        ru.append(f"   итого {fmt(rc.get('total'))} {cur} — {done_ru}")
        if rc.get("date_note"):
            ru.append(f"   ({rc['date_note']})")
    return "\n".join(th), "\n".join(ru)


def cost_reply(c, state, error=""):
    """Набранная стоимость → (тайская половина, русская). state ∈ written · dup · failed · same.
    `same` — тот же итог сегодня уже лёг по чеку: второй строки не пишем и говорим это."""
    cur = sign(c.get("currency"))
    items = c.get("items") or []
    total = fmt(c.get("total"))
    th_names = [f"{_name_for(i, TH, k)} {fmt(i.get('price'))} {cur}" for k, i in enumerate(items, 1)]
    ru_names = [_item_note(i, cur) for i in items]
    if state == "same":
        return (f"🧾 ยอด {total} {cur} บันทึกตามใบเสร็จแล้วครับ ไม่บันทึกซ้ำ",
                f"🧾 Итог {total} {cur} уже записан по чеку — второй раз не пишу")
    if state == "failed":
        return ("🧾 ⚠️ บันทึกค่าใช้จ่ายไม่สำเร็จ — ส่งใหม่อีกครั้งภายหลังนะครับ",
                f"🧾 ⚠️ Стоимость в историю НЕ легла ({error or 'мост не ответил'}) — пришлите ещё раз позже")
    if state == "dup":
        return (f"🧾 ค่าใช้จ่ายนี้บันทึกไว้แล้วครับ (รวม {total} {cur})",
                f"🧾 Эта стоимость уже в истории (итого {total} {cur}) — второй раз не пишу")
    th = "🧾 บันทึกค่าใช้จ่ายลงประวัติแล้วครับ: " + ("; ".join(th_names) + " · " if th_names else "") + \
         f"รวม {total} {cur}"
    ru = "🧾 Записал стоимость в историю байка: " + ("; ".join(ru_names) + " · " if ru_names else "") + \
         f"итого {total} {cur}"
    return th, ru


def ack_line(c):
    """Строка «стоимость записана» для смешанного сообщения: едет в следующее подтверждение работ."""
    cur = sign(c.get("currency"))
    return (f"🧾 บันทึกค่าใช้จ่ายแล้ว: รวม {fmt(c.get('total'))} {cur}",
            f"🧾 Записал стоимость: итого {fmt(c.get('total'))} {cur}")


def attach(text, th_line, ru_line):
    """Приклеить к двуязычному сообщению по строке: тайскую — в конец тайского блока (перед
    разделителем, если он уже стоит), русскую — в конец. Без флагов — обе в конец."""
    if not th_line and not ru_line:
        return text
    lines = str(text or "").split("\n")
    i = None
    for k, ln in enumerate(lines):
        if ln.lstrip().startswith("🇷🇺"):
            i = k
            break
    if i is None:
        return "\n".join(lines + [x for x in (th_line, ru_line) if x])
    j = i - 1 if (i > 0 and lines[i - 1].strip() and set(lines[i - 1].strip()) == {"➖"}) else i
    if th_line:
        lines.insert(j, th_line)
    if ru_line:
        lines.append(ru_line)
    return "\n".join(lines)
