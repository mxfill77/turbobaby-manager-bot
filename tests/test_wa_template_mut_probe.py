#!/usr/bin/env python3
"""NIGHT0710-B3g, второй круг: перенесено строителем в наборы дерева из tpl_aux/mut/tests_proposed (регрессия).
Изменено одно: проверка C28 переписана под правило языка второго круга (язык КЛИЕНТА — q_lang — первым, текст
версии запасным; красная команда m4) и дополнена запасным путём (замечание проверяющего З1, мутант R04).

Независимый агент мутантов: проверки, которые ловят ВЫЖИВШИХ мутантов прогона out_1
(T04, C15, C18, C28, C35, S03) и укрепляют два улова, державшихся не на своей проверке (T10/T11 — пойман
только порядком функций в одном процессе; S04 — только чужим e2e-набором службы).

Формат — как у наборов дерева: функции test_*, main печатает PASS/FAIL и ИТОГ. Мир-подделка (World, TplDoor,
Get, Post, listing, svc_door) берётся у соседнего набора test_wa_template_card — его импорт ставит ловушку на
urllib.request.urlopen, сети нет. Живых запросов к провайдеру нет: швы GET/POST — подделки."""
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_wa_template_card as TC  # noqa: E402

A, SVC, S = TC.A, TC.SVC, TC.S
NUM = TC.NUM
OK = '{"messages":[{"id":"wamid.%s"}]}'


def _send(lang, word, get, post):
    return S.send_template(NUM, "reply_request", lang, [word], env=TC.env_door(), get=get, transport=post,
                           sleep=lambda s: None)


# ═══ дверь ══════════════════════════════════════════════════════════════════════════════════

def test_post_language_is_requested_language():
    """T04: тело POST несёт ТОТ код языка, о котором спросили (en → en, ru → ru), и переменную своего языка.
    Иначе клиенту-англичанину уйдёт русский шаблон, а одобрение при этом проверено по паре (имя, en)."""
    for lang, word in (("en", "bike"), ("ru", "байка")):
        get, post = TC.Get(200, TC.listing("approved")), TC.Post([(200, OK % ("L" + lang), None)])
        r = _send(lang, word, get, post)
        assert r["outcome"] == S.SENT and len(post.calls) == 1, (lang, r)
        t = post.calls[0]["template"]
        assert t["name"] == "reply_request" and t["language"] == {"code": lang}, (lang, t)
        assert t["components"][0]["parameters"] == [{"type": "text", "text": word}], (lang, t)


def test_approval_is_fresh_each_send_same_process():
    """T10/T11: одобрение — свежий ответ провайдера на КАЖДУЮ отправку в одном процессе. approved → Meta
    приостановила (paused) → второй POST не уходит, причина словами провайдера; GET спрошен оба раза."""
    get, post = TC.Get(200, TC.listing("approved")), TC.Post([(200, OK % "F1", None)])
    r1 = _send("ru", "байка", get, post)
    assert r1["outcome"] == S.SENT and len(post.calls) == 1, r1
    get.body = TC.listing("paused")
    r2 = _send("ru", "байка", get, post)
    assert r2["outcome"] == S.NOT_SENT and len(post.calls) == 1, (r2, post.calls)
    assert "paused" in r2["reason"] and r2["approval"] == S.TPL_NOT_APPROVED, r2
    assert len(get.calls) == 2, get.calls


# ═══ ядро и карточка ════════════════════════════════════════════════════════════════════════

def test_e2e_en_client_gets_en_template():
    """T04 сквозь ядро: текст версии английский → настоящий `wa_send.send_template` шлёт POST с кодом en и
    {{1}}=bike; в outbox — английский текст шаблона."""
    get, post = TC.Get(200, TC.listing("approved")), TC.Post([(200, OK % "EN1", None)])
    w = TC.World(text=TC.EN)
    w.door = TC.svc_door(w.qpath, get, post)
    w.door.window = lambda number: {"state": "closed", "age": 40 * 3600}
    w.new_core()
    w.draft()
    w.press("wa:tpl:1:1")
    assert len(post.calls) == 1, post.calls
    t = post.calls[0]["template"]
    assert t["language"] == {"code": "en"} and t["components"][0]["parameters"][0]["text"] == "bike", t
    out = w.core.db.execute("SELECT text FROM outbox WHERE wamid='wamid.EN1'").fetchone()
    assert out and out[0] == TC.TPL_EN, out


def test_sending_in_flight_is_taken_for_draft_and_client():
    """C15: строка tpl_out в состоянии sending (отправка идёт) — шаблон «уходит»: ни кнопки, ни второго вызова
    двери — ни по этому черновику, ни по другому черновику того же клиента на то же входящее."""
    w = TC.World()
    w.draft()
    w.core.db.execute("INSERT INTO tpl_out(draft_id, number, upto_id, ver, name, lang, state, who, ts) "
                      "VALUES(1,?,1,1,'reply_request','ru','sending','Дарья',?)", (NUM, TC.T0 + 400))
    off = w.core.template_offer(1, 1)
    assert off and "уходит" in (off.get("why") or ""), off
    w.core.db.execute("UPDATE drafts SET state='declined' WHERE id=1")
    w.core.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,1,?,1,?)",
                      (NUM, A.PENDING, TC.RU, TC.T0 + 600))
    off2 = w.core.template_offer(2, 1)
    assert off2 and "уходит" in (off2.get("why") or ""), off2
    res = w.core.press_template(2, 1, "Дарья")
    assert w.door.tpls == [] and res["ok"] is False, (w.door.tpls, res)


def test_unknown_outcome_card_has_no_template_button():
    """C18: исход «неизвестно» — карточка не зовёт повторить вслепую: на правке нет «📨 Отправить шаблоном»
    (ушёл ли шаблон — не знаем), прежний ряд кнопок жив."""
    w = TC.World()
    w.door.tpl_res = {"outcome": "unknown", "reason": "транспорт молчит", "wamid": None}
    w.draft()
    w.press("wa:tpl:1:1")
    ed = w.http.of("editMessageText")[-1]
    assert "wa:tpl:1:1" not in TC.buttons(ed), TC.buttons(ed)
    assert "wa:send:1:1" in TC.buttons(ed), TC.buttons(ed)


def test_template_language_is_client_language_text_is_fallback():
    """C28 / П28 (редакция второго круга, красная команда m4): язык шаблона — язык КЛИЕНТА: язык его вопроса
    (q_lang) первым, текст версии — запасной, когда q_lang не записан или не ru/en. Клиенту уходит текст шаблона, а
    не версии: латиница версии язык клиента не перебивает."""
    w = TC.World(text=TC.EN)
    w.draft()
    w.core.db.execute("UPDATE drafts SET q_lang='ru' WHERE id=1")
    off = w.core.template_offer(1, 1)
    assert off and off.get("lang") == "ru" and off.get("params") == ["байка"], off
    w2 = TC.World(text=TC.TH)
    w2.draft()
    w2.core.db.execute("UPDATE drafts SET q_lang='en' WHERE id=1")
    off2 = w2.core.template_offer(1, 1)
    assert off2 and off2.get("lang") == "en", off2
    # запасной путь (замечание проверяющего З1, мутант R04): q_lang не записан / other — язык по тексту версии
    for q in (None, "other"):
        w3 = TC.World(text=TC.EN)
        w3.draft()
        w3.core.db.execute("UPDATE drafts SET q_lang=? WHERE id=1", (q,))
        off3 = w3.core.template_offer(1, 1)
        assert off3 and off3.get("lang") == "en" and off3.get("params") == ["bike"], (q, off3)
    # q_lang другого языка, текст без букв — шаблона нет, слова «не ru и не en»
    w4 = TC.World(text="15:00 ✅")
    w4.draft()
    w4.core.db.execute("UPDATE drafts SET q_lang='other' WHERE id=1")
    off4 = w4.core.template_offer(1, 1)
    assert off4 and "не ru и не en" in (off4.get("why") or ""), off4


class NoProbeDoor(A.Door):
    """Дверь без своей пробы окна: базовый `Door.window` → None («окно не измерено»)."""

    def __init__(self):
        self.sends, self.tpls = [], []

    def is_open(self):
        return True

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.NP%d" % len(self.sends)}

    def send_template(self, to, name, lang, params):
        self.tpls.append((to, name, lang, list(params)))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.NPT"}


def test_door_without_probe_is_unknown_window():
    """C35 / П16: дверь без пробы окна (ответ None) — окно НЕ измерено: шаблон не предлагается, «✅ Отправить»
    идёт прежним путём двери. Не измерено ≠ закрыто."""
    w = TC.World(door=NoProbeDoor())
    p = w.draft()
    assert TC.buttons(p) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], TC.buttons(p)
    assert w.core._window(NUM)[0] == "unknown", w.core._window(NUM)
    w.press("wa:send:1:1")
    assert w.door.sends == [(NUM, TC.RU)] and w.door.tpls == [], (w.door.sends, w.door.tpls)


# ═══ служба ═════════════════════════════════════════════════════════════════════════════════

def _svc_env():
    d = tempfile.mkdtemp(prefix="wa_tpl_probe_svc_")
    q = os.path.join(d, "q.db")
    conn = sqlite3.connect(q)
    conn.execute(TC.QSCHEMA)
    conn.commit()
    conn.close()
    return {"agent_db": os.path.join(d, "a.db"), "queue_db": q, "mirror_db": "", "tg_token": "", "show_chat": ""}


def test_svc_build_passes_language_rule():
    """S03: служба приносит ядру правило языка по тексту (`lang_of`) — без него ядро не узнает язык версии и
    шаблон не предложит никому, у кого нет q_lang."""
    core, _tg, _f, _w = SVC.build(_svc_env(), environ={"WA_AGENT_TEMPLATES": "1"}, line=[].append)
    assert core.templates is True
    assert core._tpl_lang(TC.EN, None) == "en" and core._tpl_lang(TC.RU, None) == "ru", (
        core._tpl_lang(TC.EN, None), core._tpl_lang(TC.RU, None))


def test_svc_flag_absent_is_off():
    """S04: переменной WA_AGENT_TEMPLATES нет вовсе — шаблоны ВЫКЛЮЧЕНЫ (умолчание), строка старта «выкл»."""
    lines = []
    core, _tg, _f, _w = SVC.build(_svc_env(), environ={}, line=lines.append)
    assert core.templates is False, core.templates
    assert [ln for ln in lines if ln.startswith("шаблоны (WA_AGENT_TEMPLATES): выкл")], lines


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
