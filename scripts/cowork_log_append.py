#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cowork_log_append.py — Cowork дописывает запись в ОБЩИЙ МОЗГ (Brain-док cowork_log) через Bridge.

ЗАЧЕМ: закрыть слепую зону «штаб не видит Cowork» — Cowork в конце КАЖДОЙ своей сессии вызывает
этот скрипт с краткой записью, и она появляется в cowork_log (Drive), который читает штаб.

КАК: self-contained (requests + stdlib; БЕЗ dotenv-зависимости — .env парсится сам).
write_doc на Bridge умеет только ПЕРЕЗАПИСЬ → дописываем через read-modify-write:
read_doc(cowork_log) → новая строка ПРЕПЕНДится сверху (свежее сверху, как в cc_log) → write_doc.

УСТАНОВКА (разово): положить рядом .env с двумя строками BRIDGE_URL=… и BRIDGE_TOKEN=…
(значения — те же, что в .env manager-bot на VPS; Филипп/штаб перенесёт).

ЗАПУСК:
  python cowork_log_append.py "коротко что сделал в этой сессии"
  echo "текст" | python cowork_log_append.py
Префикс DONE/NOTE можно не писать — добавится "DONE <UTC>:" автоматически (или сохранится свой).
"""
import os
import sys
import datetime

try:
    import requests
except ImportError:
    sys.stderr.write("Нужен пакет requests: pip install requests\n")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
DOC_NAME = "cowork_log"
HTTP_TIMEOUT = 60


def _load_creds():
    """BRIDGE_URL/BRIDGE_TOKEN из .env рядом со скриптом; фоллбэк — окружение. Без dotenv."""
    env = {}
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    url = env.get("BRIDGE_URL") or os.environ.get("BRIDGE_URL")
    tok = env.get("BRIDGE_TOKEN") or os.environ.get("BRIDGE_TOKEN")
    return url, tok


def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        sys.stderr.write("Пусто — нечего записывать. Передай текст аргументом или через stdin.\n")
        sys.exit(1)

    utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = text if text[:5] in ("DONE ", "NOTE ") else f"DONE {utc}: {text}"

    url, tok = _load_creds()
    if not url or not tok:
        sys.stderr.write("НЕТ BRIDGE_URL/BRIDGE_TOKEN (.env рядом со скриптом). Запись НЕ потеряна:\n" + entry + "\n")
        sys.exit(1)

    # read (не перезатираем, если чтение не удалось — защита от затирки)
    try:
        r = requests.get(url, params={"token": tok, "action": "read_doc", "name": DOC_NAME}, timeout=HTTP_TIMEOUT)
        data = r.json()
    except Exception as e:
        sys.stderr.write(f"read_doc упал ({e}). Запись НЕ потеряна:\n{entry}\n")
        sys.exit(1)
    if not data.get("ok"):
        sys.stderr.write(f"read_doc error: {data.get('error')}. Запись НЕ потеряна:\n{entry}\n")
        sys.exit(1)

    old = data.get("text") or ""
    new_body = entry + "\n" + old

    # write (read-modify-write: свежее сверху)
    try:
        w = requests.post(url, json={"token": tok, "action": "write_doc", "name": DOC_NAME, "text": new_body},
                          timeout=HTTP_TIMEOUT)
        wd = w.json()
    except Exception as e:
        sys.stderr.write(f"write_doc упал ({e}). Запись НЕ потеряна:\n{entry}\n")
        sys.exit(1)

    if wd.get("ok"):
        print("OK → cowork_log: " + entry)
    else:
        sys.stderr.write(f"write_doc error: {wd.get('error')}. Запись НЕ потеряна:\n{entry}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
