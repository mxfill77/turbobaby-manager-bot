"""Решатель темы обслуживания в ТЕНИ (01.10.2026, задание Штаба 0094-76k, SPLDECIDER0110).

ЗАЧЕМ. После ленты темы (SPLTOPICFEED0110) мозг помнит тему, но зовётся только на обращение
владельца/Пыма: на остальное отвечают шесть жёстких перехватов. Шаг 2 агентного контура
(SPLAGENTMAP0110 п.5, части 3–4): на КАЖДОЕ входящее темы модель выбирает ровно одно действие по
`topic_context`, а правила КОДОМ поверх её ответа не дают записать мимо гейтов и спросить второй раз.

ДЕЙСТВИЯ (JSON ровно одного):
  записать{что, км, источник=mid} · спросить{вопрос, ждём_что, от_кого} · ответить{текст}
  · позвать{кого: Пым|владелец, зачем} · ничего{почему}
Непарсимый / не по схеме ответ → «ничего: не понял», а не догадка.

ПРАВИЛА КОДОМ (`rules`, модель о них не решает; порядок = приоритет):
  без_mid      записать без mid основания (или mid не из этого сообщения и не из ленты темы) → отказ
  нет_числа    записать пробег без числа → отказ
  убывание     пробег ниже записанного → позвать (Пым)
  потолок      разрыв вверх больше `odo_ceiling` → позвать (Пым)
  доверие      «да»/число пробега от доверенного (Пым/владелец) → дверь `_odo_confirmed`;
               от сотрудника (или работа ТО, E2b) → дверь «кнопка Пыма», не прямая запись
  второй_вопрос спросить, когда открыт вопрос того же вида → отказ

ТЕНЬ. Решатель НИЧЕГО не пишет и не шлёт: решение и итог правил — строка журнала и событие ленты
вида `decision` (контекст мозга такие события не видит: `topic_feed.read` их пропускает). Прежний
путь не меняется. Выключатель `TOPIC_DECIDER_SHADOW`, по умолчанию ВЫКЛЮЧЕН (нет флага → ни
снимка, ни вызова модели, ни строки).
"""
import json
import os
import re

import odo_ceiling

FLAG = "TOPIC_DECIDER_SHADOW"
ACTIONS = ("записать", "спросить", "ответить", "позвать", "ничего")
CALLEES = ("Пым", "владелец")
TRUSTED_ROLES = ("pym", "owner")
DOOR_ODO = "_odo_confirmed"
DOOR_PYM = "кнопка Пыма"
NOT_UNDERSTOOD = {"действие": "ничего", "почему": "не понял"}

SYSTEM = (
    "Ты — решатель темы обслуживания байка TurboBaby. На КАЖДОЕ входящее сообщение темы выбери "
    "РОВНО ОДНО действие и верни ТОЛЬКО JSON-объект без пояснений и без кода вокруг.\n"
    "Действия:\n"
    '{"действие":"записать","что":"пробег"|"<работа>","км":<целое>,"источник":<mid сообщения-основания>}\n'
    '{"действие":"спросить","вопрос":"<один вопрос>","ждём_что":"пробег"|"работы"|"<что>","от_кого":"<роль>"}\n'
    '{"действие":"ответить","текст":"<коротко>"}\n'
    '{"действие":"позвать","кого":"Пым"|"владелец","зачем":"<коротко>"}\n'
    '{"действие":"ничего","почему":"<коротко>"}\n'
    "Опирайся на ЛЕНТУ ТЕМЫ: не переспрашивай отвеченное; реплай на открытый вопрос — ответ на него. "
    "Источник записи — #id сообщения, где человек назвал число или сказал «да». Не знаешь — «ничего»."
)


def enabled():
    """`TOPIC_DECIDER_SHADOW=1` → тень включена. Нет флага / 0 → выключена (по умолчанию)."""
    return str(os.getenv(FLAG, "0")).strip().lower() in ("1", "true", "yes", "on")


def _int(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str) and re.fullmatch(r"\s*#?\d{1,9}\s*", x):
        return int(x.strip().lstrip("#"))
    return None


def _txt(x):
    return x.strip() if isinstance(x, str) and x.strip() else None


def parse(raw):
    """Ответ модели → действие. Принимается только JSON-объект (допустима обёртка ```json).
    Любое иное (пусто, текст, два объекта, нет поля, чужое действие) → «ничего: не понял»."""
    if not isinstance(raw, str):
        return dict(NOT_UNDERSTOOD)
    s = raw.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    try:
        d = json.loads(s)
    except Exception:
        return dict(NOT_UNDERSTOOD)
    if not isinstance(d, dict):
        return dict(NOT_UNDERSTOOD)
    a = d.get("действие")
    if a == "записать":
        what, src = _txt(d.get("что")), _int(d.get("источник"))
        km = _int(d.get("км")) if d.get("км") is not None else None
        if not what:
            return dict(NOT_UNDERSTOOD)
        return {"действие": a, "что": what, "км": km, "источник": src}
    if a == "спросить":
        q, w = _txt(d.get("вопрос")), _txt(d.get("ждём_что"))
        if not q or not w:
            return dict(NOT_UNDERSTOOD)
        return {"действие": a, "вопрос": q, "ждём_что": w, "от_кого": _txt(d.get("от_кого")) or ""}
    if a == "ответить":
        t = _txt(d.get("текст"))
        return {"действие": a, "текст": t} if t else dict(NOT_UNDERSTOOD)
    if a == "позвать":
        who, why = _txt(d.get("кого")), _txt(d.get("зачем")) or ""
        return {"действие": a, "кого": who, "зачем": why} if who in CALLEES else dict(NOT_UNDERSTOOD)
    if a == "ничего":
        return {"действие": a, "почему": _txt(d.get("почему")) or ""}
    return dict(NOT_UNDERSTOOD)


def ask_kind(w):
    """Вид ожидаемого ответа: «пробег» (км/одометр/mileage) · «работы» · иначе само слово."""
    s = str(w or "").strip().lower()
    if any(k in s for k in ("пробег", "км", "одометр", "mileage", "odo")):
        return "пробег"
    if any(k in s for k in ("работ", "works", "ремонт")):
        return "работы"
    return s


def _is_mileage(what):
    return ask_kind(what) == "пробег"


def rules(dec, facts):
    """Правила кодом поверх решения модели. `facts`:
      mid (int) · role (staff|pym|owner|bot) · trusted (bool, `_act_trusted` автора)
      known (dict mid → роль автора события ленты) · last_km (записанный пробег или None)
      cur_km (текущий из таблицы или None) · ceiling (порог км или 0)
      open_kinds (dict вид → mid открытого вопроса)
    Возврат: {"итог": действие, "правило": имя сработавшего ('' — пропущено как есть), "дверь": ''|…}."""
    a = dec.get("действие")
    if a == "записать":
        src = dec.get("источник")
        known = facts.get("known") or {}
        if src is None or (src != facts.get("mid") and src not in known):
            return {"итог": {"действие": "ничего", "почему": "нет mid основания — запись отклонена"},
                    "правило": "без_mid", "дверь": ""}
        src_role = facts.get("role") if src == facts.get("mid") else known.get(src)
        src_trusted = (bool(facts.get("trusted")) if src == facts.get("mid")
                       else src_role in TRUSTED_ROLES)
        if _is_mileage(dec.get("что")):
            km = dec.get("км")
            if km is None or km <= 0:
                return {"итог": {"действие": "ничего", "почему": "пробег без числа — запись отклонена"},
                        "правило": "нет_числа", "дверь": ""}
            last = facts.get("last_km")
            if last is not None and km < int(last):
                return {"итог": {"действие": "позвать", "кого": "Пым",
                                 "зачем": f"пробег {km} ниже записанного {int(last)}"},
                        "правило": "убывание", "дверь": ""}
            cur = facts.get("cur_km") if facts.get("cur_km") is not None else last
            v = odo_ceiling.verdict(km, cur, facts.get("ceiling") or 0)
            if v.get("state") == odo_ceiling.STATE_ASK:
                return {"итог": {"действие": "позвать", "кого": "Пым",
                                 "зачем": f"пробег {km} выше потолка: разрыв {v.get('gap')} > {v.get('limit')}"},
                        "правило": "потолок", "дверь": ""}
            door = DOOR_ODO if src_trusted else DOOR_PYM
            return {"итог": dict(dec), "правило": "доверие" if not src_trusted else "", "дверь": door}
        # работа ТО — всегда через ТО-заявку и кнопку Пыма (E2b), кто бы ни назвал
        return {"итог": dict(dec), "правило": "", "дверь": DOOR_PYM}
    if a == "спросить":
        k = ask_kind(dec.get("ждём_что"))
        opened = (facts.get("open_kinds") or {})
        if k in opened:
            return {"итог": {"действие": "ничего",
                             "почему": f"вопрос вида «{k}» уже открыт (#{opened[k]}) — второй не задаём"},
                    "правило": "второй_вопрос", "дверь": ""}
        return {"итог": dict(dec), "правило": "", "дверь": ""}
    return {"итог": dict(dec), "правило": "", "дверь": ""}


def user_prompt(ctx, facts, kind, text_len):
    """Вход модели: контекст темы + факты кодом о самом сообщении (без текста людей в журнале)."""
    opened = ", ".join(f"{k} #{v}" for k, v in (facts.get("open_kinds") or {}).items()) or "нет"
    return (f"{ctx or '## ЛЕНТА ЭТОЙ ТЕМЫ: контекст не собран'}\n\n"
            f"## ВХОДЯЩЕЕ\nсообщение #{facts.get('mid')} · вид {kind} · автор {facts.get('role')} "
            f"(доверенный: {'да' if facts.get('trusted') else 'нет'}) · реплай на "
            f"#{facts.get('reply_to') if facts.get('reply_to') is not None else '—'} · символов {text_len}\n"
            f"Открытые вопросы по видам: {opened}\n"
            f"Записанный пробег: {facts.get('last_km') if facts.get('last_km') is not None else 'неизвестен'}\n"
            "Ответ — ОДИН JSON-объект.")


def say(verdict, mid):
    """Строка журнала: только действие, числа, id и имя правила — без текста людей и модели."""
    it = verdict.get("итог") or {}
    a = it.get("действие")
    bits = [f"#{mid} → {a}"]
    if a == "записать":
        bits.append(f"{it.get('что')} {it.get('км')} · основание #{it.get('источник')} · дверь {verdict.get('дверь')}")
    elif a == "спросить":
        bits.append(f"ждём {ask_kind(it.get('ждём_что'))}")
    elif a == "позвать":
        bits.append(f"{it.get('кого')}")
    elif a == "ничего":
        bits.append(f"символов причины {len(str(it.get('почему') or ''))}")
    elif a == "ответить":
        bits.append(f"символов {len(str(it.get('текст') or ''))}")
    if verdict.get("правило"):
        bits.append(f"правило {verdict['правило']} (модель: {verdict.get('модель')})")
    return "  🧠 решатель (тень): " + " · ".join(bits)


# ===================== БОЕВОЙ РЕЖИМ (01.10.2026, задание Штаба 0099-76p, SPLLIVEMODE0110) =========
# Флаг `TOPIC_DECIDER_LIVE` (по умолчанию ВЫКЛЮЧЕН → путь равен 05efc4b). Включён: на сообщение темы,
# не обращённое к Splinter, решение ИСПОЛНЯЕТСЯ через прежние двери, а перехваты на нём молчат.
# Сбой модели / таймаут / ответ не по схеме → прежний путь. Вмешался человек → тема на паузе (правило
# владельца 30.09.2026-7, п.4). Чистые части — здесь; проводка — `splinter.decider_live`.
LIVE_FLAG = "TOPIC_DECIDER_LIVE"
LIVE_ACTIONS = ("записать", "спросить", "позвать", "ничего")  # «ответить» в бою НЕ исполняется → прежний путь
REJECT_ACTIONS = ("fix", "agn")      # кнопки «исправить»/«нет» прежних дверей (`svc:<действие>:<метка>`)
CALL_WINDOW_S_DEFAULT = 3 * 3600     # зов Пыма — не чаще раза на тему за окно (как срок вопроса L)
TIMEOUT_S_DEFAULT = 25.0

LIVE_SYSTEM = SYSTEM + (
    "\nЕсли сообщение — РЕПЛАЙ человека на сообщение Splinter и человек его ПОПРАВЛЯЕТ (не то число, "
    'не тот байк, не так понял), добавь в объект поле "поправка": true.')


# ВОПРОС СОТРУДНИКАМ ОФИСА (02.10.2026, задание Штаба 0119-77t, SPLDELIVERYASK0210). Добавка к системному
# тексту боя — ТОЛЬКО при `SPLINTER_ASK_STAFF=1` (`splinter._decider_live_system`); выкл. → текст прежний.
LIVE_STAFF_ADD = (
    "\nВопрос сотрудникам офиса: если вопрос о состоянии или готовности байка и его надо задать "
    'сотрудникам офиса, добавь к «спросить» поля "вид":"байк", "вопрос_th":"<тот же вопрос по-тайски, '
    'вежливо, без давления>", "срочность":"для ясности"|"клиент интересуется" («клиент интересуется» — '
    'только если клиент ждёт ответа сейчас). Вопрос о цене, брони или сложности, которую решают менеджеры, — '
    '"вид":"цена"|"бронь"|"сложность": он уйдёт в группу «TurboBaby · Агенты», не сотрудникам офиса.')
STAFF_FIELDS = ("вид", "вопрос_th", "срочность")


def live_enabled():
    """`TOPIC_DECIDER_LIVE=1` → боевой режим. Нет флага / 0 → выключен (по умолчанию)."""
    return str(os.getenv(LIVE_FLAG, "0")).strip().lower() in ("1", "true", "yes", "on")


def _env_num(name, default):
    try:
        v = float(os.getenv(name, "") or default)
        return v if v > 0 else default
    except Exception:
        return default


def live_timeout():
    return _env_num("TOPIC_DECIDER_TIMEOUT_S", TIMEOUT_S_DEFAULT)


def call_window():
    return _env_num("TOPIC_DECIDER_CALL_WINDOW_S", CALL_WINDOW_S_DEFAULT)


def _unwrap(raw):
    s = raw.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    return m.group(1) if m else s


def parse_checked(raw):
    """(действие, причина_сбоя). Причина '' — модель ответила по схеме; иначе — почему прежний путь.
    «ничего: не понял», сказанное САМОЙ моделью объектом, — ответ, а не сбой. Поле «поправка» (bool)
    переносится в действие, только если модель поставила его ровно `true`."""
    if raw is None:
        return dict(NOT_UNDERSTOOD), "модель не ответила"
    if not isinstance(raw, str) or not raw.strip():
        return dict(NOT_UNDERSTOOD), "пустой ответ модели"
    d = parse(raw)
    try:
        j = json.loads(_unwrap(raw))
    except Exception:
        j = None
    if d == NOT_UNDERSTOOD and not (isinstance(j, dict) and j.get("действие") == "ничего"):
        return d, "ответ модели не JSON по схеме"
    if isinstance(j, dict) and j.get("поправка") is True:
        d["поправка"] = True
    if isinstance(j, dict) and d.get("действие") == "спросить":      # поля вопроса сотрудникам (если даны)
        for f in STAFF_FIELDS:
            if isinstance(j.get(f), str) and j[f].strip():
                d[f] = j[f].strip()[:400]
    return d, ""


def pause_reason(ev, decider_mids):
    """Признак вмешательства человека — из СОБЫТИЯ и разбора решателя, не из совпадения слов.
    ev: {вид: кнопка|реплай, действие: svc-действие кнопки, на: mid сообщения, к которому кнопка/реплай,
         человек: bool, поправка: bool — флаг разбора решателя}. `decider_mids` — mid сообщений решателя.
    Возврат: причина паузы или '' (паузы нет)."""
    if not ev.get("человек") or ev.get("на") is None or ev.get("на") not in decider_mids:
        return ""
    if ev.get("вид") == "кнопка" and ev.get("действие") in REJECT_ACTIONS:
        return "человек отклонил кнопку решателя"
    if ev.get("вид") == "реплай" and ev.get("поправка") is True:
        return "человек поправил решателя ответом на его сообщение"
    return ""


def call_allowed(last_ts, now, window):
    """Зов Пыма по теме — не чаще раза за окно."""
    return last_ts is None or (now - float(last_ts)) >= window


def live_say(verdict, mid, door):
    """Строка журнала боевого решения: mid, действие, правило, дверь — без текста людей и модели."""
    it = verdict.get("итог") or {}
    a = it.get("действие")
    bits = [f"#{mid} → {a}"]
    if a == "записать":
        bits.append(f"{it.get('что') if _is_mileage(it.get('что')) else 'работа'} {it.get('км')} "
                    f"· основание #{it.get('источник')}")
    elif a == "спросить":
        bits.append(f"ждём {ask_kind(it.get('ждём_что'))}")
    elif a == "позвать":
        bits.append(f"{it.get('кого')}")
    bits.append(f"правило {verdict.get('правило') or '—'}")
    bits.append(f"дверь {door or '—'}")
    return "  🧠 решатель (бой): " + " · ".join(bits)
