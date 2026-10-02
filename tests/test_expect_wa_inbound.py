#!/usr/bin/env python3
"""О10 — вход WhatsApp: регресс на ПОДДЕЛКАХ (02.10.2026, задание 0114-77n).

Контракт: у 360dialog адрес вебхука НАШ и номер подключён → в порядке; иначе ОТКАЗ; 360dialog не
ответил → НЕИЗВЕСТНО с причиной. Счёта сообщений нет. Ветки задания:
  (+) адрес наш, номер подключён                → в порядке, вердикта нет
  (−) адрес чужой (хост / секрет / пусто)       → ОТКАЗ
  (−) номер отключён (BLOCKED)                   → ОТКАЗ
  (−) 360dialog молчит (транспорт, 5xx, не JSON) → НЕИЗВЕСТНО
  (−) ключ и адрес не попадают ни в журнал, ни в тревогу, ни в строку прогона
плюс громкость (ОТКАЗ — владельцу с первого такта, эпизод — одна тревога; НЕИЗВЕСТНО — только в
мозг), закрытие только по доказанному «в порядке», откат выключателем 0 (ни одного вызова).
Ни одного обращения к сети: вызов подменён, файл ключей выдуман во временном каталоге ВНУТРИ
дерева, где лежит тест (на сервере это клон).
"""
import io
import json
import os
import sys
import tempfile
import urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
for _k in ("EXPECT_WA_INBOUND", "EXPECT_OWNER_DEFER_MIN", "EXPECT_TO_BRAIN", "EXPECT_HOLD_MIN",
           "EXPECT_WA_MIRROR_MIN"):
    os.environ.pop(_k, None)

import expectations as EX            # noqa: E402
import expect_journal as EJ          # noqa: E402
import expect_wa_inbound as EWI      # noqa: E402


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
NOW = 1_790_000_000.0
MIN = 60.0
CFG = EX.config({})
BASE = os.path.join(REPO, ".wai_test")
os.makedirs(BASE, exist_ok=True)
KEY = "TESTKEYzz9Qx_7fakefakefake"                 # выдуманный ключ: ищется в каждом выводе
SECRET = "c0ffee00c0ffee00c0ffee00c0ffee00"         # выдуманный секрет пути
OURS = EWI.PUBLIC_BASE + EWI.D360_PATH + SECRET
FOREIGN_SECRET = OURS[:-6] + "abcdef"
FOREIGN_HOST = "https://evil.example.org" + EWI.D360_PATH + SECRET


def keys_file(key=KEY, secret=SECRET):
    d = tempfile.mkdtemp(prefix="k_", dir=BASE)
    with open(os.path.join(d, ".env"), "w", encoding="utf-8") as fh:
        if key is not None:
            fh.write("WA_D360_API_KEY=%s\n" % key)
        if secret is not None:
            fh.write("WA_D360_PATH_SECRET=%s\n" % secret)
        fh.write("OTHER_SECRET=never-read\n")
    return d


class _Resp:
    def __init__(self, code, body):
        self.status, self._b = code, body

    def read(self, n=-1):
        return self._b

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(hook=None, health=None, hook_exc=None, health_exc=None, calls=None):
    """Подделка 360dialog: путь → ответ. Записывает каждый вызов (путь, заголовок ключа)."""
    calls = calls if calls is not None else []

    def _open(req, timeout=None):
        path = req.full_url[len(EWI.API_BASE):]
        calls.append((path, req.get_header(EWI.KEY_HEADER.capitalize()) or req.headers.get(EWI.KEY_HEADER)))
        exc = hook_exc if path == EWI.HOOK_PATH else health_exc
        if exc is not None:
            raise exc
        body = hook if path == EWI.HOOK_PATH else health
        raw = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
        return _Resp(200, raw)
    return _open, calls


def health(state="AVAILABLE", errors=None):
    ent = {"entity_type": "PHONE_NUMBER", "id": "100000000000001", "can_send_message": state}
    if errors:
        ent["errors"] = errors
    return {"health_status": {"can_send_message": state, "entities": [
        ent, {"entity_type": "WABA", "id": "200000000000002", "can_send_message": "AVAILABLE"}]},
        "id": "100000000000001"}


def world(hook=None, hstate="AVAILABLE", hook_exc=None, health_exc=None, key=KEY, secret=SECRET,
          health_body=None, errors=None):
    root = keys_file(key, secret)
    op, calls = opener_for({"url": OURS} if hook is None else hook,
                           health_body if health_body is not None else health(hstate, errors),
                           hook_exc, health_exc)
    f = EWI.facts(NOW, root=root, opener=op)
    return {"now": NOW, "wa_inbound": f}, calls


def o10(facts, cfg=CFG):
    return [v for v in EX.verdict(facts, cfg) if str(v.get("kind")).startswith("o10")]


def st(facts, cfg=CFG):
    return EX.wa_inbound_state(facts, cfg, NOW)


# ═══ (+) в порядке ════════════════════════════════════════════════════════════════════════════
print("(+) адрес наш, номер подключён")
fa, ca = world()
res.append(ok(st(fa)[0] == EX.WAI_OK and not o10(fa), "(+) адрес наш, AVAILABLE → в порядке, вердикта нет"))
res.append(ok([p for p, _ in ca] == [EWI.HOOK_PATH, EWI.HEALTH_PATH] and all(k == KEY for _, k in ca),
              "(+) ровно два GET чтения: вебхук и health_status, ключ — только заголовком"))
fa2, _ = world(hook={"url": OURS + "/"}, hstate="LIMITED")
res.append(ok(st(fa2)[0] == EX.WAI_OK, "(+) хвостовой «/» и LIMITED → в порядке"))
res.append(ok(EX.wa_inbound_line(*st(fa)).startswith("в порядке: адрес вебхука у 360dialog наш"),
              "(+) строка прогона называет исход"))

# ═══ (−) адрес чужой ══════════════════════════════════════════════════════════════════════════
print("\n(−) адрес чужой → ОТКАЗ")
for name, hk, part in (("секрет", {"url": FOREIGN_SECRET}, "секрет пути не наш"),
                       ("хост", {"url": FOREIGN_HOST}, "хост не наш"),
                       ("путь", {"url": EWI.PUBLIC_BASE + "/wa-webhook/meta"}, "путь не наш")):
    fb, _ = world(hook=hk)
    vb = o10(fb)
    res.append(ok(st(fb)[0] == EX.WAI_FAIL and len(vb) == 1 and vb[0]["key"] == "o10|in"
                  and vb[0]["kind"] == "o10_wa_inbound" and part in vb[0]["why"],
                  "(−) чужой %s → ОТКАЗ o10|in «%s»" % (name, part)))
fb0, _ = world(hook={"url": ""})
res.append(ok(st(fb0)[0] == EX.WAI_FAIL and "пуст" in st(fb0)[1]["why"], "(−) адрес пуст → ОТКАЗ"))

# ═══ (−) номер отключён ═══════════════════════════════════════════════════════════════════════
print("\n(−) номер отключён → ОТКАЗ")
fc, _ = world(hstate="BLOCKED", errors=[{"error_code": 141000, "error_description": "Phone number disconnected"}])
vc = o10(fc)
res.append(ok(st(fc)[0] == EX.WAI_FAIL and len(vc) == 1 and "номер не подключён" in vc[0]["why"]
              and "BLOCKED" in vc[0]["why"], "(−) BLOCKED → ОТКАЗ «номер не подключён»"))
fc2, _ = world(hook={"url": FOREIGN_SECRET}, hstate="BLOCKED")
vc2 = o10(fc2)
res.append(ok(len(vc2) == 1 and "не наш" in vc2[0]["why"] and "BLOCKED" in vc2[0]["why"],
              "(−) обе части плохи → ОДИН вердикт, обе причины в нём"))
fc3, _ = world(hook_exc=urllib.error.URLError("timed out"), hstate="BLOCKED")
res.append(ok(st(fc3)[0] == EX.WAI_FAIL, "(−) вебхук не прочитан, номер BLOCKED → ОТКАЗ сильнее НЕИЗВЕСТНО"))

# ═══ (−) 360dialog молчит ═════════════════════════════════════════════════════════════════════
print("\n(−) 360dialog молчит → НЕИЗВЕСТНО с причиной")
fd, _ = world(hook_exc=urllib.error.URLError("timed out"), health_exc=TimeoutError("timed out"))
sd, idd = st(fd)
vd = o10(fd)
res.append(ok(sd == EX.WAI_UNKNOWN and vd and vd[0]["kind"] == "o10_wa_unknown"
              and vd[0]["key"] == "o10u|hook" and "не ответил" in idd["why"]
              and "/v1/configs/webhook" in idd["addr"], "(−) транспорт молчит → НЕИЗВЕСТНО o10u|hook, адрес назван"))
fd2, _ = world(hook_exc=urllib.error.HTTPError(EWI.API_BASE, 503, "x", {}, io.BytesIO(b"")))
res.append(ok(st(fd2)[0] == EX.WAI_UNKNOWN and "HTTP 503" in st(fd2)[1]["why"], "(−) 503 → НЕИЗВЕСТНО"))
fd3, _ = world(hook_exc=urllib.error.HTTPError(EWI.API_BASE, 401, "x", {}, io.BytesIO(b"")))
res.append(ok(st(fd3)[0] == EX.WAI_UNKNOWN and "ключ не принят" in st(fd3)[1]["why"],
              "(−) 401 → НЕИЗВЕСТНО «ключ не принят», а не «в порядке»"))
fd4, _ = world(hook=b"<html>oops</html>")
res.append(ok(st(fd4)[0] == EX.WAI_UNKNOWN and "не JSON" in st(fd4)[1]["why"], "(−) не JSON → НЕИЗВЕСТНО"))
fd5, _ = world(health_body={"something": 1})
res.append(ok(st(fd5)[0] == EX.WAI_UNKNOWN and st(fd5)[1]["what"] == "number",
              "(−) незнакомая форма health_status → НЕИЗВЕСТНО o10u|number"))
fd6, _ = world(hstate="SOMETHING_NEW")
res.append(ok(st(fd6)[0] == EX.WAI_UNKNOWN, "(−) незнакомое состояние номера → НЕИЗВЕСТНО, не «в порядке»"))
fd7, c7 = world(key=None)
res.append(ok(st(fd7)[0] == EX.WAI_UNKNOWN and not c7, "(−) ключа нет → НЕИЗВЕСТНО и ни одного вызова"))
fd8, _ = world(secret=None)
res.append(ok(st(fd8)[0] == EX.WAI_UNKNOWN and "секрет пути" in st(fd8)[1]["why"],
              "(−) секрета пути нет → НЕИЗВЕСТНО «нашего адреса не знаю»"))

# ═══ закрытие и откат ═════════════════════════════════════════════════════════════════════════
print("\n(е) закрытие только по доказанному; откат выключателем 0")
res.append(ok(EX.closures(fa, CFG, ["o10|in"]) == ["o10|in"], "(е) в порядке → эпизод o10|in закрыт"))
res.append(ok(EX.closures(fd, CFG, ["o10|in"]) == [], "(е) 360dialog молчит → ОТКАЗ НЕ закрыт"))
res.append(ok(EX.closures(fb0, CFG, ["o10u|hook"]) == ["o10u|hook"], "(е) факты вернулись → НЕИЗВЕСТНО закрыто"))
CFG0 = EX.config({"EXPECT_WA_INBOUND": "0"})
res.append(ok(not o10(fc, CFG0), "(е) EXPECT_WA_INBOUND=0 → ветка мертва"))
res.append(ok(EJ.heavy({"kind": "o10_wa_inbound"}, None, True)[0] is True
              and EJ.heavy({"kind": "o10_wa_unknown"}, None, True)[0] is False,
              "(е) вес: ОТКАЗ тяжёлый, НЕИЗВЕСТНО лёгкое"))

# ═══ громкость и утечки — через настоящие руки слоя (каналы подменены) ═════════════════════════
print("\n(ж) громкость: ОТКАЗ — владельцу с первого такта, одна тревога на эпизод; утечек нет")
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

_snap["f"] = fc2
r1 = ER.run(now=NOW)
r2 = ER.run(now=NOW + 10 * MIN)
r3 = ER.run(now=NOW + 20 * MIN)
res.append(ok("o10|in" in r1["notes"] and len(sent) == 1 and "WhatsApp не присылает" in sent[0]
              and str(r1.get("wa_inbound")).startswith("ОТКАЗ"),
              "(ж) первый такт: ОТКАЗ → одна заметка каналом демона сразу (отсрочка 0)"))
res.append(ok(len(sent) == 1 and not r2["notes"] and not r3["notes"],
              "(ж) такты 2 и 3: тот же эпизод — новых тревог 0"))
_snap["f"] = fa
r4 = ER.run(now=NOW + 30 * MIN)
res.append(ok("o10|in" in r4["closed"] and len(sent) == 2 and "360dialog снова шлёт нам" in sent[1]
              and any("ОЖИДАНИЕ О10" in j for j in journal),
              "(ж) в порядке → закрытие одной строкой, в журнале «ОЖИДАНИЕ О10»"))
store.clear(), sent.clear(), journal.clear()
_snap["f"] = fd
ER.run(now=NOW)
u2 = ER.run(now=NOW + 61 * MIN)
res.append(ok(not sent and "o10u|hook" in u2["held"], "(ж) НЕИЗВЕСТНО 61 мин → владельцу 0 (лёгкое)"))

# Утечки: каждый вывод каждого прогона выше и ниже — ни ключа, ни секрета, ни нашего адреса.
store.clear()
outs = []
for f in (fa, fb0, fc, fc2, fd, fd2, fd3, fd8, world(hook={"url": FOREIGN_HOST})[0]):
    _snap["f"] = f
    store.clear()
    outs.append(json.dumps(ER.run(now=NOW), ensure_ascii=False, default=str))
    outs.append(EX.wa_inbound_line(*st(f)))
    for v in o10(f):
        outs.append(EX.render(v))
        outs.append(EJ.line(v, "VPS", NOW, NOW, "держится", 1, "x"))
    outs.append(json.dumps(f, ensure_ascii=False))
blob = "\n".join(outs + sent + journal)
res.append(ok(KEY not in blob and SECRET not in blob and OURS not in blob and FOREIGN_HOST not in blob
              and "never-read" not in blob and sent and journal,
              "(−) ключ, секрет, наш и чужой адрес — ни в тревоге, ни в журнале, ни в итоге, ни в фактах"))

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
