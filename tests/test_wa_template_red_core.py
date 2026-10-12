#!/usr/bin/env python3
"""NIGHT0710-B3g, второй круг: атаки красной команды на ядро, перенесены строителем в наборы дерева как регрессия
(tpl_aux/red/tests/test_red_tpl_core.py). На кандидате №1 красные: C1, C4b, C7, C7b, C12, C12c, C16 — дефекты
исправлены вторым коммитом. НЕ перенесена C17 (relay в теме при закрытом окне снимает черновик и ставит паузу —
прежняя семантика relay «человек взялся за беседу», и пауза по ней же запрещает шаблон, как ответ с телефона; это
выбор, а не требование блока — ответ словами в артефакте). Добавлены C12d (пауза без эха), C12e (очередь не
прочитана), C12f (ответ с телефона: черновик снят, пауза), C18 (контекст сменился — «устарело»; З1 проверяющего),
C19 (граница C1: возврат в pending только при окне, ИЗМЕРЕННОМ ядром закрытым).

КРАСНАЯ КОМАНДА NIGHT0710-B3g: атаки на ядро и карточку (press_template, _send_closed, template_offer, on_press).

Каркас (World, TplDoor, FakeHttp, svc_door…) берётся ГОТОВЫМ из набора строителя `test_wa_template_card` — тот же
формат мира, чтобы атака не спорила с подделкой. PASS = кандидат устоял, FAIL = сломан (сценарий — в RED.md).
Сети нет: ловушка urlopen ставится при импорте каркаса."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ["PRETOOL_NOPUSH"] = "1"

import test_wa_template_card as B  # noqa: E402  (каркас строителя; его main() не зовётся)

A, K, SVC, G, S = B.A, B.K, B.SVC, B.G, B.S
NUM, T0 = B.NUM, B.T0
OK_POST = (200, '{"messages":[{"id":"wamid.REAL1"}]}', None)


class FakeTime:
    """Подмена time.time: очередь значений на вызовы, потом — последнее. Двери (SendDoor.window, wa_send._door) зовут
    time.time() сами — так моделируется ход времени между пробой окна ядром и воротами двери."""

    def __init__(self, *seq):
        self.seq, self.calls = list(seq), 0
        self._orig = time.time

    def __call__(self):
        self.calls += 1
        if len(self.seq) > 1:
            return self.seq.pop(0)
        return self.seq[0]

    def __enter__(self):
        time.time = self
        return self

    def __exit__(self, *a):
        time.time = self._orig


def real_door(qpath, get=None, post=None, environ=None, clock=None):
    """Настоящая SendDoor: окно — настоящим правилом двери по очереди мира; текст и шаблон — настоящие функции
    wa_send с поддельными швами провайдера."""
    environ = environ or B.env_door()
    post = post or B.Post([OK_POST])
    get = get or B.Get(200, B.listing())
    kw = {"clock": clock} if clock else {}

    def st(to, text, db_path=None):
        return S.send_text(to, text, db_path=db_path, env=environ, transport=post, sleep=lambda s: None)

    def tp(to, n, lg, p, env=None):
        return S.send_template(to, n, lg, p, env=env, get=get, transport=post, sleep=lambda s: None, **kw)
    d = SVC.SendDoor(qpath, environ=environ, send=st, send_template=tp)
    d.post, d.get = post, get
    return d


def world_real(get=None, post=None, clock=None, text=B.RU):
    w = B.World(text=text)
    w.door = real_door(w.qpath, get=get, post=post, clock=clock)
    w.new_core()
    return w


def kinds(post):
    return [c.get("type") for c in post.calls]


# ═══ C1 — окно на границе ровно 24 ч ═════════════════════════════════════════════════════

def test_C1_boundary_24h_send_crosses_into_closed_loses_template():
    """Карточка родилась при открытом окне (23 ч 59 мин). «✅ Отправить» нажато, когда ядро мерит окно на 86399.9 с
    (открыто, `age <= 86400`), а дверь — через доли секунды на 86400.6 с (закрыто). Ядро захватило черновик, дверь
    отказала «окно закрыто — шаблоны не шлём», черновик закрыт not_sent. Ожидание блока: окно закрыто → человеку
    предложен шаблон. Факт: кнопки шаблона нет, черновик закрыт, шаблон по нему не предлагается вовсе."""
    w = world_real()
    with FakeTime(T0 + 3600):
        w.draft()                                            # окно открыто: шаблона на карточке нет
    with FakeTime(T0 + 86399.9, T0 + 86400.6):
        w.press("wa:send:1:1")
    post = w.door.post
    assert post.calls == [], post.calls                     # клиенту ничего не ушло — это верно
    st = w.state()
    offer = w.core.template_offer(1, st[1]) if st else None
    ed = [e for e in w.http.of("editMessageText")]
    has_btn = any("wa:tpl:1:1" in B.buttons(e) for e in ed if e.get("reply_markup"))
    reason = w.core.db.execute("SELECT reason FROM drafts WHERE id=1").fetchone()[0]
    tail = ed[-1]["text"][-160:] if ed else "—"
    # второй круг: строже исходной атаки (там «или») — черновик ждёт И карточка правлена с кнопкой шаблона
    assert st[0] == A.PENDING and offer and has_btn, (
        "черновик %s, шаблон не предлагается (offer=%r, кнопки шаблона на карточке нет); ответ «%s»; причина «%s»; "
        "хвост карточки «%s»" % (st[0], offer, w.answers()[-1] if w.answers() else "—", reason, tail))


def test_C1b_boundary_exact_86400_is_open():
    """Ровно 86400 с — дверь и ядро зовут это ОТКРЫТЫМ (`<=`); шаблон не предлагается, текст уходит. Фиксируем
    согласованность ядра и двери на самой границе (Meta судит сама; правило двери не менялось)."""
    w = world_real()
    with FakeTime(T0 + 3600):
        w.draft()
    with FakeTime(T0 + 86400.0):
        w.press("wa:send:1:1")
    assert kinds(w.door.post) == ["text"], kinds(w.door.post)


def test_C1c_timezone_free():
    """Окно мерится эпохой (ts_msg — секунды Meta, time.time — эпоха): смена пояса процесса не двигает границу."""
    old = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "America/New_York"
        if hasattr(time, "tzset"):
            time.tzset()
        st, info = S.window_state(T0, T0 + 86401)
        assert st == S.WINDOW_CLOSED, (st, info)
        st, info = S.window_state(T0, T0 + 86399)
        assert st == S.WINDOW_OPEN, (st, info)
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        if hasattr(time, "tzset"):
            time.tzset()


# ═══ C2 — клиент пишет между показом кнопки и нажатием ═══════════════════════════════════

def test_C2_client_writes_between_card_and_template_press():
    w = world_real()
    with FakeTime(T0 + 40 * 3600):
        w.draft()
        assert "wa:tpl:1:1" in B.buttons(w.http.of("sendMessage")[-1])
        w.put(T0 + 40 * 3600 - 5)                            # клиент написал (окно открылось), такта ещё не было
        w.press("wa:tpl:1:1")
    assert "template" not in kinds(w.door.post), kinds(w.door.post)
    ans = w.answers()[-1]
    with FakeTime(T0 + 40 * 3600 + 1):
        w.press("wa:send:1:1")                               # совет ответа «жмите ✅ Отправить» — что уйдёт?
    assert kinds(w.door.post) == [], kinds(w.door.post)      # старый черновик НЕ уходит (клиент написал ещё)
    assert w.state()[0] == A.STALE, w.state()
    print("  C2 слова: шаблон → «%s»; затем «Отправить» → «%s»" % (ans, w.answers()[-1]))


def test_C2b_client_writes_during_template_send():
    """Клиент написал, пока шаблон в пути (между проверкой окна и POST): шаблон уходит в открытое окно (безвредно),
    дальше — такт снимает черновик, новый уходит обычной кнопкой, второго шаблона нет."""
    box = {}

    class G2(B.Get):
        def __call__(self, url, key, timeout):
            if not box:
                box["rid"] = w.put(T0 + 40 * 3600 - 1)       # клиент написал, пока шаблон в пути
            return B.Get.__call__(self, url, key, timeout)
    w = world_real(get=G2(200, B.listing()))
    with FakeTime(T0 + 40 * 3600):
        w.draft()
        w.press("wa:tpl:1:1")
        assert kinds(w.door.post) == ["template"], kinds(w.door.post)
        w.core.tick(T0 + 40 * 3600 + 1)
        assert w.state(1)[0] == A.STALE, w.state(1)
        w.core.tick(T0 + 40 * 3600 + 1 + A.QUIET_DEFAULT)
        assert w.state(2) and w.state(2)[0] == A.PENDING, w.state(2)
        card = w.http.of("sendMessage")[-1]
        assert "wa:tpl:2:1" not in B.buttons(card), B.buttons(card)
        w.press("wa:send:2:1", card_id=102)
    assert kinds(w.door.post) == ["template", "text"], kinds(w.door.post)


# ═══ C3 — гонка двух нажатий ═════════════════════════════════════════════════════════════

def test_C3_reentrant_second_press_during_send():
    """Второе нажатие (другой человек) приходит, пока первый шаблон в пути — внутри вызова двери. Ровно один шаблон,
    текст не уходит."""
    w = B.World()
    w.draft()
    inner = []
    orig = w.door.send_template

    def tpl(to, name, lang, params):
        if not inner:
            inner.append(w.core.press_template(1, 1, "Иван"))
            inner.append(w.core.press(1, 1, A.ACT_SEND, "Иван"))
        return orig(to, name, lang, params)
    w.door.send_template = tpl
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1 and w.door.sends == [], (w.door.tpls, w.door.sends)
    assert inner[0]["ok"] is False and "уходит" in inner[0]["words"], inner
    assert inner[1]["ok"] is False, inner


# ═══ C4 — повтор после таймаута отправки ═════════════════════════════════════════════════

def test_C4_post_timeout_unsure_no_repeat_anywhere():
    post = B.Post([(None, "", "timeout"), OK_POST])
    w = world_real(post=post)
    w.draft()
    w.press("wa:tpl:1:1")
    assert kinds(post) == ["template"] and w.tpl_row()[0] == A.UNSURE, (kinds(post), w.tpl_row())
    w.press("wa:tpl:1:1")
    w.press("wa:send:1:1")
    w.new_core()                                             # рестарт
    w.press("wa:tpl:1:1")
    assert kinds(post) == ["template"], kinds(post)


def test_C4b_budget_eaten_by_approval_get_locks_template_forever():
    """Проверка одобрения (GET) съела общий бюджет (медленный провайдер). POST не делался ни разу — клиенту заведомо
    ничего не ушло. Кандидат: дверь → unknown → ядро unsure → «исход неизвестен, проверьте телефон», повтор запрещён
    навсегда (и по черновику, и по клиенту до нового входящего, которого не будет — шаблон не дошёл)."""
    t = [5000.0]

    class SlowGet(B.Get):
        def __call__(self, url, key, timeout):
            t[0] += 61.0
            return B.Get.__call__(self, url, key, timeout)
    post = B.Post([OK_POST])
    w = world_real(get=SlowGet(200, B.listing()), post=post, clock=lambda: t[0])
    w.draft()
    w.press("wa:tpl:1:1")
    assert kinds(post) == [], kinds(post)
    first = w.answers()[-1]
    w.door.get.__class__ = B.Get                             # провайдер снова быстрый
    w.press("wa:tpl:1:1")
    assert kinds(post) == ["template"], ("POST не было, а повтор запрещён: «%s» → «%s»; tpl_out=%r" % (
        first, w.answers()[-1], w.tpl_row()))


# ═══ C5 — подмена имени шаблона в callback_data ══════════════════════════════════════════

def test_C5_callback_substitution():
    w = B.World()
    w.draft()
    for data in ("wa:tpl:1:1:payment_reminder", "wa:tpl:1:1|rental_end_reminder", "wa:tpl_payment_reminder:1:1",
                 "wa:payment_reminder:1:1", "wa:tpl:1:-1", "wa:tpl:1: 1", "wa:tpl::1", "wa:TPL:1:1",
                 "wa:tpl:1:2", "wa:tpl:9:1", "wa:tpl:1:1\x00payment_reminder"):
        w.press(data)
    assert w.door.tpls == [], w.door.tpls
    w.press("wa:tpl:01:01")                                  # ведущие нули — тот же черновик и версия
    assert [t[1] for t in w.door.tpls] in ([], ["reply_request"]), w.door.tpls


def test_C5b_bot_and_foreign_chat_cannot_press():
    w = B.World()
    w.draft()
    w.http.updates.append([w.upd(callback_query={"id": "cqx", "from": {"id": 7, "is_bot": True, "first_name": "b"},
                                                 "data": "wa:tpl:1:1",
                                                 "message": {"message_id": 101, "chat": {"id": B.CHAT}}})])
    w.tg.poll()
    w.http.updates.append([w.upd(callback_query={"id": "cqy", "from": B.HUMAN, "data": "wa:tpl:1:1",
                                                 "message": {"message_id": 101, "chat": {"id": -100999}}})])
    w.tg.poll()
    assert w.door.tpls == [], w.door.tpls


# ═══ C6 — параметр {{1}} из ядра ═════════════════════════════════════════════════════════

def test_C6_param_is_constant_word():
    for text, want in ((B.RU + "\n\n" + "1" * 3000, ["байка"]), (B.EN + "\n" + "2" * 2000, ["bike"])):
        w = B.World(text=text)
        w.draft()
        w.press("wa:tpl:1:1")
        assert w.door.tpls and w.door.tpls[0][3] == want, w.door.tpls


# ═══ C7 — язык клиента не определяется / смешанный ═══════════════════════════════════════

def test_C7_client_lang_known_ru_but_latin_draft_goes_english():
    """Клиент пишет по-русски (q_lang=ru — вердикт кода о языке ВОПРОСА), а версия черновика латиницей (модели или
    человека: «OK, PCX 160 free today»). Шаблон уходит на английском — язык черновика бьёт язык клиента."""
    w = B.World(text="Honda PCX 160 — 350 THB/day, deposit 3000 THB 👍")
    w.draft()
    w.core.db.execute("UPDATE drafts SET q_lang='ru' WHERE id=1")
    offer = w.core.template_offer(1, 1)
    assert offer and offer.get("lang") == "ru", ("клиент ru, шаблон предложен %r" % (offer,))


def test_C7b_language_undetermined_words():
    """Букв нет вовсе (версия «15:00 ✅», язык вопроса не записан) — язык НЕ ОПРЕДЕЛЁН. Слова на карточке обязаны
    говорить «не определён», а не утверждать «язык клиента не ru и не en»."""
    w = B.World(text="15:00 ✅")
    w.draft()
    offer = w.core.template_offer(1, 1)
    assert offer and "why" in offer, offer
    assert "не ru и не en" not in offer["why"], offer["why"]


def test_C7c_mixed_ru_en_picks_majority_visible_on_card():
    for text, want in (("Hello! Здравствуйте! Байк свободен, приезжайте.", "ru"),
                       ("Здравствуйте! Yes, the bike is free, come today please", "en")):
        w = B.World(text=text)
        p = w.draft()
        offer = w.core.template_offer(1, 1)
        assert offer and offer.get("lang") == want, (text, offer)
        tt = S.template_text("reply_request", want, [A.TPL_WORD[want]])
        assert tt in p["text"], "на карточке нет текста шаблона, который уйдёт"


# ═══ C9 — шаблон без нажатия человека (любой путь такта) ═════════════════════════════════

def test_C9_no_template_without_press():
    w = B.World()
    w.core.pace = True
    w.core.followup = True
    w.draft()
    for k in range(1, 400):
        w.core.tick(T0 + A.QUIET_DEFAULT + k * 600)          # 66 ч тактов при закрытом окне
    w.core.relay(777, NUM, "Здравствуйте, это TurboBaby", "Дарья")
    w.press("wa:send:1:1")
    w.press("wa:no:1:1")
    assert w.door.tpls == [], w.door.tpls


# ═══ C12 — человек уже ответил с телефона: шаблон всё равно уходит ═══════════════════════

def test_C12_phone_reply_before_tick_template_still_sent():
    """Черновик ждёт, окно закрыто. Сотрудник ответил клиенту С ТЕЛЕФОНА (эхо в очереди, такт ещё не прошёл —
    до 5 с; при WA_AGENT_DRAFTS выкл — сколь угодно долго). «📨 Отправить шаблоном» → у `press` для такого случая есть
    перепроверка очереди ДО двери (`_fresh` → «ответили с телефона», ничего не уходит), у `press_template` её нет:
    клиент получает шаблон «ответьте, пожалуйста» вслед за живым ответом человека."""
    w = B.World()
    w.draft()
    w.put(T0 + 200, "echo", wamid="wamid.PHONE1")           # ответ с телефона, не наш wamid
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [], ("шаблон ушёл после ответа с телефона: %r; ответ «%s»" % (
        w.door.tpls, w.answers()[-1]))


def test_C12b_same_echo_normal_send_is_refused():
    """Контроль: та же ситуация, окно ОТКРЫТО, «✅ Отправить» — ядро перепроверяет очередь и не шлёт."""
    w = B.World()
    w.door.win = {"state": "open", "age": 3600}
    w.draft()
    w.put(T0 + 200, "echo", wamid="wamid.PHONE1")
    w.press("wa:send:1:1")
    assert w.door.sends == [] and w.state()[0] == A.SUPERSEDED, (w.door.sends, w.state())


def test_C12c_drafts_off_echo_never_scanned_template_sent():
    w = B.World()
    w.draft()
    w.core.drafts = False                                    # WA_AGENT_DRAFTS выкл: скан не идёт, эхо не разбирается
    w.put(T0 + 200, "echo", wamid="wamid.PHONE1")
    for k in range(5):
        w.core.tick(T0 + 1000 + k * 3600)
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [], ("черновики выкл, эхо с телефона 4 ч назад — шаблон ушёл: %r" % (w.door.tpls,))


# ═══ C16 — ушедший шаблон в теме клиента (показ ушедшего агентом, WAMIRROR0410) ═══════════

def test_C16_sent_template_shown_in_client_topic():
    """Обычный ответ, ушедший кнопкой, ложится строкой в тему клиента (`show_agent` ← `drafts`). Шаблон — тоже
    сообщение, ушедшее через API от имени агента; эха у него нет. Проверяем: появится ли он в теме клиента."""
    w = B.World()
    w.draft()
    w.press("wa:tpl:1:1")
    assert w.door.tpls, w.door.tpls
    for k in range(3):
        w.core.tick(B.T0 + 600 + k * 60)
    shown = [p for p in w.http.of("sendMessage") if str(p.get("chat_id")) == B.SHOW]
    assert any(B.TPL_RU in str(p.get("text")) or "reply_request" in str(p.get("text")) for p in shown), (
        "в тему клиента не легло ни строки о шаблоне; строк в показ: %d" % len(shown))


def test_C16b_control_normal_send_is_shown():
    w = B.World()
    w.door.win = {"state": "open", "age": 3600}
    w.draft()
    w.press("wa:send:1:1")
    for k in range(3):
        w.core.tick(B.T0 + 600 + k * 60)
    shown = [p for p in w.http.of("sendMessage") if str(p.get("chat_id")) == B.SHOW]
    assert any(B.RU in str(p.get("text")) for p in shown), shown


# ═══ C17 — человек сперва пишет в теме клиента (естественный ход): дверь отказала, шаблона больше нет ═══

def test_C12d_paused_client_no_template():
    """Второй круг: клиент на паузе (человек вмешался) без нового эха — шаблон не уходит, как не уходит «Отправить»."""
    w = B.World()
    w.draft()
    w.core.db.execute("UPDATE clients SET paused=1 WHERE number=?", (B.NUM,))
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and w.state()[0] == A.SUPERSEDED, (w.door.tpls, w.state())
    assert "пауз" in w.answers()[-1], w.answers()


def test_C12e_queue_unread_no_template_draft_waits():
    """Второй круг: очередь не прочитана при нажатии «📨» — наружу ничего, черновик ждёт, слова названы."""
    w = B.World()
    w.draft()

    def boom(number, after_id, inbound=True):
        raise OSError("очередь недоступна")
    w.core._fresh = boom
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and w.state()[0] == A.PENDING, (w.door.tpls, w.state())
    assert "очередь не прочитана" in w.answers()[-1], w.answers()


def test_C12f_phone_reply_closes_draft_and_pauses():
    """Второй круг: ответ с телефона до нажатия «📨» — черновик снят (superseded), клиент на паузе, слова названы."""
    w = B.World()
    w.draft()
    w.put(T0 + 200, "echo", wamid="wamid.PHONE2")
    w.press("wa:tpl:1:1")
    paused = w.core.db.execute("SELECT paused FROM clients WHERE number=?", (B.NUM,)).fetchone()[0]
    assert w.door.tpls == [] and w.state()[0] == A.SUPERSEDED and paused == 1, (w.door.tpls, w.state(), paused)
    assert "ответили с телефона" in w.answers()[-1], w.answers()


def test_C18_context_changed_template_outdated():
    """Второй круг (замечание проверяющего З1, мутанты R03/RM01): версия контекста беседы сменилась после черновика
    (`clients.ctx` ≠ `drafts.ctx`) — «📨» отвечает «устарело», шаблон не уходит, черновик ждёт пересборки."""
    w = B.World()
    w.draft()
    w.core.db.execute("UPDATE clients SET ctx=ctx+1 WHERE number=?", (B.NUM,))
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and "устарело" in w.answers()[-1], (w.door.tpls, w.answers())


class _NoProbeClosedDoor(A.Door):
    """Дверь без пробы окна (окно ядру не измерено), а ворота текста отказывают «окно закрыто»."""

    def __init__(self):
        self.sends, self.tpls = [], []

    def is_open(self):
        return True

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": "not_sent", "reason": "окно закрыто (последнее сообщение клиента 30 ч назад, предел 24 ч) "
                "— шаблоны не шлём", "wamid": None, "window": "closed"}

    def send_template(self, to, name, lang, params):
        self.tpls.append((to, name, lang, list(params)))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.NPC"}


def test_C19_door_refused_closed_but_window_unmeasured_old_path():
    """Второй круг (граница C1): возврат черновика в pending с шаблоном — ТОЛЬКО если ядро само измерило окно
    закрытым. Окно не измерено (у двери нет пробы), а ворота отказали «окно закрыто» — прежний путь: черновик
    not_sent, шаблон не предлагается (не измерено ≠ закрыто, П16)."""
    w = B.World(door=_NoProbeClosedDoor())
    w.draft()
    w.press("wa:send:1:1")
    assert w.state()[0] == A.NOT_SENT and w.door.tpls == [], (w.state(), w.door.tpls)
    assert w.core.template_offer(1, 1) is None


def _not_taken_C17_topic_relay_refused_kills_template_option():
    # НЕ ПЕРЕНЕСЕНА строителем во втором круге (имя без test_ — набор её не зовёт): атакует выбор семантики relay,
    # а не требование блока; ответ словами — артефакт NIGHT0710-B3g, раздел «Проверка», m3.
    """Окно закрыто, на карточке «📨». Сотрудник пишет клиенту в ТЕМЕ (relay): дверь отказывает «окно закрыто»,
    клиенту НЕ ушло ничего. Но `human_wrote` уже снял черновик (superseded) и поставил паузу — кнопки шаблона больше
    нет, а слова отказа зовут «напишите с телефона», о шаблоне ни слова."""
    w = B.World()
    w.draft()
    res = w.core.relay(777, B.NUM, "Здравствуйте! Вы ещё с нами?", "Дарья")
    assert res["outcome"] == "not_sent", res
    st = w.state()
    offer = w.core.template_offer(1, st[1])
    w.press("wa:tpl:1:1")
    assert w.door.tpls or (offer and offer.get("name")), (
        "клиенту не ушло ничего (relay: %s), а шаблон больше не предлагается: черновик %s, ответ кнопки «%s»" % (
            res["words"], st[0], w.answers()[-1]))


# ═══ C15 — выключатель: окно ядро не спрашивает, кнопки нет ═══════════════════════════════

def test_C15_flag_off_no_window_probe_no_table():
    w = B.World(templates=False)
    p = w.draft()
    w.press("wa:send:1:1")
    w.press("wa:tpl:1:1")
    assert w.door.wcalls == 0 and w.door.tpls == [] and "шаблон" not in p["text"].lower(), (w.door.wcalls,)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:500])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
