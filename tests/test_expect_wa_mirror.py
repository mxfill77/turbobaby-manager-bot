#!/usr/bin/env python3
"""О9 — внешний прибор за показом WhatsApp в Telegram: регресс на ВЫДУМАННЫХ базах (01.10.2026).

Контракт: каждая живая строка wa_inbox после точки включения показа показана в своей теме не
позже 10 минут. Отрицательные ветки задания 0090-76g:
  (а) просроченная строка при активном юните            → ОТКАЗ
  (б) юнит не активен, сводка в журнале свежая            → ОТКАЗ (при любом флаге)
  (в) флаг включён, точки включения нет дольше 10 минут   → ОТКАЗ «показ не стартовал»
  (г) флаг выключен                                       → удержание, не тревога
  (д) база не открывается                                 → НЕИЗВЕСТНО с адресом
плюс порядок флага (окружение процесса сильнее файла ключей), закрытие эпизода только по
доказанному факту, громкость (погасший быстрее отсрочки — владельцу не идёт, но в счёте),
откат порогом 0. Ни одной отправки: каналы рук подменены, тестовые базы — во временном каталоге
ВНУТРИ дерева, где лежит тест (на сервере это клон).
"""
import os
import sqlite3
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
for _k in ("EXPECT_WA_MIRROR_MIN", "EXPECT_OWNER_DEFER_MIN", "EXPECT_TO_BRAIN", "EXPECT_HOLD_MIN"):
    os.environ.pop(_k, None)

import expectations as EX            # noqa: E402
import expect_journal as EJ          # noqa: E402
import expect_wa_mirror as EWM       # noqa: E402
import wa_tg_mirror as M             # noqa: E402


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
NOW = 1_790_000_000.0
MIN = 60.0
CFG = EX.config({})
BASE = os.path.join(REPO, ".wam_test")
os.makedirs(BASE, exist_ok=True)
PID = 4242


def world(rows=(), shown=(), start=None, flag_proc=None, flag_file=None, active=True,
          since_ago=3600.0, log_text="", state_broken=False, queue_broken=False, sysctl_rc=0):
    """Выдуманный мир: очередь, база показанного, файл ключей, /proc процесса, журнал, systemctl."""
    d = tempfile.mkdtemp(prefix="w_", dir=BASE)
    qp = os.path.join(d, "wa_queue.db")
    if queue_broken:
        with open(qp, "wb") as fh:
            fh.write(b"not a database at all " * 40)
    else:
        q = sqlite3.connect(qp)
        q.execute("CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY, ts_queued INTEGER, from_number "
                  "TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT, mime TEXT, caption "
                  "TEXT, media_note TEXT, ts_msg INTEGER, echo INTEGER, history INTEGER, wamid TEXT)")
        for rid, ts, mtype, echo, hist in rows:
            q.execute("INSERT INTO wa_inbox(id, ts_queued, from_number, name, msg_type, text, ts_msg, "
                      "echo, history, wamid) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (rid, int(ts), "000", "x", mtype, "x", int(ts), echo, hist, "wamid.T%d" % rid))
        q.commit()
        q.close()
    sp = os.path.join(d, "wa_tg_mirror.db")
    if state_broken:
        with open(sp, "wb") as fh:
            fh.write(b"garbage, not sqlite " * 40)
    else:
        s = sqlite3.connect(sp)
        for stmt in M._STATE_SCHEMA.strip().split(";"):
            if stmt.strip():
                s.execute(stmt)
        if start is not None:
            s.execute("INSERT INTO kv(k, v) VALUES ('show_start_id', ?)", (str(start),))
        for rid, state in shown:
            s.execute("INSERT INTO shown(key, number, state, ts) VALUES (?,?,?,?)",
                      ("msg:wamid.T%d" % rid, "000", state, NOW))
        s.commit()
        s.close()
    if flag_file is not None:
        with open(os.path.join(d, ".env"), "w") as fh:
            fh.write("OTHER_KEY=zzz\n%s=%s\n" % (M.FLAG_NAME, flag_file))
    pdir = os.path.join(d, "proc", str(PID))
    os.makedirs(pdir)
    env = b"PATH=/usr/bin\0OTHER=1\0"
    if flag_proc is not None:
        env += ("%s=%s\0" % (M.FLAG_NAME, flag_proc)).encode()
    with open(os.path.join(pdir, "environ"), "wb") as fh:
        fh.write(env)
    with open(os.path.join(d, "wa_tg_mirror.log"), "w", encoding="utf-8") as fh:
        fh.write(log_text)

    class _P:
        def __init__(self, out, rc):
            self.stdout, self.returncode = out, rc

    def run(argv, **kw):
        assert argv[:3] == ["systemctl", "show", "wa-tg-mirror"], argv
        if active:
            out = ("ActiveState=active\nSubState=running\nMainPID=%d\nActiveEnterTimestamp=@%d\n"
                   % (PID, int(NOW - since_ago)))
        else:
            out = "ActiveState=inactive\nSubState=dead\nMainPID=0\nActiveEnterTimestamp=\n"
        return _P("" if sysctl_rc else out, sysctl_rc)

    f = EWM.facts(NOW, root=d, run=run, proc=os.path.join(d, "proc"))
    return {"now": NOW, "wa_mirror": f}, d


def o9(facts, cfg=CFG):
    return [v for v in EX.verdict(facts, cfg) if str(v.get("kind")).startswith("o9")]


def st(facts, cfg=CFG):
    return EX.wa_mirror_state(facts, cfg, NOW)


LIVE = "text"     # известный тип при echo=0, history=0 → входящее (wa_kind)

# ═══ (а) просроченная строка при активном юните → ОТКАЗ ═══════════════════════════════════════
print("\n(а) просроченная живая строка при активном юните")
fa, _ = world(rows=[(5, NOW - 30 * MIN, LIVE, 0, 0), (11, NOW - 15 * MIN, LIVE, 0, 0)],
              start=10, flag_proc="1")
va = o9(fa)
res.append(ok(st(fa)[0] == EX.WAM_FAIL and len(va) == 1 and va[0]["key"] == "o9|late"
              and va[0]["kind"] == "o9_wa_mirror", "(а) строка 15 мин без показа → ОТКАЗ o9|late"))
res.append(ok(va and va[0].get("ids") == [11], "(а) названа ровно строка после точки (id 11), id 5 "
              "до точки не считается: %s" % (va and va[0].get("ids"))))
fa2, _ = world(rows=[(11, NOW - 15 * MIN, LIVE, 0, 0)], shown=[(11, M.S_UNSURE)], start=10,
               flag_proc="1")
res.append(ok(st(fa2)[0] == EX.WAM_OK and not o9(fa2),
              "(а) та же строка в shown (даже «без ответа», как у службы) → в порядке"))
fa3, _ = world(rows=[(11, NOW - 5 * MIN, LIVE, 0, 0)], start=10, flag_proc="1")
res.append(ok(st(fa3)[0] == EX.WAM_OK and not o9(fa3), "(а) строка 5 мин без показа → ещё в сроке"))
fa4, _ = world(rows=[(11, NOW - 30 * MIN, "status", 0, 0), (12, NOW - 30 * MIN, LIVE, 0, 1)],
               start=10, flag_proc="1")
res.append(ok(st(fa4)[0] == EX.WAM_OK and not o9(fa4),
              "(а) квитанция и строка истории не живые (функция службы) → не считаются"))
txt = EX.render(va[0]) if va else ""
res.append(ok("ОТКАЗ" in txt and "11" in txt and "бот показа" in txt,
              "(а) заметка: ОТКАЗ, id строки, канал назван не ботом показа"))

# ═══ (б) юнит не активен, сводка свежая → ОТКАЗ при любом флаге ═════════════════════════════════
print("\n(б) юнит не активен, свежая сводка в журнале")
fresh = "2026-09-21 12:00:00,000 [INFO] wa_tg_mirror: сводка: показ=идёт тем=3 показано=9\n"
for flag in ("1", "0", None):
    fb, _ = world(active=False, flag_proc=flag, log_text=fresh)
    vb = o9(fb)
    res.append(ok(st(fb)[0] == EX.WAM_FAIL and len(vb) == 1 and vb[0]["key"] == "o9|unit",
                  "(б) флаг=%s: юнит не активен → ОТКАЗ o9|unit" % flag))
res.append(ok(vb and (vb[0].get("hint") or {}).get("show") == "идёт",
              "(б) сводка «идёт» едет пояснением, решение от неё не зависит"))

# ═══ (в) флаг включён, точки включения нет дольше 10 минут → ОТКАЗ ═════════════════════════════
print("\n(в) показ не стартовал")
fc, _ = world(flag_proc="1", start=None, since_ago=11 * MIN)
vc = o9(fc)
res.append(ok(st(fc)[0] == EX.WAM_FAIL and len(vc) == 1 and vc[0]["key"] == "o9|nostart",
              "(в) юнит активен 11 мин, точки включения нет → ОТКАЗ «показ не стартовал»"))
fc2, _ = world(flag_proc="1", start=None, since_ago=5 * MIN)
res.append(ok(st(fc2)[0] == EX.WAM_OK and not o9(fc2), "(в) активен 5 мин → ещё включается"))

# ═══ (г) флаг выключен → удержание; порядок флага — порядком службы ═══════════════════════════
print("\n(г) флаг выключен и порядок источников флага")
fd, _ = world(rows=[(11, NOW - 60 * MIN, LIVE, 0, 0)], start=10, flag_proc=None, flag_file=None)
res.append(ok(st(fd)[0] == EX.WAM_HOLD and not o9(fd),
              "(г) флага нет нигде → удержание, тревоги нет (даже при «просроченной» строке)"))
fd2, _ = world(rows=[(11, NOW - 60 * MIN, LIVE, 0, 0)], start=10, flag_proc="0", flag_file="1")
res.append(ok(st(fd2)[0] == EX.WAM_HOLD, "(г) окружение юнита «0» сильнее файла «1» → удержание"))
fd3, _ = world(rows=[(11, NOW - 60 * MIN, LIVE, 0, 0)], start=10, flag_proc=None, flag_file="1")
res.append(ok(st(fd3)[0] == EX.WAM_FAIL and fd3["wa_mirror"]["flag"]["src"] == "файл ключей",
              "(г) в окружении нет, в файле «1» → включён (файл) → судится просрочка"))
fd4, _ = world(start=10, flag_proc="", flag_file="1")
res.append(ok(st(fd4)[0] == EX.WAM_HOLD,
              "(г) в окружении пусто («задано») — файл не перезаписывает → удержание"))
res.append(ok(EX.wa_mirror_line(*st(fd)).startswith("удержание: показ выключен"),
              "(г) строка итога: «удержание: показ выключен …»"))

# ═══ (д) база не открывается → НЕИЗВЕСТНО с адресом ═══════════════════════════════════════════
print("\n(д) НЕИЗВЕСТНО с адресом")
fe, de = world(flag_proc="1", state_broken=True)
ve = o9(fe)
s_e, i_e = st(fe)
res.append(ok(s_e == EX.WAM_UNKNOWN and len(ve) == 1 and ve[0]["key"] == "o9u|state"
              and os.path.join(de, "wa_tg_mirror.db") in str(ve[0].get("addr")),
              "(д) база показанного битая → НЕИЗВЕСТНО o9u|state, адрес = путь базы"))
fe2, de2 = world(rows=[(11, NOW - 60 * MIN, LIVE, 0, 0)], start=10, flag_proc="1",
                 queue_broken=True)
ve2 = o9(fe2)
res.append(ok(st(fe2)[0] == EX.WAM_UNKNOWN and ve2 and ve2[0]["key"] == "o9u|queue"
              and os.path.join(de2, "wa_queue.db") in str(ve2[0].get("addr")),
              "(д) очередь битая → НЕИЗВЕСТНО o9u|queue, адрес = путь очереди"))
fe3, _ = world(flag_proc="1", sysctl_rc=1)
res.append(ok(st(fe3)[0] == EX.WAM_UNKNOWN and o9(fe3)[0]["key"] == "o9u|unit",
              "(д) systemctl не ответил → НЕИЗВЕСТНО o9u|unit"))
res.append(ok(EX.wa_mirror_line(s_e, i_e).startswith("НЕИЗВЕСТНО: ") and "wa_tg_mirror.db"
              in EX.wa_mirror_line(s_e, i_e), "(д) строка итога несёт адрес"))
res.append(ok(not EJ.heavy(ve[0])[0] and EJ.heavy(va[0])[0],
              "(д) НЕИЗВЕСТНО владельцу не адресовано (вес лёгкий), ОТКАЗ — тяжёлый"))

# ═══ закрытие и откат ═════════════════════════════════════════════════════════════════════════
print("\n(е) закрытие только по доказанному факту; откат порогом 0")
res.append(ok(EX.closures(fa3, CFG, ["o9|late"]) == ["o9|late"],
              "(е) показ в порядке → эпизод o9|late закрыт"))
res.append(ok(EX.closures(fe, CFG, ["o9|late"]) == [],
              "(е) судить нечем → эпизод НЕ закрыт (молчание источника не выздоровление)"))
res.append(ok(EX.closures(fd, CFG, ["o9|unit"]) == ["o9|unit"],
              "(е) удержание доказано → эпизод «юнит не активен» закрыт"))
CFG0 = EX.config({"EXPECT_WA_MIRROR_MIN": "0"})
res.append(ok(not o9(fa, CFG0), "(е) EXPECT_WA_MIRROR_MIN=0 → ветка мертва"))

# ═══ громкость: правило слоя через настоящие руки (каналы подменены) ═══════════════════════════
print("\n(ж) громкость: погасший быстрее отсрочки не идёт владельцу, но остаётся в счёте")
import expectations_run as ER        # noqa: E402

sent, journal, store = [], [], {}
ER.load_state = lambda: dict(store.get("st") or {})
ER.save_state = lambda s: store.__setitem__("st", s)
ER.send_note = lambda text: sent.append(text) or True
ER.write_journal = lambda text: journal.append(text) or True
ER.write_proof = lambda v, f, n: ""
ER.queue_state_step = lambda *a, **k: {}
_snap = {}
ER.snapshot = lambda now=None, st=None, cfg=None: dict(_snap["f"], now=now)

_snap["f"] = fa
o1 = ER.run(now=NOW)
res.append(ok("o9|late" in o1["held"] and not sent and str(o1.get("wa_mirror")).startswith("ОТКАЗ"),
              "(ж) первый прогон: ОТКАЗ в итоге, эпизод держится, владельцу 0"))
_snap["f"] = fa2                     # строку показали (часы прогона ушли на +10 мин)
o2 = ER.run(now=NOW + 10 * MIN)
res.append(ok("o9|late" in o2["quiet"] and not sent
              and any("ОЖИДАНИЕ О9" in j for j in journal)
              and int(((store["st"].get("quiet") or {}).get("n")) or 0) == 1,
              "(ж) погас через 10 мин: владельцу 0, строка «ОЖИДАНИЕ О9» в журнале, счёт тихих = 1"))
store.clear(), sent.clear(), journal.clear()
_snap["f"] = fa
ER.run(now=NOW)
o4 = ER.run(now=NOW + 61 * MIN)
res.append(ok("o9|late" in o4["notes"] and len(sent) == 1 and "показ WhatsApp" in sent[0],
              "(ж) держится 61 мин (отсрочка 60): одна заметка каналом демона"))

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
