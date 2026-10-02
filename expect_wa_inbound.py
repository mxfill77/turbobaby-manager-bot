#!/usr/bin/env python3
"""О10 — РУКИ ПРИБОРА «ВХОД WhatsApp»: 360dialog шлёт события НАМ, и номер подключён (02.10.2026,
задание 0114-77n).

ПОЧЕМУ БЕЗ ПОДСЧЁТОВ. Молчание входа нельзя отличить от тишины клиентов по счёту сообщений: ночью
и в мёртвый вход приходит одинаково ноль. Поэтому прибор не считает строки очереди и не ждёт
«примерного момента», а раз в такт слоя ожиданий СПРАШИВАЕТ у 360dialog две настройки, от которых
доставка зависит целиком:
  адрес  — GET {API_BASE}/v1/configs/webhook → поле `url`; сверяется с НАШИМ адресом
           https://wa.turbophuket.com/wa-webhook/d360/<WA_D360_PATH_SECRET> (тот вход, который
           слушает wa-webhook и который прописан 01.10, WAD360APPLY0110);
  номер  — GET {API_BASE}/health_status → сущность PHONE_NUMBER, поле `can_send_message`
           (AVAILABLE / LIMITED — подключён, BLOCKED — нет; прочее — незнакомо).

КЛЮЧ И АДРЕС НЕ ПОКАЗЫВАЮТСЯ НИГДЕ. Из файла ключей берутся РОВНО два имени — ключ канала
`WA_D360_API_KEY` (тот, которым прописан вебхук и которым служба показа качает медиа) и секрет пути
`WA_D360_PATH_SECRET` (тот, что ждёт вход d360). Наружу уходят только «совпадает / не совпадает»,
какая часть адреса разошлась и короткие отпечатки sha256. Тело ответа 360dialog не печатается.

ТРИ ИСХОДА у каждой части, и «не ответил» — не «в порядке»: транспорт, HTTP-отказ, не-JSON,
незнакомая форма → НЕИЗВЕСТНО с причиной и адресом. Судья — `expectations.wa_inbound_state`.

Usage: venv/bin/python3 expect_wa_inbound.py [--root <дерево>]
  один прогон без отправки: строка исхода и сводка без значений. Два вызова чтения к 360dialog.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

API_BASE = "https://waba-v2.360dialog.io"           # тот же хост, что у wa_send / wa_tg_mirror
KEY_HEADER = "D360-API-KEY"
HOOK_PATH = "/v1/configs/webhook"
HEALTH_PATH = "/health_status"
# Наш публичный вход: Caddy wa.turbophuket.com → 127.0.0.1:8765, путь не срезается (WAD360APPLY0110).
PUBLIC_BASE = "https://wa.turbophuket.com"
D360_PATH = "/wa-webhook/d360/"
KEY_NAME, SECRET_NAME = "WA_D360_API_KEY", "WA_D360_PATH_SECRET"
CALL_TIMEOUT = 15.0                                   # плечо одного GET; вызовов в такт ровно два

NUMBER_OK = ("AVAILABLE", "LIMITED")
NUMBER_BAD = ("BLOCKED",)


def fp(text):
    """Отпечаток: 10 знаков sha256. По нему два адреса сравнимы глазами, восстановить нельзя."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:10]


def our_url(secret):
    return PUBLIC_BASE + D360_PATH + str(secret or "").strip()


def _norm(url):
    return str(url or "").strip().rstrip("/")


# ─────────────────────────────── ключи: ровно два имени ───────────────────────────────────
def keys_facts(path):
    """Файл ключей → {"key": str, "secret": str} без значений наружу | {"err", "addr"}.
    Последняя строка выигрывает — так же, как у load_dotenv служб."""
    try:
        from dotenv import dotenv_values
        if not os.path.exists(path):
            return {"err": "файла ключей нет", "addr": path}
        vals = dotenv_values(path)
    except Exception as e:                                           # noqa: BLE001
        return {"err": "файл ключей не прочитан (%s)" % type(e).__name__, "addr": path}
    return {"key": (vals.get(KEY_NAME) or "").strip(),
            "secret": (vals.get(SECRET_NAME) or "").strip(), "addr": path}


# ─────────────────────────────── вызов чтения ──────────────────────────────────────────────
def get_json(path, key, opener=None, timeout=CALL_TIMEOUT):
    """GET к 360dialog → (dict | None, причина-без-значений). Ключ — только в заголовке."""
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(API_BASE + path, method="GET",
                                 headers={KEY_HEADER: key, "Accept": "application/json"})
    addr = "GET %s%s" % (urlsplit(API_BASE).netloc, path)
    try:
        with opener(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read(65536)
    except urllib.error.HTTPError as e:
        why = "ключ не принят" if e.code in (401, 403) else (
            "адреса чтения нет" if e.code == 404 else "отказ сервера")
        return None, {"err": "%s (HTTP %s)" % (why, e.code), "addr": addr}
    except Exception as e:                                           # noqa: BLE001
        return None, {"err": "360dialog не ответил (%s)" % type(e).__name__, "addr": addr}
    if code != 200:
        return None, {"err": "ответ HTTP %s" % code, "addr": addr}
    try:
        body = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None, {"err": "ответ не JSON", "addr": addr}
    if not isinstance(body, dict):
        return None, {"err": "ответ не объект JSON", "addr": addr}
    return body, {"addr": addr}


def hook_facts(body, meta, secret):
    """Ответ про вебхук → {"set", "match", "host_ok", "path_ok", "fp_their", "fp_our"} | err."""
    if body is None:
        return dict(meta)
    url = body.get("url")
    if url is None and isinstance(body.get("webhook"), dict):
        url = body["webhook"].get("url")
    if url is None and "url" not in body:
        return {"err": "в ответе нет поля url (ключи: %s)" % ",".join(sorted(body)[:8]),
                "addr": meta.get("addr")}
    their, ours = _norm(url), _norm(our_url(secret))
    if not their:
        return {"set": False, "match": False, "fp_our": fp(ours), "addr": meta.get("addr")}
    t, o = urlsplit(their), urlsplit(ours)
    return {"set": True, "match": their == ours,
            "host_ok": (t.scheme, t.netloc.lower()) == (o.scheme, o.netloc.lower()),
            # путь — без секрета: вход d360 тот же, а секрет сверяется полным совпадением выше
            "path_ok": t.path.startswith(D360_PATH),
            "fp_their": fp(their), "fp_our": fp(ours), "addr": meta.get("addr")}


def number_facts(body, meta):
    """Ответ health_status → {"state": <can_send_message номера>, "errors": [...]} | err."""
    if body is None:
        return dict(meta)
    hs = body.get("health_status")
    if not isinstance(hs, dict):
        return {"err": "в ответе нет health_status (ключи: %s)" % ",".join(sorted(body)[:8]),
                "addr": meta.get("addr")}
    for ent in hs.get("entities") or []:
        if isinstance(ent, dict) and str(ent.get("entity_type") or "").upper() == "PHONE_NUMBER":
            errs = []
            for er in ent.get("errors") or []:
                if isinstance(er, dict):
                    errs.append("%s %s" % (er.get("error_code") or "?",
                                           str(er.get("error_description") or "")[:80]))
            return {"state": str(ent.get("can_send_message") or "").upper(),
                    "errors": errs[:3], "addr": meta.get("addr")}
    return {"err": "в health_status нет сущности PHONE_NUMBER", "addr": meta.get("addr")}


# ─────────────────────────────── сбор ─────────────────────────────────────────────────────
def facts(now=None, root=None, opener=None):
    """Факты О10. Нет ключа — к 360dialog не ходим вовсе (судить нечем — НЕИЗВЕСТНО)."""
    path = os.path.join(root or REPO, ".env")
    k = keys_facts(path)
    out = {"keys": {"err": k.get("err"), "addr": k.get("addr"),
                    "key": bool(k.get("key")), "secret": bool(k.get("secret"))}}
    if k.get("err") or not k.get("key"):
        return out
    body, meta = get_json(HOOK_PATH, k["key"], opener)
    out["hook"] = hook_facts(body, meta, k.get("secret")) if k.get("secret") else \
        {"err": "секрет пути %s не задан — нашего адреса не знаю" % SECRET_NAME, "addr": path}
    body, meta = get_json(HEALTH_PATH, k["key"], opener)
    out["number"] = number_facts(body, meta)
    return out


def main(argv=None):
    import expectations
    argv = list(sys.argv[1:] if argv is None else argv)
    root = argv[argv.index("--root") + 1] if "--root" in argv else None
    now = time.time()
    cfg = expectations.config(os.environ)
    f = facts(now, root=root)
    st, info = expectations.wa_inbound_state({"now": now, "wa_inbound": f}, cfg, now)
    print(expectations.wa_inbound_line(st, info))
    print(json.dumps({"keys": f.get("keys"), "hook": f.get("hook"), "number": f.get("number"),
                      "now": round(now, 1)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
