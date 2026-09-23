# -*- coding: utf-8 -*-
"""Слой 2 по операциям, конец тихих потерь подтверждений, запрет гасить «да» вслепую, метка
слоя в результате, живой дефолт запасной модели, полный баннер (класс 25.07.2026).
Сети нет: мост подменён заглушкой."""
import logging
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import orchestrator_daemon as OD


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
# Спрашиваем РЕШЕНИЕ слоя 2, а не его внутренний регексп: с 30.07.2026 удаление судится ПО ЦЕЛИ
# (уборка своего черновика в /tmp — не красное), и живой контракт держит именно эта функция —
# её зовут оба боевых места (process_approved и _dec_red_note). Тест на регексп проверял бы
# устройство, а не поведение (класс «судить по действию», ENV_PLAYBOOK п.5).
L2 = OD._is_headless_impossible

print("(1) слой 2: ТЕМЫ больше не ловятся, ОПЕРАЦИИ ловятся")
for t in ("покажи отчёт по деньгам за неделю", "проверить удалённый доступ по ключу",
          "сводка по кассе за месяц", "выгрузи список байков", "посмотри календарь на завтра",
          "прочитай crm и скажи сколько строк", "лист 1 — только чтение",
          "посчитай зарплату вручную в уме",
          "убрать свой черновик: os.remove('/tmp/tb_scratch/x.py')"):
    res.append(ok(not L2(t), "тема НЕ ловится: «%s»" % t[:46]))
for t in ("clasp push", "sqlite3 memory.db 'select 1'", "bridge.set_fleet_oil(...)",
          "delete_event(id=7)", "add_transaction(-500)", "void_last()",
          "closing_upsert(...)", "create_booking(...)", "activate_booking(...)",
          "os.remove('/root/a')", "shutil.rmtree(x)", "rm -rf /root/x",
          "gspread.open('Sheet')", "POST script.google.com/macros", "confirmed = true"):
    res.append(ok(L2(t), "операция ловится: «%s»" % t[:46]))

print("(2) отказ моста больше не уходит молча")
caught = []


class _H(logging.Handler):
    def emit(self, r):
        caught.append(r.getMessage())


OD.log.addHandler(_H())
OD.log.setLevel(logging.INFO)


class _BadBridge:
    def get_pending(self, *a, **k):
        return {"ok": False, "error": "boom"}

    def complete_task(self, *a, **k):
        return {"ok": True}


_real_bc = OD.bc
OD.bc = _BadBridge()
caught[:] = []
OD.process_approved()
res.append(ok(any("мост не ответил" in m for m in caught), "approved: отказ залогирован"))
caught[:] = []
OD.process_na_reminders()
res.append(ok(any("мост не ответил" in m for m in caught), "na_reminders: отказ залогирован"))
res.append(ok(OD._POLL_FAIL_N.get("approved", 0) >= 1, "подряд-неудачи считаются"))

print("(3) покрытие опросов очереди")
now = time.time()
OD._POLL_OK_TS[:] = []
res.append(ok(OD._poll_covered(1800) is False, "истории нет -> НЕ покрыто"))
OD._POLL_OK_TS[:] = [now - 1800 + i * OD.POLL_SEC for i in range(31)]
res.append(ok(OD._poll_covered(1800) is True, "плотная серия опросов -> покрыто"))
OD._POLL_OK_TS[:] = [now - 1800, now - 100, now]
res.append(ok(OD._poll_covered(1800) is False, "дыра в середине окна -> НЕ покрыто"))

print("(4) «да» не сгорает вслепую, а сгоревшее помечено слоем")
closed = []


class _Bridge:
    def __init__(self, items):
        self.items = items

    def get_pending(self, st, *a, **k):
        return {"ok": True, "items": self.items if st == "approved" else []}

    def complete_task(self, tid, status, result="", *a, **k):
        closed.append((tid, status, result))
        return {"ok": True}


TASK = [{"id": 777, "status": "approved", "updated": "2000-01-01T00:00:00+00:00",
         "task_text": "обычная задача", "result": "op=other | что-то", "op": "other",
         "source": "test", "approved_by": "Filipp"}]
OD.bc = _Bridge(TASK)
OD._approved_expired = lambda *a, **k: True
OD._POLL_OK_TS[:] = []
closed[:] = []
caught[:] = []
OD.process_approved()
res.append(ok(not closed, "непокрытое окно -> задача НЕ погашена (закрыто: %d)" % len(closed)))
res.append(ok(any("НЕ гашу" in m for m in caught), "в журнале сказано, почему не погашена"))
OD._POLL_OK_TS[:] = [now - 1800 + i * OD.POLL_SEC for i in range(31)]
closed[:] = []
OD.process_approved()
res.append(ok(len(closed) == 1 and closed[0][1] == "failed", "покрытое окно -> гасим по TTL"))
res.append(ok(bool(closed) and "[закрыто: слой ttl]" in closed[0][2],
              "в результате назван слой: %r" % (closed[0][2][-26:] if closed else "")))
OD.bc = _real_bc

print("(5) дефолт запасной модели в КОДЕ живой")
src = open(os.path.join(ROOT, "orchestrator_daemon.py"), encoding="utf-8").read()
decl = [l for l in src.splitlines() if l.startswith("ORCH_MODEL_FALLBACK =")]
res.append(ok(len(decl) == 1, "объявление фолбэка ровно одно"))
# МЁРТВАЯ модель — это claude-opus-4-8[1m] (1M-вариант, 404 not_found_error), а НЕ обычный
# claude-opus-4-8: он живой и с 30.07.2026 сам стоит запасным на ОБЕИХ полосах. Проверяем
# именно мёртвый литерал, иначе страж запрещал бы живую запасную модель.
res.append(ok(bool(decl) and "claude-opus-4-8[1m]" not in decl[0],
              "мёртвой модели в объявлении нет: %s" % (decl[0][:88] if decl else "нет строки")))
# 23.09.2026 решение владельца: запасная всех голов — claude-opus-5 (claude-opus-4-8 снят с лестницы).
res.append(ok(bool(decl) and 'or "claude-opus-5"' in decl[0], "дефолт фолбэка = claude-opus-5"))

print("(6) баннер печатает модель, запасную и усилия")
i = src.find("ДЕМОН СТАРТ")
blk = src[i:i + 1600]
res.append(ok(i > 0 and "fallback=%s" in blk, "в формате баннера есть fallback"))
res.append(ok("effort=%s" in blk, "в формате баннера есть effort"))
res.append(ok("ORCH_MODEL_FALLBACK" in blk and "EXECUTOR_EFFORT" in blk, "аргументы переданы"))

print("\nИТОГ: %s (%d/%d)" % ("ВСЕ PASS" if all(res) else "ЕСТЬ FAIL", sum(res), len(res)))
sys.exit(0 if all(res) else 1)
