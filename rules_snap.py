"""Снимок узла мозга business_rules для Splinter (02.10.2026, задание Штаба 0119-77t.0210, SPLDELIVERYASK0210).

До этой правки Splinter узел business_rules не читал вовсе (разведка 0072, перепроверено 02.10: ни
`splinter.py`, ни `bot.py`, ни `claude_client.py`, ни `topic_decider.py` имени узла не содержат), и
правила владельца 30.09.2026-4…-7 до агента не доезжали.

Как устроено:
  * `refresh(read)` — одно чтение узла (`read()` → {ok, text}); удача → снимок на диск атомарно
    (текст, время чтения, sha, длина); НЕУДАЧА НЕ ЗАТИРАЕТ прежний снимок — в файл ложатся только
    время и причина сбоя рядом с прежним текстом;
  * `prompt_block(now)` — выжимка для промпта: блоки «РЕШЕНИЕ/РЕШЕНИЯ ВЛАДЕЛЬЦА», где речь о Splinter,
    сотрудниках офиса, Пыме, «Агентах» или Delivery, — только заголовок и раздел «ПРАВИЛО», свежие
    сверху, не длиннее `SPLINTER_RULES_MAX_CHARS` (по умолчанию 8000). В шапке — время снимка и
    ВОЗРАСТ, при сбое последнего чтения — слова «показан прежний снимок». Снимка нет → None
    («правил не знаю», а не пустая строка).
Выключатель `SPLINTER_RULES_FEED` (по умолчанию ВЫКЛЮЧЕН): выкл. → узел не читается, промпты байт в байт
прежние.
"""
import hashlib
import json
import os
import re
import time

FLAG = "SPLINTER_RULES_FEED"
DOC = "business_rules"            # ключ манифеста моста (brain_writer.resolve_name("KB_business_rules"))
MAX_CHARS_DEFAULT = 8000          # замер 02.10: узел 133 970 символов → 7 блоков, 7 421 символ выжимки
REFRESH_S = 1800                  # такт чтения узла (30 мин) — правило владельца живёт сутками, не минутами
TOPIC_WORDS = ("splinter", "сотрудник", "пым", "агент", "delivery", "тайц")
_HEAD = re.compile(r"^РЕШЕНИ[ЕЯ] ВЛАДЕЛЬЦА\b")


def enabled():
    return str(os.getenv(FLAG, "0")).strip().lower() in ("1", "true", "yes", "on")


def max_chars():
    try:
        v = int(os.getenv("SPLINTER_RULES_MAX_CHARS", "") or MAX_CHARS_DEFAULT)
        return v if v > 0 else MAX_CHARS_DEFAULT
    except (TypeError, ValueError):
        return MAX_CHARS_DEFAULT


def snap_path():
    return os.getenv("SPLINTER_RULES_SNAP") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "business_rules_snap.json")


def load(path=None):
    try:
        with open(path or snap_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _save(d, path=None):
    p = path or snap_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False)
    os.replace(tmp, p)


def refresh(read, now=None, path=None):
    """Одно чтение узла. Возврат: {"ok": bool, "why": str, "len": int}. Не бросает."""
    now = time.time() if now is None else now
    prev = load(path) or {}
    try:
        r = read()
        text = (r or {}).get("text") or (r or {}).get("content") or "" if (r or {}).get("ok") else ""
        why = "" if text.strip() else ("мост: не ok" if not (r or {}).get("ok") else "пустой текст")
    except Exception as e:
        text, why = "", f"чтение упало ({type(e).__name__})"
    if why:
        prev.update({"fail_ts": now, "fail_why": why})
        try:
            _save(prev, path)
        except Exception:
            pass
        return {"ok": False, "why": why, "len": len(prev.get("text") or "")}
    d = {"text": text, "read_ts": now, "len": len(text),
         "sha": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]}
    _save(d, path)
    return {"ok": True, "why": "", "len": len(text)}


def extract(text):
    """Блоки решений владельца о Splinter / сотрудниках офиса: заголовок + раздел «ПРАВИЛО». Свежие сверху."""
    blocks, cur = [], None
    for line in (text or "").splitlines():
        if _HEAD.match(line.strip()):
            cur = [line.strip()]
            blocks.append(cur)
        elif cur is not None:
            cur.append(line)
    out = []
    for b in blocks:
        title, body, keep, rule = b[0], b[1:], [], False
        for ln in body:
            s = ln.strip()
            if s.startswith("- "):
                rule = s.startswith("- ПРАВИЛО")
                if rule:
                    continue
            if rule and s:
                keep.append(s)
        if not keep:
            continue
        blob = (title + " " + " ".join(keep)).lower()
        if any(w in blob for w in TOPIC_WORDS):
            out.append(title + "\n" + "\n".join(keep))
    return list(reversed(out))


def _age(sec):
    sec = max(0, int(sec))
    h, m = sec // 3600, (sec % 3600) // 60
    return f"{h} ч {m} мин" if h else f"{m} мин"


def prompt_block(now=None, path=None, cap=None):
    """Выжимка для промпта решателя и мозга. Выключено или снимка нет → None."""
    if not enabled():
        return None
    d = load(path)
    if not d or not d.get("text"):
        return None
    now = time.time() if now is None else now
    cap = cap or max_chars()
    ts = float(d.get("read_ts") or 0)
    head = (f"## ПРАВИЛА ВЛАДЕЛЬЦА (узел мозга business_rules, снимок "
            f"{time.strftime('%d.%m %H:%M', time.gmtime(ts))} UTC, возраст {_age(now - ts)})")
    if float(d.get("fail_ts") or 0) > ts:
        head += (f"; последнее чтение не удалось {time.strftime('%d.%m %H:%M', time.gmtime(d['fail_ts']))}"
                 f" UTC — показан прежний снимок")
    parts, used, total = [], 0, extract(d["text"])
    for blk in total:
        if used + len(blk) + 2 > cap:
            continue                       # длинный блок не вытесняет короткие следом

        parts.append(blk)
        used += len(blk) + 2
    tail = (f"\n(показано правил {len(parts)} из {len(total)}; узел — {d.get('len') or len(d['text'])} символов. "
            f"Правило владельца сильнее твоей догадки; противоречит ему — спроси, а не действуй.)")
    return head + "\n" + "\n\n".join(parts) + tail
