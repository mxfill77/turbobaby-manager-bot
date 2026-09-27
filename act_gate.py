# -*- coding: utf-8 -*-
"""ОДНО МЕСТО ПЕРЕД ДЕЙСТВИЕМ В ТЕМЕ БАЙКА (27.09.2026, правило владельца, задание Штаба 0055-74x).

ПОВОД (разведки ПК-репо 27.09: SPLINTERKONTEKST2709, SPLINTERPEREPROS2709,
SPLINTERPROBEGPODSHIPNIK2709, SPLINTERCHEK2709). Четыре случая одного часа в одной теме, и во всех
дверь Splinter действовала по машинному чтению ОДНОГО сообщения:
  04:38  поручение владельца человеку (тег человека) → «принял работы — пришли пробег» + заявка;
  04:59  порог «после 20 000» в тексте владельца → записан пробег 20000 без переспроса;
  05:21  фото снятой колодки от того, кому 43 мин назад поручены работы → тревога «повреждение»
         зашитым тегом Пыма;
  05:57  чек прочитан как приборка → «Вижу 198864 км, верно?», и «да» ЛЮБОГО записало бы число.
Места, которое спросило бы адресата, сверилось с темой и переспросило, до действия не было.

ПРАВИЛО ВЛАДЕЛЬЦА 27.09: сверить сообщение с тем, что идёт в теме; адресовано человеку или неясно —
одним сообщением RU+TH сказать, что видно, спросить, верно ли понято и кто берёт; действовать после
«да». Прямое поручение Splinter и ясный факт работы — как сейчас. Разговор без задач — молчание
(его держит пол ответа, 0041-74j; здесь он не судится).

ИСХОДЫ: `do` (дверь действует, как действовала) · `ask` (одно сообщение с вопросом, действие —
после «да») · `silent` (задач нет — решать нечего). Сомнение внутри функции → `ask`, а не `do`:
молча писать по сбою нельзя (правило 23.08 — и молчать тоже, поэтому не `silent`).

ГРАНИЦА УСТРОЙСТВОМ: импорты ровно `re` и `work_intent` (вокабуляр завершения берётся готовым).
Ни моста, ни диска, ни отправки — руки живут в `splinter` (`_act_gate_*`).
"""
import re

import work_intent

DO, ASK, SILENT = "do", "ask", "silent"

#: Двери, которые судит место. Остальные (карточка, ответы на вопрос бота) — вопросы сами по себе.
DOOR_TEXT_KM = "text_km"        # S11: число из текста → свой одометр «обслуживание»
DOOR_DAMAGE = "damage"          # S13: тревога J по фото
DOOR_WORKS = "works"            # S3/S4/S15: заявка и «принял работы» по перечню работ

#: Слова пробега ПЕРЕД числом: «пробег 19130», «одометр: 19 130», «mileage 19130», «ไมล์ 19130».
_KM_WORDS = r"(?:пробег\w*|одометр\w*|odo(?:meter)?|mileage|ไมล์|เลขไมล์)"
#: Единица ПОСЛЕ числа: «19130 км», «19 130 km», «19130 กม».
_KM_UNIT = r"(?:км|km|กม|กิโล)"
#: Слова ПОРОГА перед числом: число после них — срок, а не показание («после 20 000»).
_THRESHOLD = r"(?:после|через|каждые|каждых|каждый|до|от|after|every|หลัง|ทุก)"
_NUM = r"(\d{1,3}(?:[  .,]\d{3})+|\d{3,6})"

#: Слова ленты темы, по которым поручение узнаётся в СЫРОМ тексте (разборщик колодки 04:38
#: потерял — поэтому не только его `works`).
_WORK_WORDS = (
    "масл", "колодк", "тормоз", "цеп", "звезд", "подшип", "фильтр", "свеч", "ремень", "вариатор",
    "аккумулятор", "шин", "покрыш", "резин", "колес", "сальник", "вилк", "амортиз", "ролик",
    "oil", "brake", "pad", "chain", "bearing", "filter", "tire", "tyre", "belt", "battery",
    "น้ำมัน", "ผ้าเบรก", "เบรก", "โซ่", "ลูกปืน", "กรอง", "ยาง", "สายพาน", "แบต",
)


def _digits(s):
    return re.sub(r"\D", "", str(s or ""))


def work_words(text):
    """Слова работ в сыром тексте. Порядок сохранён, повторы сняты."""
    low = str(text or "").lower()
    out = []
    for w in _WORK_WORDS:
        if w in low and w not in out:
            out.append(w)
    return out


def mileage_form(text, km):
    """Как число `km` названо в тексте: explicit · threshold · bare · absent. Не бросает.

    explicit  — слово пробега перед числом или единица после («пробег 19130», «19130 км»);
    threshold — слово порога перед числом («после 20 000»): это срок, а не показание, и оно
                сильнее единицы («через 20 000 км» — всё равно порог);
    bare      — число есть, формы нет;
    absent    — числа в тексте нет (разборщик взял его не отсюда)."""
    try:
        want = _digits(km)
        if not want:
            return "absent"
        low = str(text or "").lower()
        found = False
        for m in re.finditer(_NUM, low):
            if _digits(m.group(1)) != want:
                continue
            found = True
            before = low[max(0, m.start() - 24):m.start()]
            after = low[m.end():m.end() + 8]
            if re.search(_THRESHOLD + r"[\s:]*$", before):
                return "threshold"
            if re.search(_KM_WORDS + r"[\s:=\-]*$", before) or re.match(r"\s*" + _KM_UNIT, after):
                return "explicit"
        return "bare" if found else "absent"
    except Exception:
        return "bare"


def done_fact(text):
    """Ясный факт работы: в тексте есть клауза с глаголом завершения в прошедшем («поменял», «готово»)."""
    try:
        return any(work_intent.done_past(c) for c in work_intent.clauses(text))
    except Exception:
        return False


def assignment_for(feed, author, now, window_s):
    """Поручение в ленте темы: последняя запись с тегом `author` (или любым тегом, если автор
    не назван) и словами работ в окне. → {'works': [...], 'by': ..., 'to': ..., 'age_s': ...} | {}."""
    try:
        a = str(author or "").lstrip("@").lower()
        for rec in reversed(list(feed or [])):
            age = float(now) - float(rec.get("ts") or 0)
            if age < 0 or age > float(window_s):
                continue
            tags = [str(t).lower() for t in (rec.get("tags") or [])]
            ww = list(rec.get("works") or [])
            if not ww or not tags:
                continue
            if a and a not in tags:
                continue
            return {"works": ww, "by": rec.get("author") or "", "to": tags[0], "age_s": int(age)}
    except Exception:
        return {}
    return {}


def odo_candidate(new_km, cur_km, limit):
    """Вероятное число для неправдоподобного показания: одна лишняя цифра (198864 → 19864).
    Кандидат обязан быть не меньше текущего и выше него не дальше границы. Нет — None."""
    try:
        s, cur, lim = _digits(new_km), int(cur_km), int(limit)
    except Exception:
        return None
    best = None
    for i in range(len(s)):
        c = s[:i] + s[i + 1:]
        if not c or (len(c) > 1 and c[0] == "0"):
            continue
        v = int(c)
        if cur <= v <= cur + lim and (best is None or v - cur < best - cur):
            best = v
    return best


def verdict(f):
    """Факты одного сообщения у одной двери → {'act', 'why', 'see_ru', 'see_th'}. Не бросает.

    f: door · to_bot (тег бота / ответ боту без другого адресата) · to_human (строка: кому,
    или "") · trusted · text · km (число двери text_km) · works · damage · disassembled ·
    service (положение РЕМОНТ или сервис-контекст темы) · assignment (из `assignment_for`) ·
    bike."""
    try:
        door = f.get("door")
        text = str(f.get("text") or "")
        bike = str(f.get("bike") or "")
        works = [str(w) for w in (f.get("works") or []) if str(w).strip()]
        if f.get("to_bot"):
            return _v(DO, "прямое обращение к Splinter")
        to_human = str(f.get("to_human") or "")

        if door == DOOR_TEXT_KM:
            km = str(f.get("km") or "")
            form = mileage_form(text, km)
            if to_human:
                return _v(ASK, f"число {km} в сообщении человеку ({to_human})",
                          f"в сообщении число {km} — это пробег {bike}? Сообщение адресовано "
                          f"не мне ({to_human}), без «да» пробегом не пишу",
                          f"ในข้อความมีเลข {km} — นี่คือเลขไมล์ {bike} ใช่ไหม?")
            if form == "explicit" and f.get("trusted"):
                return _v(DO, "явное «пробег N» доверенного")
            if form in ("explicit", "bare") and done_fact(text):
                return _v(DO, "число в отчёте о сделанной работе (ясный факт)")
            why = {"threshold": "число после слова порога — срок, а не показание",
                   "bare": "число без слова пробега",
                   "absent": "числа в тексте нет",
                   "explicit": "«пробег N» не от доверенного и без отчёта о работе"}.get(form, form)
            return _v(ASK, why,
                      f"в сообщении число {km} ({why}). Это пробег {bike}? Верно понял? Без «да» "
                      f"пробегом не пишу",
                      f"ในข้อความมีเลข {km} — นี่คือเลขไมล์ {bike} ใช่ไหม? ถ้าไม่ยืนยันจะไม่บันทึก")

        if door == DOOR_DAMAGE:
            asg = f.get("assignment") or {}
            if f.get("service") or f.get("disassembled") or asg:
                aw = ", ".join(asg.get("works") or []) if asg else ""
                ru = ("на фото снятая деталь" if f.get("disassembled") else "на фото деталь")
                ru += f" ({bike}). Байк в ремонте — это не повреждение при приёме. По какой это работе?"
                if aw:
                    ru += f" В теме поручено: {aw} — это оно? Верно понял?"
                th = f"ในรูปเป็นชิ้นส่วน ({bike}) รถอยู่ระหว่างซ่อม — งานไหนครับ?"
                return _v(ASK, "фото детали в сервисном положении байка", ru, th)
            return _v(DO, "повреждение на фото вне ремонта (приём/возврат)")

        if door == DOOR_WORKS:
            if to_human:
                wl = ", ".join(works) or "работы"
                return _v(ASK, f"поручение человеку ({to_human})",
                          f"вижу поручение: {wl} ({bike}) — адресовано {to_human}, не мне. "
                          f"Верно понял? Кто берёт — адресат, владелец или механик?",
                          f"เห็นงาน: {wl} ({bike}) — สั่งให้ {to_human} ใช่ไหม? ใครรับงาน?")
            return _v(DO, "работы без другого адресата")

        return _v(DO, "дверь вне места")
    except Exception as e:           # сбой места → вопрос, а не молчаливое действие
        return _v(ASK, f"разбор упал ({type(e).__name__})",
                  "не уверен, что понял сообщение. Верно понял?", "ไม่แน่ใจว่าเข้าใจถูกไหม?")


def _v(act, why, see_ru="", see_th=""):
    return {"act": act, "why": why, "see_ru": see_ru, "see_th": see_th}
