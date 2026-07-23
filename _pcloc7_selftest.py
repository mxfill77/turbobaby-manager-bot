# -*- coding: utf-8 -*-
"""
Самотест ЖИВЬЁМ локального дирижёра ПК (шаг 7/7 родителя 185, pcloc-dec).

Гоняется на VPS-зеркале ПК-репо /root/_pcport_userbot_185 (HEAD = шаг 6/7): реальный
pc_orchestrator с PC_LOCAL_DEC=1, РЕАЛЬНЫЕ headless-вызовы claude -p (планировщик цепи и
исполнители шагов — как на ПК), реальный цикл poll_once. Единственная замена — очередь:
локальный HTTP-стаб протокола Bridge (in-memory, 127.0.0.1) вместо Google-очереди —
изоляция от прод-полосы pc (никакой гонки с реальным ПК-демоном, ноль карточек в Telegram:
_notify/_cowork демона зовут несуществующий на Linux venv\\Scripts\\python.exe и молча гаснут).

Сценарий по ТЗ: PC_LOCAL_DEC=1 → прямым каналом (enqueue_pc_task → claim → done, реальный
HTTP) игрушечный родитель from=Filipp-pcloc-dec lane=pc из 2 read-only шагов (1: версия
питона; 2: счёт файлов в docs) → дождаться цикла план→шаги→сводка → проверить маркеры →
вернуть PC_LOCAL_DEC=0. Read-only: рабочие таблицы/прод-очередь/Telegram не трогаются.
"""
import datetime
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

MIRROR = "/root/_pcport_userbot_185"
EMU = os.path.join(MIRROR, r"D:\turbobaby-bot")   # каталог LOG/heartbeat (создаёт импорт демона)
# Рабочая эмуляция REPO ПК — БЕЗ бэкслешей: буквальный путь "D:\turbobaby-bot" на Linux валиден
# для ФС, но claude CLI интерпретирует \t и падает «Path does not exist» — на реальном ПК
# проблемы нет (там путь настоящий). Патчим o.REPO на этот каталог после импорта (см. main).
EMU2 = os.path.join(MIRROR, "_emu_d_turbobaby-bot")
DUMP = "/root/turbobaby-manager-bot/_pcloc7_queue_dump.json"

TOY = ("Игрушечный самотест локального дирижёра (read-only, ничего не менять, git/деплой/таблицы "
       "не трогать): разбей РОВНО на 2 шага: 1) выяснить версию питона командой python3 --version "
       "и доложить её; 2) посчитать количество файлов в папке docs (ls docs) и доложить число.")

# ------------------------- in-memory очередь + HTTP-стаб Bridge -------------------------

LOCK = threading.Lock()
ROWS = {}
NID = [200]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class BridgeStub(BaseHTTPRequestHandler):
    def log_message(self, *a):   # тихий сервер
        pass

    def _send(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        action = (q.get("action") or [""])[0]
        if action != "get_pending":
            return self._send({"ok": False, "error": "unknown_action"})
        sts = [s.strip() for s in (q.get("status") or [""])[0].split(",") if s.strip()]
        lane = (q.get("lane") or [None])[0]
        with LOCK:
            items = [dict(r) for r in sorted(ROWS.values(), key=lambda x: x["id"])
                     if r["status"] in sts and (lane is None or r["lane"] == lane)]
        self._send({"ok": True, "items": items})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        except Exception:
            return self._send({"ok": False, "error": "bad_json"})
        a = body.get("action")
        with LOCK:
            if a == "enqueue_task":
                NID[0] += 1
                ROWS[NID[0]] = {"id": NID[0], "from": body.get("from") or "",
                                "task_text": body.get("task_text") or "", "status": "new",
                                "result": "", "lane": body.get("lane") or "pc", "updated": _now()}
                return self._send({"ok": True, "id": NID[0]})
            r = ROWS.get(int(body.get("id") or 0))
            if not r:
                return self._send({"ok": False, "error": "not_found"})
            if a == "claim_task":
                if r["status"] != "new":
                    return self._send({"ok": False, "error": "already_claimed"})
                r["status"], r["updated"] = "in_progress", _now()
                return self._send({"ok": True, "task": dict(r)})
            if a == "complete_task":
                if body.get("status") not in ("done", "failed"):
                    return self._send({"ok": False, "error": "bad_status"})
                r["status"], r["result"], r["updated"] = body["status"], body.get("result") or "", _now()
                return self._send({"ok": True})
            if a == "set_needs_approval":
                r["status"], r["result"], r["updated"] = "needs_approval", body.get("what") or "", _now()
                return self._send({"ok": True})
            if a == "task_heartbeat":
                r["updated"] = _now()
                return self._send({"ok": True})
        self._send({"ok": False, "error": "unknown_action"})


def snapshot():
    with LOCK:
        return {k: dict(v) for k, v in ROWS.items()}


def main():
    # --- среда эмуляции ПК-репо (до импорта демона: LOG_PATH относительный) ---
    os.chdir(MIRROR)
    os.makedirs(EMU, exist_ok=True)
    os.makedirs(os.path.join(EMU2, "docs"), exist_ok=True)
    for name in ("alpha.md", "beta.md", "gamma.md"):
        with open(os.path.join(EMU2, "docs", name), "w", encoding="utf-8") as f:
            f.write("самотест pcloc-dec: файл-наполнитель docs\n")
    os.makedirs(os.path.join(EMU2, ".claude"), exist_ok=True)
    with open(os.path.join(EMU2, ".claude", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"permissions": {"allow": [
            "Read", "Glob", "Grep",
            "Bash(python3 --version*)", "Bash(python --version*)", "Bash(python3 -V*)",
            "Bash(ls*)", "Bash(find*)", "Bash(wc*)", "Bash(pwd*)", "Bash(echo*)",
        ], "deny": []}}, f)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), BridgeStub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # --- env самотеста (до импорта: константы читаются на импорте) ---
    os.environ["BRIDGE_URL"] = f"http://127.0.0.1:{port}"
    os.environ["BRIDGE_TOKEN"] = "selftest-toy"
    os.environ["PC_LOCAL_DEC"] = "1"          # ТЗ шага 7: флаг взведён на время самотеста
    os.environ["STEP_SELFHEAL"] = "0"          # happy-path по ТЗ: план→шаги→сводка без думателей
    os.environ["PLAN_ADAPT"] = "0"
    os.environ["THINKER_MODEL"] = "fable"      # VPS-алиас кондуктора (на ПК из .env свой)
    os.environ["THINKER_FALLBACK"] = "claude-opus-4-8[1m]"
    os.environ["PC_TASK_TIMEOUT"] = "420"      # самотестовая рамка вместо 45 мин
    os.environ["PC_DEC_PLAN_TIMEOUT"] = "420"
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(k, None)

    sys.path.insert(0, MIRROR)
    import pc_orchestrator as o
    # средовая подмена ТОЛЬКО пути REPO (см. комментарий у EMU2): исполнители шагов работают
    # в чистом каталоге-эмуляции; run_task/маркер-файл читают глобаль на вызове — патч работает
    o.REPO = EMU2
    print(f"[{_now()}] демон импортирован: LANE={o.LANE} PC_LOCAL_DEC={o._local_dec_on()} "
          f"BRIDGE_URL={o.BRIDGE_URL} REPO={o.REPO}")

    # --- игрушечный родитель ПРЯМЫМ каналом (реальный HTTP enqueue, 86d8b03) ---
    ok, pid, err = o.enqueue_pc_task(TOY, frm=o.PC_LOCAL_DEC_FROM)
    if not ok:
        print("SELFTEST FAIL: enqueue родителя не прошёл:", err)
        return 1
    print(f"[{_now()}] родитель id={pid} в очереди (from={o.PC_LOCAL_DEC_FROM}, lane=pc)")

    # --- живой цикл демона до сводки/провала ---
    deadline = time.time() + 1500
    seq_max = 0
    verdictable = None
    while time.time() < deadline:
        o.poll_once()
        rows = snapshot()
        chain_new = [r for r in rows.values() if r["status"] == "new"
                     and r["from"] == o.PC_LOCAL_DEC_FROM and o._STEP_RE.match(r["task_text"])]
        seq_max = max(seq_max, len(chain_new))
        parent = rows[pid]
        sums = [r for r in rows.values() if o._SUM_RE.match(r["task_text"])
                and int(o._SUM_RE.match(r["task_text"]).group(1)) == pid]
        state = {k: (v["status"], v["task_text"][:60]) for k, v in sorted(rows.items())}
        print(f"[{_now()}] тик: {state}")
        if sums and sums[0]["status"] in ("done", "failed"):
            verdictable = rows
            break
        if parent["status"] == "failed":
            verdictable = rows
            break
        time.sleep(2)

    rows = verdictable or snapshot()
    with open(DUMP, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    # --- проверка маркеров цепи ---
    checks = []

    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    parent = rows[pid]
    chk("родитель done", parent["status"] == "done", parent["status"])
    chk("маркер плана «🧩 … локальный дирижёр PC» в result родителя",
        "🧩" in parent["result"] and "локальный дирижёр PC" in parent["result"],
        parent["result"][:120])
    chk("план из 2 шагов в result родителя",
        "1." in parent["result"] and "2." in parent["result"] and "2 шагов" in parent["result"],
        parent["result"][:200])

    steps = []
    for r in sorted(rows.values(), key=lambda x: x["id"]):
        m = o._STEP_RE.match(r["task_text"])
        if m and int(m.group(3)) == pid:
            steps.append((int(m.group(1)), int(m.group(2)), r))
    chk("шагов цепи ровно 2", len(steps) == 2, f"нашлось {len(steps)}")
    for i, n, r in steps:
        chk(f"шаг {i}/{n}: маркер [шаг {i}/{n} родитель {pid}]",
            r["task_text"].startswith(f"[шаг {i}/{n} родитель {pid}]"), r["task_text"][:80])
        chk(f"шаг {i}: from/lane", (r["from"], r["lane"]) == (o.PC_LOCAL_DEC_FROM, "pc"),
            f"{r['from']}/{r['lane']}")
        chk(f"шаг {i}: done", r["status"] == "done", f"{r['status']}: {r['result'][:120]}")

    sums = [r for r in sorted(rows.values(), key=lambda x: x["id"])
            if r["task_text"].startswith(f"[сводка родитель {pid}]")]
    chk("сводка ровно одна", len(sums) == 1, f"нашлось {len(sums)}")
    if sums:
        s = sums[0]
        chk("сводка done", s["status"] == "done", s["status"])
        chk("сводка: «2/2 шагов done»", "2/2 шагов done" in s["result"], s["result"][:200])
        chk("сводка: ✅ по каждому шагу", s["result"].count("✅") == 2,
            f"✅×{s['result'].count('✅')}")
        chk("сводка: подпись локального дирижёра", "локальный дирижёр" in s["result"],
            s["result"][:200])
    chk("sequential-релиз: максимум 1 new-шаг цепи одновременно", seq_max <= 1,
        f"максимум был {seq_max}")
    reds = [r for r in rows.values() if r["status"] == "needs_approval"]
    chk("красного/зависшего нет (read-only цепь)", not reds, str(len(reds)))

    print()
    fails = 0
    for name, okc, detail in checks:
        mark = "PASS" if okc else "FAIL"
        fails += 0 if okc else 1
        print(f"  [{mark}] {name}" + (f" — {detail}" if (detail and not okc) else ""))

    # --- вернуть флаг (жил только в env самотеста; постоянных следов нет) ---
    os.environ["PC_LOCAL_DEC"] = "0"
    print(f"\n[{_now()}] PC_LOCAL_DEC возвращён в 0 (env самотеста); дамп очереди: {DUMP}")

    if fails:
        print(f"SELFTEST FAIL: {fails} из {len(checks)} проверок красные")
        return 1
    print(f"SELFTEST PASS: {len(checks)}/{len(checks)} проверок зелёные "
          f"(план→шаги→сводка живьём, маркеры целы)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
