#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Шаг 1/7 родитель 185: read-only выгрузка cc_log через Bridge → /tmp/cclog_raw_185.txt (по образцу cowork_log_append)."""
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
HTTP_TIMEOUT = 60


def _load_creds():
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
    url, tok = _load_creds()
    if not url or not tok:
        sys.stderr.write("НЕТ BRIDGE_URL/BRIDGE_TOKEN в .env\n")
        sys.exit(1)
    r = requests.get(url, params={"token": tok, "action": "read_doc", "name": "cc_log"}, timeout=HTTP_TIMEOUT)
    data = r.json()
    if not data.get("ok"):
        sys.stderr.write(f"read_doc error: {data.get('error')}\n")
        sys.exit(1)
    text = data.get("text") or ""
    out = "/tmp/cclog_raw_185.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"OK {len(text)} chars -> {out}")


if __name__ == "__main__":
    main()
