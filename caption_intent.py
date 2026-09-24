# -*- coding: utf-8 -*-
"""ПОДПИСЬ К ФОТО: КОРОТКОЕ УКАЗАНИЕ — ЗАЯВКА, А НЕ ПОВОД СОВЕТОВАТЬ МОЙКУ (24.09.2026).

ПОВОД, ИЗ ЖУРНАЛА СЕРВЕРА (артефакт ПК `2026-09-24-XADVZHIVOYSLUCHAY2409.md`, §2–§3). 24.09 07:09
UTC владелец прислал в тему XADV 750 GREY 2478 фото колеса с подписью «Need to change». Разборщик
текста (`SERVICING_SYSTEM`) вердикта не дал: `type=None works=[]`. Строка событий легла как
`photo` без текста подписи — поля для неё нет. Заявки нет. Снимок сказал «колесо, грязь», и ветка
C ответила советом помыть байк на фото, подписанное «надо менять».

ЧТО РЕШАЕТ МОДУЛЬ. Одна подпись → одно из ТРЁХ состояний:
    DIRECTIVE  короткое УКАЗАНИЕ сделать работу («need to change», «заменить», «сломано»,
               «เปลี่ยน», «เสีย») — заявка на байк темы;
    DONE       отчёт о СДЕЛАННОМ («changed», «поменял», «เปลี่ยนแล้ว») — прежний путь записи работ;
    NONE       ни то ни другое: болтовня, вопрос, отрицание, длинный текст, одни теги и знаки —
               прежний путь, байт-в-байт.
Третий исход не запасной: «не знаю» здесь всегда значит «как было», и заявку модуль рождает
только по положительному признаку.

ПОЧЕМУ СЛОВАМИ, А НЕ МОДЕЛЬЮ. Модель уже была спрошена и промолчала. Указание в подписи —
это 1–5 слов из узкого словаря, и его видно без модели. Длиннее пяти слов — не подпись-указание,
а текст; его судит разборщик, как судил.

ПОРЯДОК ПРОВЕРОК И ПОЧЕМУ ИМЕННО ТАКОЙ.
  1 слов нет (теги, ссылки, эмодзи) → NONE;
  2 слов больше пяти → NONE;
  3 вопрос (знак или частица, определение `work_intent.asks`) → NONE: «need to change?» —
    вопрос о работе, а не заявка на неё (класс 22.08, ADV 350 372);
  4 отчёт о сделанном → DONE, раньше указания: «เปลี่ยนแล้ว» несёт и глагол, и «уже»;
  5 отрицание («не надо менять», «no need», «ไม่ต้อง») → NONE;
  6 указание → DIRECTIVE.

ПРЕДМЕТ. Что менять — из подписи по малому словарю деталей, иначе из снимка (`kind=wheel` →
колесо), иначе честное «по фото». Слова предмета даны парой RU/TH из словаря, поэтому в тайской
строке подтверждения кириллицы не бывает.

ЧИСТОТА. Импорты ровно два — `re` и `work_intent` (одно определение вопроса на оба решения:
разойдясь, два списка частиц дали бы заявку там, где соседний гейт видит вопрос). Моста, записи,
сети и часов здесь нет; руки — в `splinter._caption_zayavka`.
"""
import re

import work_intent

DIRECTIVE = "directive"
DONE = "done"
NONE = "none"

#: Подпись-указание короткая. Длиннее — это уже текст, его судит разборщик.
MAX_WORDS = 5

#: Действие → (RU, TH) для строки подтверждения.
ACT_CHANGE = "change"
ACT_REPAIR = "repair"
ACT_BROKEN = "broken"
ACT_LABEL = {
    ACT_CHANGE: ("замена", "เปลี่ยน"),
    ACT_REPAIR: ("ремонт", "ซ่อม"),
    ACT_BROKEN: ("поломка", "ชำรุด"),
}

# --- отчёт о сделанном: проверяется РАНЬШЕ указания ---------------------------------------
_DONE_EN = frozenset(("changed", "replaced", "fixed", "repaired", "done", "finished", "installed"))
_DONE_RU = re.compile(
    r"\b(?:заменил\w*|поменял\w*|сменил\w*|починил\w*|замен[её]н\w*|поменян\w*|сделал\w*|"
    r"сделан\w*|готово|залил\w*|поставил\w*|отремонтирован\w*|устранил\w*)")
_DONE_TH = ("แล้ว", "เสร็จ", "เรียบร้อย")

# --- отрицание: «не надо менять» заявкой не является --------------------------------------
_NEG_EN = frozenset(("no", "not", "dont", "don", "doesnt", "doesn", "never"))
_NEG_RU = re.compile(r"\bне\s+(?:надо|нужн\w*|стоит|менять|меняй|трогать|трогай)\b|\bнет\s+нужды\b")
_NEG_TH = ("ไม่",)

# --- указание: действие по порядку силы (замена > ремонт > поломка) -----------------------
_ACT_EN = (
    (ACT_CHANGE, frozenset(("change", "replace", "need", "needs"))),
    (ACT_REPAIR, frozenset(("fix", "repair"))),
    (ACT_BROKEN, frozenset(("broken", "broke", "damaged"))),
)
_ACT_RU = (
    (ACT_CHANGE, re.compile(r"\b(?:замени(?:ть)?|поменя(?:ть|й)|меня(?:ть|й)|смени(?:ть)?)\b"
                            r"|\b(?:под|на)\s+замену\b|\b(?:нужн\w*|надо|требу\w*)\s+замен\w*")),
    (ACT_REPAIR, re.compile(r"\b(?:почини(?:ть)?|отремонтир(?:овать|уй))\b|\bне\s+работает\b")),
    (ACT_BROKEN, re.compile(r"\bслома\w*")),
)
_ACT_TH = (
    (ACT_CHANGE, ("เปลี่ยน",)),
    (ACT_REPAIR, ("ซ่อม",)),
    (ACT_BROKEN, ("ชำรุด", "พัง")),
)
#: «เสีย» (сломан) сидит внутри «เสียง» (звук) — поэтому отдельным правилом, не подстрокой.
_TH_BROKEN_RE = re.compile("เสีย(?!ง)")

# --- предмет: (RU, TH, слова EN, регэксп RU, подстроки TH); порядок значим: колодки раньше тормоза
_OBJECTS = (
    ("шина", "ยาง", frozenset(("tire", "tyre", "tires", "tyres")),
     re.compile(r"\b(?:шин\w*|покрышк\w*|резин\w*)"), ("ยาง",)),
    ("колесо", "ล้อ", frozenset(("wheel", "wheels", "rim")),
     re.compile(r"\b(?:колес\w*|колёс\w*)"), ("ล้อ",)),
    ("тормозные колодки", "ผ้าเบรก", frozenset(("pad", "pads")),
     re.compile(r"\bколодк\w*"), ("ผ้าเบรก",)),
    ("тормоза", "เบรก", frozenset(("brake", "brakes")),
     re.compile(r"\bтормоз\w*"), ("เบรก",)),
    ("цепь", "โซ่", frozenset(("chain",)),
     re.compile(r"\bцеп\w*"), ("โซ่",)),
    ("масло", "น้ำมันเครื่อง", frozenset(("oil",)),
     re.compile(r"\bмасл\w*"), ("น้ำมัน",)),
    ("аккумулятор", "แบตเตอรี่", frozenset(("battery",)),
     re.compile(r"\b(?:аккумулятор\w*|акб)\b"), ("แบต",)),
    ("зеркало", "กระจก", frozenset(("mirror", "mirrors")),
     re.compile(r"\bзеркал\w*"), ("กระจก",)),
    ("ремень", "สายพาน", frozenset(("belt",)),
     re.compile(r"\bрем(?:ень|н[яюеи])\b"), ("สายพาน",)),
    ("фара", "ไฟหน้า", frozenset(("light", "headlight", "lamp")),
     re.compile(r"\b(?:фар[аыуе]?|лампочк\w*)\b"), ("ไฟหน้า",)),
)
_OBJ_WHEEL_PHOTO = ("колесо", "ล้อ")
_OBJ_UNKNOWN = ("что — по фото", "ดูตามรูป")


def _words(text):
    """Слова подписи без тегов людей и ссылок; слово — токен, где есть буква или цифра."""
    out = []
    for tok in str(text or "").split():
        if tok.startswith("@") or tok.lower().startswith(("http://", "https://", "t.me/")):
            continue
        if any(ch.isalnum() for ch in tok):
            out.append(tok)
    return out


def _en(low):
    return set(re.findall(r"[a-z]+", low.replace("'", "")))


def verdict(text):
    """Подпись → `{"state": DIRECTIVE|DONE|NONE, "why": str, "act": str|None, "n": int}`.
    Не бросает: любой сбой = NONE (прежний путь)."""
    try:
        return _verdict(text)
    except Exception as e:          # решение не имеет права уронить заход
        return {"state": NONE, "why": f"разбор подписи упал ({type(e).__name__})", "act": None, "n": 0}


def _verdict(text):
    words = _words(text)
    n = len(words)
    if not n:
        return {"state": NONE, "why": "в подписи нет слов", "act": None, "n": 0}
    if n > MAX_WORDS:
        return {"state": NONE, "why": f"слов {n} > {MAX_WORDS}: это текст, его судит разборщик",
                "act": None, "n": n}
    body = " ".join(words)
    low = body.lower()
    if any(work_intent.asks(c) for c in work_intent.clauses(body)):
        return {"state": NONE, "why": "вопрос, а не указание", "act": None, "n": n}
    en = _en(low)
    if en & _DONE_EN or _DONE_RU.search(low) or any(m in body for m in _DONE_TH):
        return {"state": DONE, "why": "отчёт о сделанном", "act": None, "n": n}
    if en & _NEG_EN or _NEG_RU.search(low) or any(m in body for m in _NEG_TH):
        return {"state": NONE, "why": "отрицание", "act": None, "n": n}
    for act, kws in _ACT_EN:
        if en & kws:
            return {"state": DIRECTIVE, "why": "указание (EN)", "act": act, "n": n}
    for act, rx in _ACT_RU:
        if rx.search(low):
            return {"state": DIRECTIVE, "why": "указание (RU)", "act": act, "n": n}
    for act, subs in _ACT_TH:
        if any(s in body for s in subs):
            return {"state": DIRECTIVE, "why": "указание (TH)", "act": act, "n": n}
    if _TH_BROKEN_RE.search(body):
        return {"state": DIRECTIVE, "why": "указание (TH)", "act": ACT_BROKEN, "n": n}
    return {"state": NONE, "why": "указания нет", "act": None, "n": n}


def object_of(text, vis=None):
    """Что менять → (RU, TH). Сначала подпись (словарь деталей), затем снимок: `kind=wheel` —
    колесо. Не названо нигде — честное «по фото», а не догадка."""
    low = str(text or "").lower()
    en = _en(low)
    for ru, th, kws_en, rx_ru, subs_th in _OBJECTS:
        if en & kws_en or rx_ru.search(low) or any(s in str(text or "") for s in subs_th):
            return ru, th
    kind = str((vis or {}).get("kind") or "").strip().lower()
    if kind == "wheel":
        return _OBJ_WHEEL_PHOTO
    return _OBJ_UNKNOWN


def work_label(act, obj_ru):
    """Строка работы для заявки: «замена (колесо)». Ложится в note заявки дословно."""
    return f"{ACT_LABEL.get(act, ACT_LABEL[ACT_CHANGE])[0]} ({obj_ru})"


def confirm_text(bike, act, obj):
    """Подтверждение заявки: одно сообщение, TH + RU, строки со значком блокнота."""
    ru_act, th_act = ACT_LABEL.get(act, ACT_LABEL[ACT_CHANGE])
    obj_ru, obj_th = obj
    return (f"🐀 Splinter\n"
            f"📝 รับเรื่อง: {bike} — {th_act} ({obj_th})\n"
            f"📝 заявка: {bike} — {ru_act} ({obj_ru})")


def note_with_caption(notes, caption, limit=200):
    """Текст подписи — в существующее поле `notes` строки событий, с пометкой «подпись:».
    Подпись идёт ПЕРВОЙ: поле режется с хвоста, и так она не теряется за заметкой снимка."""
    cap = " ".join(str(caption or "").split())
    if not cap:
        return (notes or "")[:limit]
    head = f"подпись: «{cap[:80]}»"
    rest = str(notes or "").strip()
    return (head + (" | " + rest if rest else ""))[:limit]
