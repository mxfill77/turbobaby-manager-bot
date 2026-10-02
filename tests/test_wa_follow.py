#!/usr/bin/env python3
"""Напоминание притихшему (WAFOLLOWUP0210): последнее слово наше и FOLLOW_QUIET тишины клиента, окно 24 ч
открыто, напоминаний в беседе меньше FOLLOW_MAX — черновик-напоминание модели с карточкой на «Отправить»;
модель вправе сказать «не нужно» (карточки нет, строка журнала); клиент написал до нажатия — «устарело»;
выключатель WA_AGENT_FOLLOWUP по умолчанию выключен.
Всё на подделках: временная очередь схемой wa_webhook, временная база агента, модель/Telegram/дверь —
подделки из test_wa_agent и test_wa_agent_model. Сети нет, модель не зовётся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import test_wa_agent as TA  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402

NUM, T0 = TA.NUM, TA.T0
FOLLOW = "Напомню: подобрать вам байк на даты?"


class FollowModel(TA.FakeModel):
    """Модель черновика из test_wa_agent + напоминание: текст, {skip}, None или исключение."""

    def __init__(self, follow=FOLLOW, **kw):
        super().__init__(**kw)
        self.follow, self.fcalls = follow, []

    def followup(self, number, upto_id):
        self.fcalls.append((number, upto_id))
        if isinstance(self.follow, Exception):
            raise self.follow
        return self.follow


class FollowTG(TA.FakeTG):
    def __init__(self):
        super().__init__()
        self.texts = {}

    def card(self, draft_id, ver, number, text):
        self.texts[draft_id] = text
        return super().card(draft_id, ver, number, text)


class FWorld(TA.World):
    def __init__(self, follow=True, pace=False, model=None, **kw):
        self.follow_on, self.pace, self.lines = follow, pace, []
        super().__init__(model=model or FollowModel(), **kw)
        self.tg = FollowTG()
        self.core.tg = self.tg

    def new_core(self):
        return A.Core(self.dbpath, self.qpath, self.model, getattr(self, "tg", None) or FollowTG(), self.door,
                      followup=self.follow_on, pace=self.pace, rand=lambda: 0.5, log=self.lines.append)

    def tick(self, t):
        """Такт без ограничителя «раз в минуту» (его проверяет свой тест)."""
        self.core._follow_last = None
        return self.core.tick(t)

    def follows(self, state=None):
        db = sqlite3.connect(self.dbpath)
        rows = db.execute("SELECT id, state, text FROM drafts WHERE kind=? ORDER BY id", (A.KIND_FOLLOW,)).fetchall()
        db.close()
        return [r for r in rows if state is None or r[1] == state]


def answered(w, t=T0):
    """Клиент пишет в t, черновик, «Отправить» в t+80 — ушло. → время нашего ответа (outbox)."""
    w.put(t)
    w.tick(t + A.QUIET_DEFAULT)
    d = w.drafts(A.PENDING)
    assert len(d) == 1, d
    res = w.core.press(d[0][0], 1, A.ACT_SEND, "owner", now=t + 80)
    assert res["state"] == A.SENT, res
    return t + 80


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_silence_15min_one_draft():
    w = FWorld()
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET - 1)
    assert w.follows() == [] and w.model.fcalls == [], "напоминание раньше 15 мин"
    made = w.tick(ours + A.FOLLOW_QUIET)
    f = w.follows()
    assert len(f) == 1 and f[0][1] == A.PENDING and f[0][2] == FOLLOW and made == [f[0][0]], (f, made)
    assert w.tg.texts.get(f[0][0]) == FOLLOW and len(w.model.fcalls) == 1, (w.tg.texts, w.model.fcalls)
    w.tick(ours + A.FOLLOW_QUIET + 600)
    assert len(w.follows()) == 1 and len(w.model.fcalls) == 1, "второй черновик на ту же тишину"
    res = w.core.press(f[0][0], 1, A.ACT_SEND, "owner", now=ours + 1000)
    assert res["state"] == A.SENT and w.door.sends[-1] == (NUM, FOLLOW), (res, w.door.sends)


def test_third_reminder_no():
    w = FWorld()
    t = answered(w)
    for i in range(2):
        w.tick(t + A.FOLLOW_QUIET)
        f = w.follows(A.PENDING)
        assert len(f) == 1, (i, w.follows())
        t = t + A.FOLLOW_QUIET + 10
        assert w.core.press(f[0][0], 1, A.ACT_SEND, "owner", now=t)["state"] == A.SENT
    w.tick(t + A.FOLLOW_QUIET)
    w.tick(t + 3 * A.FOLLOW_QUIET)
    assert len(w.follows()) == 2 and len(w.model.fcalls) == 2, (w.follows(), w.model.fcalls)
    assert len(w.door.sends) == 3, w.door.sends                        # ответ + два напоминания


def test_new_talk_resets_count():
    w = FWorld()
    t = answered(w)
    for _ in range(2):
        w.tick(t + A.FOLLOW_QUIET)
        t = t + A.FOLLOW_QUIET + 10
        w.core.press(w.follows(A.PENDING)[0][0], 1, A.ACT_SEND, "owner", now=t)
    t2 = answered(w, t + A.PACE_NEW_TALK + 3600)                     # клиент вернулся через 5 ч — беседа новая
    w.tick(t2 + A.FOLLOW_QUIET)
    assert len(w.follows(A.PENDING)) == 1, w.follows()


def test_after_decline_same_silence_not_again():
    w = FWorld()
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    did = w.follows()[0][0]
    assert w.core.press(did, 1, A.ACT_DECLINE, "owner", now=ours + 1000)["state"] == A.DECLINED
    w.tick(ours + 3000)
    assert len(w.follows()) == 1 and len(w.model.fcalls) == 1, "на ту же тишину спросили второй раз"


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_client_wrote_stale():
    w = FWorld()
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    did = w.follows()[0][0]
    w.put(ours + 950)                                                 # клиент написал сам
    w.tick(ours + 960)
    assert w.follows()[0][1] == A.STALE, w.follows()
    words = [x for d, x in w.tg.done if d == did]
    assert words and "устарело" in words[-1] and "напоминание не нужно" in words[-1], w.tg.done
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=ours + 970)
    assert not res["ok"] and len(w.door.sends) == 1, (res, w.door.sends)


def test_client_wrote_unscanned_press_stale():
    w = FWorld()
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    did = w.follows()[0][0]
    w.put(ours + 950)                                                 # такт ещё не видел
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=ours + 951)
    assert res["state"] == A.STALE and len(w.door.sends) == 1, (res, w.door.sends)


def test_window_closed_no():
    for dt, want in ((A.FOLLOW_WINDOW - A.FOLLOW_SPARE - 5, 1), (A.FOLLOW_WINDOW - A.FOLLOW_SPARE + 5, 0),
                     (A.FOLLOW_WINDOW + 3600, 0)):
        w = FWorld()
        answered(w)                                                   # клиент писал в T0
        w.tick(T0 + dt)
        assert len(w.follows()) == want and len(w.model.fcalls) == want, (dt, w.follows(), w.model.fcalls)


def test_window_rule_equals_wa_send():
    # wa_send.py — из корня дерева (у мутантов wa_agent.py лежит в своём каталоге, двери там нет)
    src = open(os.path.join(ROOT, "wa_send.py"), encoding="utf-8").read()
    m = re.search(r"^WINDOW_SECS\s*=\s*(\d+)", src, re.M)
    assert m and int(m.group(1)) == A.FOLLOW_WINDOW, (m and m.group(1), A.FOLLOW_WINDOW)


def test_owner_numbers():
    # слова владельца и задания: «через 15 минут тишины», «не больше двух на беседу»
    assert A.FOLLOW_QUIET == 15 * 60 and A.FOLLOW_MAX == 2, (A.FOLLOW_QUIET, A.FOLLOW_MAX)


def test_model_not_needed_no_card():
    w = FWorld(model=FollowModel(follow={"skip": True, "why": "попрощался"}))
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    assert w.follows() == [] and len(w.tg.cards) == 1, (w.follows(), w.tg.cards)   # только карточка ответа
    assert any("не нужно, карточки нет" in ln for ln in w.lines), w.lines
    w.tick(ours + 3 * A.FOLLOW_QUIET)
    assert len(w.model.fcalls) == 1, "«не нужно» спрошено второй раз на ту же тишину"


def test_switch_off_nothing():
    w = FWorld(follow=False)
    ours = answered(w)
    for dt in (A.FOLLOW_QUIET, 3600, 6 * 3600):
        w.tick(ours + dt)
    assert w.follows() == [] and w.model.fcalls == [] and len(w.tg.cards) == 1, (w.follows(), w.model.fcalls)


def test_core_default_off():
    w = TA.World()
    assert w.core.followup is False


def test_svc_switch():
    import wa_agent_svc as SV
    w = TA.World()
    env = {"queue_db": w.qpath, "agent_db": os.path.join(os.path.dirname(w.dbpath), "svc.db"),
           "tg_token": "123:SECRET", "show_chat": "-1004401325262", "mirror_db": ""}
    for environ, on in (({}, False), ({"WA_AGENT_FOLLOWUP": "1"}, True), ({"WA_AGENT_FOLLOWUP": "да"}, False)):
        lines = []
        core, _tg, _f, _w = SV.build(env, environ=environ, model=FollowModel(), http=TM.FakeHttp(),
                                     line=lines.append)
        assert core.followup is on, (environ, core.followup)
        assert any(ln.startswith("напоминание (WA_AGENT_FOLLOWUP): " + ("вкл" if on else "выкл")) for ln in lines), lines
        core.db.close()


def test_paused_no_followup():
    w = FWorld()
    ours = answered(w)
    w.put(ours + 10, kind="echo")                                     # человек ответил с телефона — пауза
    w.tick(ours + 20)
    assert w.paused()[0] == 1
    w.tick(ours + 10 + 2 * A.FOLLOW_QUIET)
    assert w.follows() == [] and w.model.fcalls == [], w.follows()


def test_client_last_word_no():
    w = FWorld()
    w.put(T0)
    w.tick(T0 + A.QUIET_DEFAULT)
    did = w.drafts(A.PENDING)[0][0]
    w.core.press(did, 1, A.ACT_DECLINE, "owner", now=T0 + 80)          # «Не нужно»: нашего ответа нет
    w.tick(T0 + 2 * A.FOLLOW_QUIET)
    assert w.follows() == [] and w.model.fcalls == [], w.follows()


def test_reaction_breaks_silence():
    w = FWorld()
    ours = answered(w)
    w.put(ours + 100, msg_type="reaction")                            # клиент поставил реакцию
    w.tick(ours + 2 * A.FOLLOW_QUIET)
    assert w.follows() == [] and w.model.fcalls == [], w.follows()


def test_model_fail_retry_later():
    w = FWorld(model=FollowModel(follow=None))
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    w.tick(ours + A.FOLLOW_QUIET + 60)
    assert w.follows() == [] and len(w.model.fcalls) == 1, w.model.fcalls
    w.model.follow = FOLLOW
    w.tick(ours + A.FOLLOW_QUIET + A.MODEL_RETRY_SEC)
    assert len(w.follows()) == 1 and len(w.model.fcalls) == 2, (w.follows(), w.model.fcalls)


def test_model_crash_no_draft():
    w = FWorld(model=FollowModel(follow=RuntimeError("x")))
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    assert w.follows() == [] and any("модель упала" in ln for ln in w.lines), w.lines


def test_client_wrote_while_model_thought():
    w = FWorld()
    ours = answered(w)
    orig = w.model.followup

    def during(number, upto_id):
        w.put(ours + 905)
        return orig(number, upto_id)
    w.model.followup = during
    w.tick(ours + A.FOLLOW_QUIET)
    assert w.follows() == [], w.follows()


def test_once_a_minute():
    w = FWorld()
    ours = answered(w)
    w.core.tick(ours + A.FOLLOW_QUIET - 1)                            # поиск был минуту назад
    w.core.tick(ours + A.FOLLOW_QUIET)
    assert w.follows() == [], "поиск чаще раза в минуту"
    w.core.tick(ours + A.FOLLOW_QUIET - 1 + A.FOLLOW_EVERY)
    assert len(w.follows()) == 1, w.follows()


def test_pace_not_for_followup():
    w = FWorld()
    ours = answered(w)
    w.core.pace = True
    w.tick(ours + A.FOLLOW_QUIET)
    res = w.core.press(w.follows()[0][0], 1, A.ACT_SEND, "owner", now=ours + A.FOLLOW_QUIET + 1)
    assert res["state"] == A.SENT and w.door.sends[-1] == (NUM, FOLLOW), res


def test_journal_no_client_text_or_number():
    w = FWorld()
    ours = answered(w)
    w.tick(ours + A.FOLLOW_QUIET)
    w.put(ours + 950)
    w.tick(ours + 960)
    assert any("напоминание" in ln for ln in w.lines), w.lines
    assert not any(NUM in ln or FOLLOW in ln for ln in w.lines), w.lines


# ═══ руки и адаптер модели ═══════════════════════════════════════════════════════════════

FOLLOW_JSON = json.dumps({"skip": False, "text": FOLLOW, "lang": "ru", "why": "клиент выбирал байк"},
                         ensure_ascii=False)
SKIP_JSON = json.dumps({"skip": True, "text": "", "why": "клиент попрощался"}, ensure_ascii=False)


def test_tg_card_marked_reminder():
    w = TM.World()
    w.core.followup = True
    w.put(T0, "Есть PCX на завтра?")
    w.core.tick(T0 + 100)
    did = w.core.db.execute("SELECT id FROM drafts").fetchone()[0]
    assert w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 110)["state"] == A.SENT
    w.call.reply = FOLLOW_JSON
    w.core._follow_last = None
    w.core.tick(T0 + 110 + A.FOLLOW_QUIET)
    fdid = w.core.db.execute("SELECT id FROM drafts WHERE kind=?", (A.KIND_FOLLOW,)).fetchone()[0]
    body = w.http.of("sendMessage")[-1]["text"]
    assert body.startswith("🔔 Напоминание №%d" % fdid) and "НАПОМИНАНИЕ" in body and FOLLOW in body, body
    kb = w.http.of("sendMessage")[-1]["reply_markup"]["inline_keyboard"][0]
    assert kb[0]["callback_data"] == "wa:send:%d:1" % fdid, kb
    sysp, user = w.call.calls[-1]
    assert sysp == WM.FOLLOW_SYSTEM_PROMPT and "Есть PCX на завтра?" in user, user[-300:]
    w.put(T0 + 1100, "ещё думаю")
    w.core.tick(T0 + 1101)
    edits = w.http.of("editMessageText")
    assert edits and "устарело" in edits[-1]["text"], edits


def test_adapter_parse_followup():
    assert WM.parse_followup(SKIP_JSON) == {"skip": True, "why": "клиент попрощался"}
    got = WM.parse_followup(FOLLOW_JSON)
    assert got["text"] == FOLLOW and got["lang"] == "ru", got
    for raw in ("не JSON", "[]", json.dumps({"skip": False, "text": ""}), json.dumps({"skip": "yes"})):
        assert WM.parse_followup(raw) is None, raw
    assert A.follow_out({"skip": True, "why": "x"}) == ("skip", "x")
    assert A.follow_out(FOLLOW) == ("text", FOLLOW)
    assert A.follow_out(None) == ("fail", None) and A.follow_out("  ") == ("fail", None)


def test_adapter_followup_masked():
    w = TM.World(reply=SKIP_JSON)
    w.put(T0, "пароль от wifi: Qwerty12345zz, сколько стоит PCX?")
    out = w.adapter.followup(TM.NUM, 10 ** 9)                        # номер подделок модели — свой
    assert out == {"skip": True, "why": "клиент попрощался"}, out
    _sysp, user = w.call.calls[-1]
    assert "Qwerty12345zz" not in user and "[скрыто: пароль]" in user, user[-300:]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
