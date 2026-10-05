#!/usr/bin/env python3
"""Карточка черновика по решениям владельца 05.10 12:35 и 12:39 (WACARDUI0510): «✅ Отправить» на КАЖДОЙ версии
(пометка «нужен человек» видна первой), внизу — как считал агент (why версии модели) и проверка чисел кодом.
Всё на подделках (Bot API, дверь, модель) — мир карточки берётся готовым у `test_wa_card_compact`, сети нет.
Фразы клиентов и суммы выдуманы; №16 — синтетика по числам живого случая (итог 39 352, в тексте 40 000).

WA_AGENT_SRC=<каталог> подменяет модули (прогон на базе и мутантов)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import test_wa_card_compact as C  # noqa: E402  — мир карточки на подделках

WHY = "клиент спросил цену PCX на 7 суток; 2 800 — из блока «ЦЕНА»; наличие не знаю"
PRICE16 = {"line": "PCX 160: 7 суток, итого 39 352 ฿"}
TEXT16 = "Здравствуйте! За неделю выйдет 40 000 бат, коллега подтвердит наличие."


class ClaimsModel(C.FakeModel):
    """Подделка адаптера с проверкой чисел кодом: claims — как у живого адаптера (`K.money_claims`)."""

    def __init__(self, claims=None):
        super().__init__()
        self.claims = claims

    def draft(self, number, upto_id):
        out = super().draft(number, upto_id)
        if self.claims is not None:
            out["claims"] = [list(c) for c in self.claims]
        return out


def world(door_open=True, claims=()):
    w = C.World(door_open=door_open)
    w.model = ClaimsModel(list(claims) if claims is not None else None)
    w.core.model = w.model
    return w


def kb(p):
    return [b["callback_data"] for row in p["reply_markup"]["inline_keyboard"] for b in row]


# ═══ п.1: «Отправить» на каждой версии ═══════════════════════════════════════════════════

def test_v1_money_reason_has_send_and_mark_first():
    w = world()
    c1 = C.card(w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, extra=[K.MONEY_CLAIM_WORDS]))
    t = c1["text"]
    assert "wa:send:1:1" in kb(c1), kb(c1)
    assert kb(c1)[0] == "wa:send:1:1", kb(c1)
    notes = t.split("\n\n")[2]
    assert notes.split("\n")[0] == G.W_HAND, notes                  # пометка — первой строкой под ответом
    assert "«Отправить» открыто — сначала проверьте пометку выше" in t, t


def test_v1_press_reaches_door_and_logs_count():
    w = world()
    w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, extra=[K.MONEY_CLAIM_WORDS])
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [(C.NUM, TEXT16)], w.door.sends
    hand = w.core.handoff(1)
    line = [ln for ln in w.lines if "при причинах «нужен человек»" in ln]
    assert len(line) == 1 and (": %d — " % len(hand)) in line[0], (hand, w.lines[-6:])


def test_door_closed_does_not_send():
    w = world(door_open=False)
    c1 = C.card(w.draft("Какой депозит?", extra=[K.MONEY_CLAIM_WORDS]))
    assert "wa:send:1:1" in kb(c1) and G.W_DOOR_CLOSED in c1["text"], (kb(c1), c1["text"])
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [] and w.state()[0] == A.PENDING, (w.door.sends, w.state())


# ═══ п.2: как считал агент и проверка кодом ═════════════════════════════════════════════

def test_why_on_v1_not_on_human_version():
    w = world()
    c1 = C.card(w.draft("Сколько стоит PCX на неделю?", why=WHY))
    assert ("💭 Как считал агент: " + WHY) in c1["text"], c1["text"]
    t = c1["text"]
    assert t.index(G.W_HINT) < t.index("💭 Как считал агент"), t           # после ответа и пометок
    w.feed(w.reply(101, "Готовый текст человека."))
    c2 = C.card(w.http.of("sendMessage")[1:])
    assert "версия 2" in c2["text"] and "💭" not in c2["text"], c2["text"]
    assert kb(c2)[0] == "wa:send:1:2", kb(c2)


def test_empty_why_named():
    w = world()
    t = C.card(w.draft("Привет"))["text"]
    assert "💭 агент не объяснил" in t, t


def test_check_ok_line():
    w = world(claims=[])
    t = C.card(w.draft("Сколько стоит PCX на неделю?"))["text"]
    assert "🔎 числа сверены с блоком «ЦЕНА»" in t, t


def test_draft16_synthetic_40000_in_check():
    claims = K.money_claims(TEXT16, PRICE16)
    assert claims == [("сумма", 40000)], claims
    w = world(claims=claims)
    c1 = C.card(w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, extra=[K.MONEY_CLAIM_WORDS],
                        why="итог из блока «ЦЕНА» 39 352, округлил до 40 000"))
    check = [ln for ln in c1["text"].split("\n") if ln.startswith("🔎")]
    assert len(check) == 1 and "сумма 40 000" in check[0], check
    assert "wa:send:1:1" in kb(c1)


def test_client_gets_only_text():
    w = world(claims=[("сумма", 40000)])
    w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, why="СЛУЖЕБНОЕ-ОБЪЯСНЕНИЕ")
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [(C.NUM, TEXT16)], w.door.sends
    assert not any("СЛУЖЕБНОЕ" in s[1] or "🔎" in s[1] for s in w.door.sends)


def test_core_extra_by_version():
    w = world(claims=[])
    w.draft("Привет", why=WHY)
    e1 = w.core.card_extra(1, 1, C.ANSWER)
    assert e1 and e1["agent"] and e1["why"] == WHY and e1["claims"] == [], e1
    e2 = w.core.card_extra(1, 2, "текст человека")
    assert not (e2 or {}).get("agent"), e2


# ═══ п.3: правило why и предел ══════════════════════════════════════════════════════════

def test_prompt_rule_and_parse_limit():
    import json
    import wa_agent_model as M
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert "13. Поле \"why\"" in p and "блок «ЦЕНА», наши прежние слова" in p, p[-600:]
    got = M.parse_reply(json.dumps({"text": "ok", "lang": "ru", "handoff": [], "why": "w" * 900}))
    assert len(got["why"]) == 600, len(got["why"])


# ═══ п.4: окно ══════════════════════════════════════════════════════════════════════════

def test_block_fits_and_cut_announced():
    why, check = "Ж" * 600, G.W_CHECK_OK
    texts = G.card_texts("T", "Ответ.", "N" * 3300, "D" * 50, agent=(why, check))
    last = texts[-1]
    assert len(last) <= G.CARD_ROOM and all(len(x) <= G.TG_TEXT_MAX for x in texts), [len(x) for x in texts]
    assert "Ответ." in "".join(texts) and check in last and "…обрезано " in last, last[-200:]
    n = int(last.split("…обрезано ")[1].split(" ")[0])
    assert last.count("Ж") + n == len(why), (last.count("Ж"), n)
    # короткий why — целиком, без пометки обрезки
    ok = G.card_texts("T", "Ответ.", "N" * 100, "", agent=("коротко", check))
    assert "💭 Как считал агент: коротко" in ok[-1] and "обрезано" not in ok[-1], ok


def test_long_answer_not_cut_with_block():
    answer = "Ответ клиенту без сокращений. " * 128 + "КОНЕЦ"
    texts = G.card_texts("T", answer, "N" * 100, "", agent=("w" * 600, G.W_CHECK_OK))
    assert answer in "".join(texts[:-1]).replace("T" + G.W_ANSWER_LEAD, "", 1), [len(x) for x in texts]
    assert "💭 Как считал агент: " + "w" * 600 in texts[-1], texts[-1][-200:]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL %s %s: %s" % (name, type(e).__name__, str(e)[:300]))
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
