#!/usr/bin/env python3
"""Мини-ревизия 07.07 поздний вечер: RESULT в cc_log (ПОД врезкой) + KB_PULSE — ОДНОЙ операцией."""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient


def insert_under_vrezka(old: str, line: str) -> str:
    lines = old.split("\n")
    idx = None
    for i, ln in enumerate(lines[:15]):
        s = ln.strip()
        if s and set(s) == {"═"}:
            idx = i
            break
    if idx is None:
        return line + "\n\n" + old
    head = "\n".join(lines[:idx + 1])
    rest = "\n".join(lines[idx + 1:]).lstrip("\n")
    return head + "\n\n" + line + "\n\n" + rest


ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
line = (f"DONE {ts} UTC (o4-headless): RESULT мини-ревизия «ПК-театр закрыт» (07.07 поздний вечер, дополнение "
        "к утренней) — KB_MASTER обновлён (снимок до правки /tmp/KB_MASTER_snap_20260707_evening.md, 43516→47547 cp). "
        "§3: дописан блок ⭐07.07 ПОЗДНИЙ ВЕЧЕР — ПК-театр 3 куска (c674b8b ПК-репо pc-самопочинка / fa3680d "
        "декомпозер pc + sequential release + restart-proof + process_pc_chains / a2b8945 единый пульт 328, "
        "роутер haiku, живые обкатки), фантом 122 + фикс дыры 7ff92fb (чужой рестарт → возврат в new), авария "
        "клиентского контура (краш CLI единичный, Conflict getUpdates) + подъём #129 силами pc_orchestrator + "
        "фикс класса 7517615 (stderr в файлы, error-handler+синглтон модербота, вотчдог 5 мин, OS-синглтон — "
        "дубль схлопнулся), sonnet для suggest подтверждён рестартом (PID 19952, крашей 0), THINKER_MODEL=fable-5 "
        "отделён (49aa9c1), журнал-ритуал Dispatch в CLAUDE.md, ночной инцидент 138 → фикс класса 6de3cfc (реапер "
        "сирот ORPHAN_TTL + _enqueue_reliable + ⏱-гейт думателя, гейт 64/64). "
        "§4: ПК-ТЕАТР ЗАВЕРШЁН — кандидат (а) выполнен, оба театра под одним дирижёром и пультом 328; АКТИВНЫЙ "
        "ГОРИЗОНТ ОСИ = ОПЕРАЦИИ O3 (бронь/выдача/приём). "
        "§7 хвосты: обкатка думателей vps+pc (расширен), + pc_agent на коде до 7517615 (вотчдог сторожит), "
        "+ durable-фикс intermittent 404 Google в bridge_client (follow-redirect-as-GET + backoff) кандидатом, "
        "+ разобрать алерты «ТЕСТЫ КРАСНЫЕ 17:56/20:05». Post-write verify OK (длина + маркеры, оба захода). "
        "registry_check: 1-й прогон поймал c674b8b без маркера чужого репо → помечен «ПК-репо» на всех 3 строках "
        "(штатный механизм фикса 9a695fb) → повторный прогон СХОДИТСЯ 4/4, 0 расхождений. NOTE по ходу: intermittent "
        "404 Google ударил живьём в 20:40 UTC (один прогон реестра ушёл в пропуски, ретрай чистый) — подтверждает "
        "актуальность хвоста durable-фикса. Хвостов новых нет.")

pulse = (f"{ts} UTC | 🟢 | мини-ревизия «ПК-театр закрыт» завершена: KB_MASTER §3/§4/§7 дописаны (ПК-театр "
         "закрыт, активный горизонт = ОПЕРАЦИИ O3), post-write verify OK, registry_check СХОДИТСЯ 4/4 | "
         "ничего не жду | детали→cc_log запись «мини-ревизия 07.07 поздний вечер»")

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("cc_log READ FAIL — НЕ пишу (защита от затирки):", r)
    raise SystemExit(1)
new = insert_under_vrezka(r.get("text", ""), line)
w = c.write_doc(text=new, name="cc_log")
if not w.get("ok"):
    print("cc_log WRITE FAIL:", w)
    raise SystemExit(1)
print(f"cc_log OK (old={len(r.get('text',''))} → new={len(new)})")

wp = c.write_doc(text=pulse, name="pulse")
print("pulse:", "OK" if wp.get("ok") else f"FAIL {wp}")
if not wp.get("ok"):
    raise SystemExit(1)
