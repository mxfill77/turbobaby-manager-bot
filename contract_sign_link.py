# -*- coding: utf-8 -*-
"""ESIGNLINK2510 — одна ссылка клиенту на подпись и рядом правка договора (команда Splinter «договор»).

ЗАЧЕМ. Слово владельца 25.10.2026: «надо что в контрактах вот такая ссылка приходила на подпись и остальные не надо
… а то путаницу, и ссылочка на редактирования контракта рядом была». «Такая ссылка» — ссылка веб-приложения TB e-Sign
(`…/exec?a=sign&d=<id документа>&k=<токен>&who=client`): её получает группа контрактов, токен — HMAC от секрета
TB e-Sign, посчитать её здесь нельзя. С TB e-Sign 0.2.2 она лежит в реестре подписей (колонка «Ссылка клиенту на
подпись»), и дверь моста `contract_find` отдаёт её полем `sign_url`, а «Ссылку на документ» — полем `doc_url`.

ПОЧЕМУ ДВА СООБЩЕНИЯ. Строка реестра появляется не сразу: сканер TB e-Sign берёт документ из папки договоров раз в
минуту после 45 с тишины, то есть через ~1–2 мин после `make_contract`. Поэтому Splinter сразу отвечает «договор
готов» со ссылкой на правку, а ссылку на подпись досылает отдельным сообщением, когда она появится (опрос
`contract_find(doc_id=…)` по расписанию `offsets`, потолок WAIT_S). Не дождался — говорит, что ссылка будет в
группе контрактов, и ничего не выдумывает.

ЧТО ЗДЕСЬ. Только решения и слова, без сети и файлов: `doc_id_of` (id документа из ответа make_contract),
`sign_url_ok` (ссылка — та самая ссылка TB e-Sign ЭТОГО договора), `verdict` (ответ двери → послать / подписан /
стоп / ждать), тексты сообщений. Опрос и отправка — в `splinter.py` (`_contract_sign_link_follow`). Импорты — ровно
`re` и `urllib.parse` (страж — ast в тесте).

ЗАМОК ОТ ЧУЖОЙ ССЫЛКИ. Посылается только ссылка, у которой хост script.google.com, путь веб-приложения (…/macros/…/
exec), `a=sign`, `who=client`, непустой `k` и `d` == id ЭТОГО документа; всё прочее (прямая ссылка BoldSign, ссылка
агента, ссылка другого договора, пробелы внутри) — стоп с причиной, а не отправка. Ссылок у договора в реестре
несколько разных — тоже стоп. Ручка в splinter — `CONTRACT_SIGN_LINK` (по умолчанию ВЫКЛ: ответ «договор готов»
прежний байт-в-байт, модуль не импортируется)."""
import re
from urllib.parse import parse_qs, urlsplit

FLAG = "CONTRACT_SIGN_LINK"

WAIT_S = 300        # потолок ожидания: строка реестра появляется через ~1–2 мин, запас — на задержку триггера
FIRST_GAP_S = 60    # после мгновенной проверки (пересобранный договор уже в реестре) следующая — через минуту
STEP_S = 30         # дальше — раз в 30 с: ≤ 10 чтений реестра на договор
FIND_LIMIT = 5      # строк одного документа больше одной быть не должно; 5 — чтобы увидеть дубли

SIGN_LABEL = "✍️ Ссылка клиенту на подпись"
EDIT_LABEL = "✏️ Редактировать договор"
TO_GROUP = "ссылка будет в группе контрактов"

# отказы моста, которые за минуты не пройдут: ждать бессмысленно — сразу сказать
STOP_ERRORS = {
    "no_filter": "мост не знает поиска по документу (выкладка моста ESIGNLINK2510 не сделана)",
    "unknown_action": "в мосте нет двери договоров",
    "bad_doc_id": "мост не принял id документа",
    "no_column": "в реестре подписей нет нужной колонки",
    "no_registry_config": "мост не нашёл реестр подписей",
    "registry_ambiguous": "мост нашёл несколько реестров подписей",
    "no_registry_sheet": "в реестре подписей нет листа «Реестр»",
    "unauthorized": "мост отказал в доступе",
}

_DOC_IN_URL = re.compile(r"/d/([-\w]{25,})")
_BARE_ID = re.compile(r"^[-\w]{25,}$")


def offsets(wait_s=WAIT_S, first_gap_s=FIRST_GAP_S, step_s=STEP_S):
    """Моменты чтения реестра от начала ожидания, с: 0, first_gap, first_gap+step, … не позже wait_s."""
    out, t = [0], first_gap_s
    while step_s > 0 and t <= wait_s:
        out.append(t)
        t += step_s
    return out


def doc_id_of(file_id="", url=""):
    """id Google-документа из ответа make_contract: `file_id`, иначе `/d/<id>` из `url`. Не разобран → ''."""
    fid = str(file_id or "").strip()
    if _BARE_ID.match(fid):
        return fid
    m = _DOC_IN_URL.search(str(url or ""))
    return m.group(1) if m else ""


def _one(q, key):
    vals = q.get(key) or []
    return vals[0] if len(vals) == 1 else None


def sign_url_ok(url, doc_id):
    """Ссылка — ссылка TB e-Sign клиенту на подпись ЭТОГО документа (см. «замок» в шапке модуля)."""
    s = str(url or "").strip()
    if not s or not doc_id or any(ch.isspace() for ch in s):
        return False
    try:
        u = urlsplit(s)
        q = parse_qs(u.query, keep_blank_values=True)
    except ValueError:
        return False
    if u.scheme != "https" or u.netloc != "script.google.com" or u.fragment:
        return False
    if "/macros/" not in u.path or not u.path.endswith("/exec"):
        return False
    return (_one(q, "a") == "sign" and _one(q, "who") == "client" and _one(q, "d") == doc_id
            and bool(_one(q, "k")))


def edit_url_ok(url, doc_id):
    """Ссылка на правку — Google-документ ЭТОГО id (docs/drive.google.com, путь …/d/<id>…). Предикат: «не та или не
    разобрана» и есть честное «нет», поэтому путь разбирается по сегментам, без шаблона."""
    s = str(url or "").strip()
    if not s or not doc_id or any(ch.isspace() for ch in s):
        return False
    try:
        u = urlsplit(s)
    except ValueError:
        return False
    parts = u.path.split("/")
    after_d = parts[parts.index("d") + 1] if "d" in parts[:-1] else None
    return u.scheme == "https" and u.netloc in ("docs.google.com", "drive.google.com") and after_d == doc_id


def verdict(resp, doc_id):
    """Ответ `contract_find(doc_id=…)` → {"act": "send" | "signed" | "stop" | "wait", "why": слова[, "url", "edit"]}.

    send — ровно одна годная ссылка у неподписанной строки ЭТОГО документа; signed — строки документа есть и все
    подписаны (ссылка не нужна); stop — ждать бессмысленно (мост без поиска по документу, реестр без колонки
    ссылки, ссылка не та, ссылок несколько); wait — строки ещё нет / ссылки в ней ещё нет / сбой чтения."""
    if not isinstance(resp, dict):
        return {"act": "wait", "why": "мост ответил не словарём"}
    if not resp.get("ok"):
        err = str(resp.get("error") or "нет ответа")
        if err in STOP_ERRORS:
            return {"act": "stop", "why": STOP_ERRORS[err]}
        return {"act": "wait", "why": "реестр не прочитан (%s)" % err}
    cols = resp.get("optional_columns")
    if not isinstance(cols, dict):
        return {"act": "stop", "why": "мост не отдаёт ссылку на подпись (дверь до ESIGNLINK2510)"}
    if cols.get("sign_url") is not True:
        return {"act": "stop", "why": "в реестре подписей нет колонки «Ссылка клиенту на подпись» (TB e-Sign до 0.2.2)"}
    items = resp.get("items") if isinstance(resp.get("items"), list) else []
    rows = [r for r in items if isinstance(r, dict) and str(r.get("doc_id") or "").strip() == doc_id]
    if not rows:
        return {"act": "wait", "why": "договора ещё нет в реестре подписей"}
    open_rows = [r for r in rows if r.get("signed") is not True]
    if not open_rows:
        return {"act": "signed", "why": "договор уже подписан"}
    urls = sorted({str(r.get("sign_url") or "").strip() for r in open_rows} - {""})
    if len(urls) > 1:
        return {"act": "stop", "why": "в реестре у договора несколько разных ссылок на подпись"}
    if urls and not sign_url_ok(urls[0], doc_id):
        return {"act": "stop", "why": "ссылка в реестре не похожа на ссылку TB e-Sign этого договора"}
    if not urls:
        return {"act": "wait", "why": "строка договора в реестре есть, ссылки на подпись в ней ещё нет"}
    row = next(r for r in open_rows if str(r.get("sign_url") or "").strip() == urls[0])
    edit = str(row.get("doc_url") or "").strip()
    return {"act": "send", "why": "ссылка из реестра подписей", "url": urls[0],
            "edit": edit if edit_url_ok(edit, doc_id) else ""}


def _named(name):
    n = str(name or "").strip()
    return " «%s»" % n if n else ""


def ready_text(name, edit_url, reminder, has_doc_id):
    """Первое сообщение: договор готов, ссылка на правку; ссылка на подпись — следующим сообщением."""
    lines = ["🐀 Splinter", "✅ Договор готов%s." % _named(name)]
    if str(edit_url or "").strip():
        lines += [EDIT_LABEL + ":", str(edit_url).strip()]
    if has_doc_id:
        lines.append("✍️ Ссылку клиенту на подпись пришлю следующим сообщением, как только договор появится "
                     "в реестре подписей (обычно 1–2 мин).")
    else:
        lines.append("✍️ id документа в ответе моста не разобран — %s." % TO_GROUP)
    if str(reminder or "").strip():
        lines.append(str(reminder).strip())
    return "\n".join(lines)


def link_text(name, sign_url, edit_url):
    """Досылка: две ссылки рядом — клиенту на подпись и правка договора."""
    lines = ["🐀 Splinter", SIGN_LABEL + "%s:" % _named(name), sign_url]
    if str(edit_url or "").strip():
        lines += [EDIT_LABEL + ":", str(edit_url).strip()]
    return "\n".join(lines)


def signed_text(name):
    return "🐀 Splinter\nℹ️ Договор%s уже подписан — ссылка на подпись не нужна." % _named(name)


def fail_text(name, why):
    return "🐀 Splinter\n⚠️ Ссылку клиенту на подпись%s не прислал: %s — %s." % (_named(name), why, TO_GROUP)


def timeout_why(last, wait_s=WAIT_S):
    minutes = max(1, int(round(wait_s / 60.0)))
    return "за %d мин не дождался (%s)" % (minutes, last or "договора нет в реестре подписей")


def text_for(v, name, edit_fallback=""):
    """Итог ожидания → текст досылки."""
    if v.get("act") == "send":
        return link_text(name, v["url"], v.get("edit") or edit_fallback)
    if v.get("act") == "signed":
        return signed_text(name)
    return fail_text(name, v.get("why") or "причина не названа")
