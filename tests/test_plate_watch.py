"""НОМЕР НА БАЙКЕ ↔ ИМЯ ТЕМЫ ↔ ЗЕЛЁНАЯ КНИГА (25.10.2026, PLATEWATCH2510; ревью r2 — 25.10).

Правило владельца 25.10: имя темы обслуживания идёт за номером, ФИЗИЧЕСКИ стоящим на байке;
расхождение с зелёной книгой — предупреждение. Повод — переход 24.10 на номера из зелёных книг,
а снимки показывают старые таблички: 83 — 2478 при книге 9286, 1190 — 9315 при 8676.

Предмет — четыре вещи:
  1  РЕШЕНИЕ `plate_watch` (чистое, импортов ноль): какое чтение годится, номер темы, предложение
     имени, два НЕЗАВИСИМЫХ чтения (разные отправки и снимки, ≥ 6 ч) за 14 суток, все чтения окна
     согласны, номер другого байка / на цифру от номера темы или книги / часть номера / объём — тишина,
     имени бота не верим (дрейф) или тема привязана руками — тишина, висящая карточка, её проверка
     в момент нажатия, «Оставить», предупреждение раз в 7 суток;
  2  ПРОМПТ снимка: поле `plate` — только табличка на САМОМ байке; `PLATE_WATCH=0/false` — промпт
     БЕЗ поля, байт-в-байт прежний;
  3  ЖИВОЙ `splinter.handle` + кнопки `svc:plren` / `svc:plkeep`: 83 и 1190 — карточка, 82 — ничего,
     в тему байка от ветки не уходит НИ ОДНОГО сообщения, сверка — фоновой задачей под одним замком
     (одна карточка на две сверки, «Оставить» во время отправки не теряется), нажимает только
     владелец и только на сообщении карточки, предупреждение без кнопок — в ленту, а не в инбокс,
     битая память — тишина, TOPIC_NOT_MODIFIED — успех, `_bike_topic_id` находит тему по номеру;
  4  ДРЕЙФ ИМЕНИ ТЕМЫ: обычное сообщение (reply на сообщение создания) больше не возвращает теме
     ПЕРВОЕ имя — живой случай 82, 21.10 09:23:30 UTC «5104» → «3902»; у имени есть происхождение.
  r3 (ревью 25.10, тесты `test_r3_*`): прежний номер чужого байка и номер не последним словом имени —
     «номер другого байка»; переименование — только в номер книги или в прежний номер из пары карты
     моста, иначе заметка без кнопок; объём последним словом — не номер; чтения окна не обрезаются;
     оборванная отправка не держит место; PLATE_WATCH=0 разоружает кнопки; замок проверен нажатием
     во время отправки.

Сеть, Telegram, мост, модель и memory.db — заглушки; зелёная книга — настоящий
`plate_watch_book.json` из корня дерева. Память и ВСЕ файлы состояния splinter — во временном
каталоге (ревью r2 M2: сьют гонит живой `S.handle` с боевыми номерами тем 82, 83, 1190).
"""
import ast
import asyncio
import json
import os
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # дерево, которое судим
sys.path.insert(0, ROOT)
_TMP = tempfile.gettempdir()
_RUN = f"{os.getpid()}_{int(time.time() * 1000)}"     # своё имя на прогон: прежний прогон с тем же pid не подмешается


def _tmpf(tag, ext=".json"):
    return os.path.join(_TMP, f"tb_plate_{tag}_{_RUN}{ext}")


# Файлы состояния splinter — ВНЕ живого дерева, как у соседних сьютов того же дня (test_servicing_tidy,
# test_service_receipt_cost): без этого прогон мимо гейта писал бы ленту тем 82/83/1190 в боевой topic_feed/.
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("NOTIFY_COUNT_FILE", _tmpf("notify", ".txt"))
os.environ.setdefault("TOPIC_FEED_DIR", os.path.join(_TMP, f"tb_plate_feed_{_RUN}"))
os.environ.setdefault("MILEAGE_Q_STATE", _tmpf("mileage_q"))
os.environ.setdefault("DECIDER_LIVE_STATE", _tmpf("dlive"))
os.environ.setdefault("RESTART_HANDOFF_STATE", _tmpf("handoff"))
os.environ.setdefault("AUTOBOOK_CANCEL_STATE", _tmpf("abc"))
os.environ.setdefault("HINT_DEDUP_STATE", _tmpf("hint"))
os.environ.setdefault("WORKS_PERSIST_STATE", _tmpf("works"))
os.environ.setdefault("SVC_TOKENS_STATE", _tmpf("svc_tokens"))
os.environ["TOPIC_DECIDER_LIVE"] = "0"
os.environ["ACT_GATE"] = "0"            # предмет сьюта — номер темы; ворота судит tests/test_act_gate.py
os.environ["PLATE_WATCH"] = "1"
os.environ["PLATE_WATCH_STATE"] = _tmpf("plate")

import notify                # noqa: E402
import plate_watch as PW     # noqa: E402
import splinter as S         # noqa: E402

DAY = 86400.0
GAP = 7 * 3600.0             # больше PW.MIN_GAP_S: свидетели с разных заходов
NOW = 1792915200.0           # 25.10.2026 00:00 UTC
SERV = S.SERVICING_CHAT
OWNER = ("turbophuket1", 6879003264)          # бизнес-аккаунт владельца (OWNER_IDS)
PYM = ("pleummmm", 99001)                     # доверенный, но НЕ владелец
N83, N82, N1190 = "XADV 750CC GREY 9286", "XADV 750CC BLACK 5104", "XMAX 300CC NEW BROWN 8676"
with open(os.path.join(ROOT, "plate_watch_book.json"), encoding="utf-8") as _f:
    BOOK = json.load(_f)


def _book(topic):
    return PW.book_entry(BOOK, topic)


def _plate(d, legible=True, series=None):
    return {"kind": "bike", "dirt": False, "damage": None, "fuel": None, "mileage": None, "notes": "байк",
            "plate": {"digits": d, "series": series, "province": "Phuket", "legible": legible}}


def _st(topic, *reads, base=NOW, st=None):
    """Память с чтениями: reads = (цифры, mid[, отправка[, возраст в сутках[, file_unique_id]]]). Без возраста
    чтения идут через GAP, последнее — в `base`."""
    st = PW.clean(st)
    n = len(reads)
    for i, r in enumerate(reads):
        d, mid = r[0], r[1]
        grp = r[2] if len(r) > 2 else None
        age = r[3] if len(r) > 3 and r[3] is not None else (n - 1 - i) * GAP / DAY
        fu = r[4] if len(r) > 4 else None
        st = PW.add_reading(st, topic, {"d": d}, mid, grp, base - age * DAY, fu=fu)
    return st


def _v(st, topic, name, now=NOW, src=None, others=None):
    return PW.verdict(st, topic, name, _book(topic), now, src=src, others=others)


# ============================================================================================
#  (0) СРЕДА СЬЮТА — ничего в живое дерево (ревью r2 M2)
# ============================================================================================
def test_suite_state_is_redirected():
    for k in ("TOPIC_FEED_DIR", "MILEAGE_Q_STATE", "DECIDER_LIVE_STATE", "RESTART_HANDOFF_STATE",
              "AUTOBOOK_CANCEL_STATE", "HINT_DEDUP_STATE", "WORKS_PERSIST_STATE", "SVC_TOKENS_STATE",
              "PLATE_WATCH_STATE", "NOTIFY_COUNT_FILE"):
        v = os.environ.get(k)
        assert v and not os.path.abspath(v).startswith(ROOT + os.sep), (k, v)
    assert os.environ.get("PRETOOL_NOPUSH") == "1" and os.environ.get("TOPIC_DECIDER_LIVE") == "0"
    assert not os.path.abspath(S._dlive_path()).startswith(ROOT + os.sep), S._dlive_path()


# ============================================================================================
#  (1) РЕШЕНИЕ — чистое
# ============================================================================================
def test_module_is_pure():
    src = open(os.path.join(ROOT, "plate_watch.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == [], [ast.dump(n) for n in imports]
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not used & {"open", "eval", "exec", "__import__", "input"}, used


def test_engine_sizes_mirror_splinter():
    assert PW.ENGINE_CC == frozenset(S._CC_PLATE), (PW.ENGINE_CC ^ frozenset(S._CC_PLATE))


def test_reading_only_legible_digits():
    assert PW.reading(_plate("2478", series="2กจ")) == {"d": "2478", "series": "2กจ", "province": "Phuket"}
    assert PW.reading(_plate("2478", legible=False)) is None          # байк на фоне / смазано
    assert PW.reading(_plate("2478", legible="true")) is None         # только булево «да»
    assert PW.reading(_plate("24 78"))["d"] == "2478"
    assert PW.reading(_plate("๒๔๗๘"))["d"] == "2478"                  # тайские цифры
    assert PW.reading(_plate(461))["d"] == "461"
    # две цифры — не номер для моста: строку Лист1 он ищет по числу от трёх цифр (plateFromName_)
    for bad in ("24781", "47", "0047", "", "2กจ", None, "24?8", True):
        assert PW.reading(_plate(bad)) is None, bad
    for bad in (None, {}, {"plate": None}, {"plate": "2478"}, "мусор"):
        assert PW.reading(bad) is None, bad


def test_topic_plate_is_the_last_word():
    assert PW.topic_plate("XADV 750CC GREY 9286") == "9286"
    assert PW.topic_plate("CB 300CC R 461") == "461"
    assert PW.topic_plate("XADV 750 BLACK") is None                    # «750» — объём, не номер
    assert PW.topic_plate("5104") is None and PW.topic_plate(None) is None
    assert PW.topic_plate("NMAX 155CC 12") is None                      # две цифры мост не узнает
    # номер темы совпадает с тем, что мост берёт из имени (зеркало plateFromName_) — на всём парке книги
    for b in BOOK["bikes"]:
        assert PW.topic_plate(b["name"]) == S._plate_from_name(b["name"]) == b["plate_digits"], b["name"]
    assert PW.propose("XADV 750CC GREY 9286", "2478") == "XADV 750CC GREY 2478"
    assert PW.propose("XADV 750 BLACK", "2478") is None


def test_greenbook_file_names_live_topics():
    # своё имя файла, не прежнее greenbook_plates.json: неотслеживаемая копия того на сервере не остановит pull (S9)
    assert S._PLATE_BOOK_FILE == os.path.join(ROOT, "plate_watch_book.json")
    assert _book(83)["d"] == "9286" and _book(83)["series"] == "2กจ" and _book(83)["name"] == N83
    assert _book(1190)["d"] == "8676" and _book(82)["d"] == "5104"
    assert _book(62)["d"] == "5662" and _book(66)["d"] == "461"
    assert _book(999999) is None and PW.book_entry(None, 83) is None
    assert PW.book_topic(BOOK, "9286") == 83 and PW.book_topic(BOOK, "2478") is None


def test_live_83_two_readings_rename_with_warning():
    st = _st(83, ("2478", 4411), ("2478", 4520))
    v = _v(st, 83, N83)
    assert v["kind"] == PW.KIND_RENAME and v["why"] == PW.RENAME, v
    assert v["d"] == "2478" and v["g"] == "9286" and v["mids"] == [4411, 4520], v
    assert v["proposed"] == "XADV 750CC GREY 2478"
    text = PW.card_text(v, SERV)
    assert "⚠️ Номер на байке не совпадает с зелёной книгой (9286)" in text, text
    assert "«XADV 750CC GREY 2478»" in text and "4411" in text and "4520" in text
    assert "https://t.me/c/2751134848/83/4411" in text


def test_live_82_same_everywhere_nothing():
    st = _st(82, ("5104", 900), ("5104", 901))
    v = _v(st, 82, N82)
    assert v["kind"] is None and v["why"] == PW.SAME, v


def test_live_1190_rename_with_warning():
    st = _st(1190, ("9315", 70), ("9315", 75))
    v = _v(st, 1190, N1190)
    assert v["kind"] == PW.KIND_RENAME and v["proposed"] == "XMAX 300CC NEW BROWN 9315", v
    assert "⚠️ Номер на байке не совпадает с зелёной книгой (8676)" in PW.card_text(v, SERV)


def test_bike_equals_book_says_so():
    # тема 62 зовётся (по событию переименования) старым номером 5849, а на байке уже новый 5662 = книга
    st = _st(62, ("5662", 10), ("5662", 11))
    v = _v(st, 62, "ADV 350CC BLACK 5849", src=PW.SRC_EVENT)
    text = PW.card_text(v, SERV)
    assert v["kind"] == PW.KIND_RENAME and "✅ Номер на байке совпадает с зелёной книгой (5662)" in text, text
    assert "не совпадает с зелёной книгой" not in text


def test_live_66_longer_plate_is_not_a_partial_read_and_renames_only_with_a_bridge_pair():
    """Ревью предлагало молчать, когда длина номера на байке не равна ни длине номера темы, ни книги. Живой случай
    66 (на байке 9011, в книге и имени 461) это правило заглушило бы. Неполное/слипшееся чтение ловится точнее:
    один номер — другой без одной цифры (286 ↔ 9286, 1461 ↔ 461), см. test_partial_merged_engine_are_silent.
    r3: 9011 — прежний номер ЭТОГО байка (страница владельца), но пары 9011 → 461 в карте моста нет: с именем
    «… 9011» записи ТО не нашли бы строку — заметка без кнопок. Пара появится в книге — карточка вернётся."""
    st = _st(66, ("9011", 1), ("9011", 2))
    v = _v(st, 66, "CB 300CC R 461")
    assert v["kind"] == PW.KIND_NOTE and v["why"] == PW.NOT_ROUTED and v["why"] != PW.PARTIAL, v
    doc = dict(BOOK, bridge_old_plates=dict(BOOK["bridge_old_plates"], **{"9011": "461"}))
    v = PW.verdict(st, 66, "CB 300CC R 461", PW.book_entry(doc, 66), NOW)
    assert v["kind"] == PW.KIND_RENAME and v["proposed"] == "CB 300CC R 9011", v
    assert S._plate_from_name(v["proposed"]) == "9011"


def test_single_reading_album_close_and_same_photo_are_few():
    assert _v(_st(83, ("2478", 1)), 83, N83)["why"] == PW.FEW
    album = _st(83, ("2478", 1, "alb"), ("2478", 2, "alb"), ("2478", 3, "alb"))
    assert _v(album, 83, N83)["why"] == PW.FEW
    old = _st(83, ("2478", 1, None, 15), ("2478", 2, None, 0))
    assert _v(old, 83, N83)["why"] == PW.FEW
    same_msg = PW.add_reading(_st(83, ("2478", 7)), 83, {"d": "2478"}, 7, None, NOW)   # повтор по «да»
    assert _v(same_msg, 83, N83)["why"] == PW.FEW
    # ревью r2 S5: две отправки через 3 секунды — одна съёмка, а не два свидетеля
    close = _st(83, ("2478", 1, None, 3 / DAY), ("2478", 2, None, 0))
    assert _v(close, 83, N83)["why"] == PW.FEW
    # тот же снимок, присланный повторно (пересылка) через сутки, — один свидетель
    fwd = _st(83, ("2478", 1, None, 1.0, "FU1"), ("2478", 2, None, 0, "FU1"))
    assert _v(fwd, 83, N83)["why"] == PW.FEW
    two = _st(83, ("2478", 1, None, 1.0, "FU1"), ("2478", 2, None, 0, "FU2"))
    assert _v(two, 83, N83)["kind"] == PW.KIND_RENAME
    # альбом + тот же снимок в другой отправке: всё один свидетель
    mixed = _st(83, ("2478", 1, "a", 1.0, "FU1"), ("2478", 2, "a", 1.0, "FU2"), ("2478", 3, None, 0, "FU2"))
    assert _v(mixed, 83, N83)["why"] == PW.FEW


def test_any_dissent_is_split():
    st = _st(83, ("2478", 1), ("2478", 2), ("2473", 3), ("2473", 4))
    assert _v(st, 83, N83)["why"] == PW.SPLIT
    # ревью r2 S5 (проба 4): перевес 2:1 — уже не «сошлись», а сомнение
    st = _st(83, ("2478", 1), ("2478", 2), ("2473", 3))
    v = _v(st, 83, N83)
    assert v["kind"] is None and v["why"] == PW.SPLIT and "2473" in v["detail"], v
    # несогласное чтение вышло из окна — согласие вернулось
    st = _st(83, ("2473", 3, None, 15), ("2478", 1, None, 1), ("2478", 2, None, 0))
    assert _v(st, 83, N83)["kind"] == PW.KIND_RENAME


def test_no_plate_in_topic_name_nothing():
    st = _st(83, ("2478", 1), ("2478", 2))
    assert _v(st, 83, "XADV 750 GREY", src=PW.SRC_EVENT)["why"] == PW.NO_TOPIC_PLATE


def test_neighbour_and_other_bike_numbers_are_silent():
    """Ревью r2 M1: 4248 (тема 222) и 4246 (тема 381) — близнецы; принятый за 4246 номер 4248 дал бы теме 222
    номер темы 381, и ТО из 222 ушли бы в строку 381."""
    others = PW.fleet_numbers(BOOK, {}, 222)
    assert others["4246"] == 381 and "4248" not in others
    v = _v(_st(222, ("4246", 1), ("4246", 2)), 222, "XMAX 300CC GREEN 4248", others=others)
    assert v["kind"] is None and v["why"] == PW.NEAR, v
    # номер другого байка, не близнец: снят чужой байк (тема 70 FORZA 8950) в теме 83
    o83 = PW.fleet_numbers(BOOK, {83: N83}, 83)
    v = _v(_st(83, ("8950", 1), ("8950", 2)), 83, N83, others=o83)
    assert v["kind"] is None and v["why"] == PW.OTHER_BIKE and "70" in v["detail"], v
    # номер из ИМЕНИ другой темы (книги у неё нет)
    o = PW.fleet_numbers(BOOK, {990001: "TEST 155CC 7777", 83: N83}, 83)
    assert _v(_st(83, ("7777", 1), ("7777", 2)), 83, N83, others=o)["why"] == PW.OTHER_BIKE
    # на одну цифру от КНИГИ (имя уже другое)
    v = _v(_st(83, ("9288", 1), ("9288", 2)), 83, "XADV 750CC GREY 2478", src=PW.SRC_PLATE, others=o83)
    assert v["why"] == PW.NEAR and "книги" in v["detail"], v


def test_partial_merged_engine_are_silent():
    # проба 2: первая цифра закрыта — «286» вместо 9286
    assert _v(_st(83, ("286", 1), ("286", 2)), 83, N83)["why"] == PW.PARTIAL
    # проба 3: цифра серии «1กว 461» слиплась с номером — «1461»
    assert _v(_st(66, ("1461", 1), ("1461", 2)), 66, "CB 300CC R 461")["why"] == PW.PARTIAL
    # средняя цифра потеряна
    assert _v(_st(83, ("926", 1), ("926", 2)), 83, N83)["why"] == PW.PARTIAL
    # проба 7: «300» — объём, не номер (и мост из имени его не возьмёт)
    v = _v(_st(1190, ("300", 1), ("300", 2)), 1190, N1190)
    assert v["why"] == PW.ENGINE and S._plate_from_name(PW.propose(N1190, "300")) is None, v


def test_untrusted_names_are_silent():
    """Ревью r2 M3: имя с прежней меткой 'forum_created' или из reply может быть дрейфом (82 — «…3902» при
    названии «XADV 750CC BLACK 5104»). Такому имени сверка не верит: ни карточки, ни «совпадает»."""
    drift = "XADV 750 BLACK 3902"
    for src in ("forum_created", PW.SRC_REPLY, None):
        v = _v(_st(82, ("5104", 1), ("5104", 2)), 82, drift, src=src)
        assert v["kind"] is None and v["why"] == PW.UNTRUSTED and "5104" in v["detail"], (src, v)
        v = _v(_st(82, ("3902", 1), ("3902", 2)), 82, drift, src=src)     # сценарий B: старая табличка
        assert v["kind"] is None and v["why"] == PW.UNTRUSTED, (src, v)
    # имя книги — верим при любой метке; событие темы после правки — верим и без книги
    assert _v(_st(82, ("5104", 1), ("5104", 2)), 82, N82, src="forum_created")["why"] == PW.SAME
    assert _v(_st(82, ("3902", 1), ("3902", 2)), 82, drift, src=PW.SRC_EVENT)["why"] == PW.WARN
    assert PW.name_trusted("xadv 750cc  black 5104", None, _book(82))


def test_manual_binding_is_silent():
    v = _v(_st(83, ("2478", 1), ("2478", 2)), 83, N83, src=PW.SRC_MANUAL)
    assert v["kind"] is None and v["why"] == PW.MANUAL, v


def test_pending_card_and_ttl():
    st = _st(83, ("2478", 1), ("2478", 2))
    v = _v(st, 83, N83)
    st, n = PW.next_seq(st)
    st = PW.with_card(st, v, n, NOW, chat_id=SERV)
    assert PW.find_card(st, n)[1]["proposed"] == "XADV 750CC GREY 2478"
    st = PW.add_reading(st, 83, {"d": "2478"}, 3, None, NOW + 60)
    assert _v(st, 83, N83, now=NOW + 60)["why"] == PW.PENDING
    later = NOW + PW.CARD_TTL_S + 60
    st = PW.add_reading(PW.add_reading(st, 83, {"d": "2478"}, 8, None, later - GAP), 83, {"d": "2478"}, 9, None, later)
    v = _v(st, 83, N83, now=later)
    assert v["kind"] == PW.KIND_RENAME and v.get("drop_card"), v       # старая уходит, приходит свежая


def test_card_dropped_and_refused_when_plate_fixed():
    """Ревью r2 S2 (проба 5): карточка предлагала 2478; через 30 суток на байке верная 9286, чтения дают SAME —
    карточка снимается сверкой и не исполняется нажатием."""
    st = _st(83, ("2478", 1), ("2478", 2))
    v = _v(st, 83, N83)
    st, n = PW.next_seq(st)
    st = PW.with_card(st, v, n, NOW)
    card = PW.find_card(st, n)[1]
    assert PW.card_valid(st, card, N83, _book(83), NOW + 60) == (True, "")
    later = NOW + 30 * DAY
    st = _st(83, ("9286", 3), ("9286", 4), base=later, st=st)
    v2 = _v(st, 83, N83, now=later)
    assert v2["why"] == PW.SAME and v2.get("drop_card"), v2
    ok, why = PW.card_valid(st, card, N83, _book(83), later)
    assert not ok and why == PW.CARD_OLD, why
    ok, why = PW.card_valid(st, dict(card, ts=later), N83, _book(83), later)      # даже свежая — чтения не те
    assert not ok and PW.SAME in why, why
    ok, why = PW.card_valid(st, card, "XADV 750CC GREY 7777", _book(83), NOW + 60)
    assert not ok and "7777" in why, why


def test_declined_holds_until_name_or_digits_change():
    st = _st(83, ("2478", 1), ("2478", 2))
    v = _v(st, 83, N83)
    st, n = PW.next_seq(st)
    st = PW.with_card(st, v, n, NOW)
    st = PW.with_declined(st, PW.find_card(st, n)[1], NOW)
    assert PW.find_card(st, n) == (None, None)
    assert _v(st, 83, N83)["why"] == PW.DECLINED
    assert _v(st, 83, "XADV 750CC GREY2 9286", src=PW.SRC_EVENT)["kind"] == PW.KIND_RENAME


def test_warn_only_once_per_seven_days():
    # после переименования 83 зовётся по табличке 2478 — книга по-прежнему 9286
    st = _st(83, ("2478", 1), ("2478", 2))
    v = _v(st, 83, "XADV 750CC GREY 2478", src=PW.SRC_PLATE)
    assert v["kind"] == PW.KIND_WARN and v["why"] == PW.WARN, v
    text = PW.card_text(v, SERV)
    assert text.startswith("⚠️ Номер на байке не совпадает с зелёной книгой (9286)"), text
    assert "Предлагаю" not in text
    st = PW.with_warned(st, 83, NOW)
    assert _v(st, 83, "XADV 750CC GREY 2478", now=NOW + 6 * DAY, src=PW.SRC_PLATE)["why"] == PW.WARN_RECENT
    st = _st(83, ("2478", 5), ("2478", 6), base=NOW + 8 * DAY, st=st)
    assert _v(st, 83, "XADV 750CC GREY 2478", now=NOW + 8 * DAY, src=PW.SRC_PLATE)["kind"] == PW.KIND_WARN


def test_off_and_broken_memory():
    st = _st(83, ("2478", 1), ("2478", 2))
    assert PW.verdict(st, 83, N83, _book(83), NOW, on=False)["why"] == PW.OFF
    for bad in (None, "мусор", {"readings": "x", "cards": [1]}, {"readings": {"83": [None, {"d": "abc"}]}}):
        assert _v(bad, 83, N83)["why"] == PW.FEW, bad


def test_card_numbers_never_restart():
    """Ревью r2 S3 (проба 6): память потеряна → счётчик с нуля выдавал новой карточке номер старой."""
    _st0, n1 = PW.next_seq(PW.clean("garbage"), floor=int(NOW * 1000))
    assert n1 == int(NOW * 1000)
    st, n2 = PW.next_seq(_st0, floor=int(NOW * 1000))          # та же миллисекунда — всё равно новый
    assert n2 == n1 + 1
    _st1, n3 = PW.next_seq(PW.clean(None), floor=int((NOW + 1) * 1000))
    assert n3 > n2
    assert len(f"svc:{S._PLATE_BTN_KEEP}:{n3}".encode()) <= 64          # предел callback_data Telegram


def test_card_words():
    v = _v(_st(83, ("2478", 4411), ("2478", 4520)), 83, N83)
    text = PW.card_text(v, SERV)
    assert text.count("Зелёная книга") == 1, text
    assert "служебная строка Telegram" in text and "v96" in text and "2478" in text, text     # ревью r2 S10
    # r3: книги по теме нет — номер ничем не привязан к байку, переименовать не предлагаем: заметка без кнопок
    nb = PW.verdict(_st(990005, ("5678", 1), ("5678", 2)), 990005, "TEST 155CC 1234", None, NOW, src=PW.SRC_EVENT)
    tnb = PW.card_text(nb, SERV)
    assert nb["kind"] == PW.KIND_NOTE and tnb.count("записи нет") >= 1 and "нечем" in tnb, tnb
    assert "Предлагаю" not in tnb and "Переименовать тему —" not in tnb, tnb
    assert "Сверить с зелёной книгой нечем — записи по теме нет." not in tnb
    assert PW._seen_line({"d": "2478", "mids": []}, SERV) == "На байке: 2478"


# --- ревью r3 -------------------------------------------------------------------------------
LIVE_OLD = {"2478": 83, "9315": 1190, "7943": 455, "9011": 66, "5849": 62, "798": 64, "3902": 82, "8855": 2582,
            "5580": 69}


def test_r3_old_plates_of_other_bikes_are_other_bike_numbers():
    """correctness-oldplate-not-other-bike: прежний номер чужого байка (2478 на байке темы 83) — тот самый, что прочтут
    со снимка не в той теме, а мост по нему пишет в строку ТОГО байка. Он обязан быть «номером другого байка»."""
    for d, tid in LIVE_OLD.items():
        others = PW.fleet_numbers(BOOK, {}, 70)
        assert others.get(d) == tid, (d, tid, others.get(d))
        assert d not in PW.fleet_numbers(BOOK, {}, tid), (d, tid)            # свой прежний номер — не чужой
    names = {b["topic_id"]: b["name"] for b in BOOK["bikes"]}               # все темы по книге (как после 24.10)
    o70 = PW.fleet_numbers(BOOK, names, 70)
    v = _v(_st(70, ("2478", 1), ("2478", 2)), 70, "FORZA 300CC WHITE 8950", others=o70)
    assert v["kind"] is None and v["why"] == PW.OTHER_BIKE and "83" in v["detail"], v
    # карта моста: каждая пара — прежний номер именно той строки книги, в которую мост её сводит
    for old, new in PW.bridge_map(BOOK).items():
        tid = PW.book_topic(BOOK, new)
        assert tid is not None and old in _book(tid)["old"] and old in _book(tid)["routed"], (old, new, tid)


def test_r3_other_topic_numbers_by_the_bridge_rule():
    """safety-other-bike-name: номер темы, стоящий не последним словом («ADV350 6699 black new», тема 4615), мост
    находит (`_plate_from_name`), а прежняя сверка «другого байка» брала только последнее слово и его не видела."""
    live = "ADV350 6699 black new"
    assert PW.name_numbers(live) == ["6699"] and PW.topic_plate(live) is None
    assert PW.name_numbers("MT-03 300СС BLUE 5068") == ["5068"]              # «300» — объём (и кириллическое СС)
    assert PW.name_numbers("XMAX 300CC NEW RED GLOSS 2 PHUKET 4729") == ["4729"]
    assert PW.name_numbers(None) == [] and PW.name_numbers("NO NUMBER 12") == []
    # зеркало моста: номер, который мост берёт из имени, всегда среди номеров имени
    for name in [b["name"] for b in BOOK["bikes"]] + [live, "ADV 160 6470", "XSR GREY 7943", "XADV 750 BLACK 3902"]:
        assert S._plate_from_name(name) in PW.name_numbers(name), name
    names = {62: "ADV 350CC BLACK 5662", 4615: live}
    o62 = PW.fleet_numbers(BOOK, names, 62)
    assert o62.get("6699") == 4615, o62
    v = _v(_st(62, ("6699", 1), ("6699", 2)), 62, "ADV 350CC BLACK 5662", others=o62)
    assert v["kind"] is None and v["why"] == PW.OTHER_BIKE, v


def test_r3_rename_only_to_the_book_or_a_bridge_paired_old_plate():
    """safety-unknown-plate-rename: кнопка — только в номер книги этого байка или его прежний номер из пары карты
    моста. Иное (ошибка чтения 1↔7, закрытая скобкой цифра, номер без пары, без книги) — заметка без кнопок."""
    assert _book(83)["old"] == ["2478"] and _book(83)["routed"] == ["2478"]
    assert _book(66)["old"] == ["9011"] and _book(66)["routed"] == []
    assert _book(69)["old"] == [] and _book(69)["old_unproven"] == ["5580"] and _book(69)["routed"] == []
    # 66: на байке 9011, стёртая «1» прочитана как «7» в двух заходах
    v = _v(_st(66, ("9017", 1), ("9017", 2)), 66, "CB 300CC R 461")
    assert v["kind"] == PW.KIND_NOTE and v["why"] == PW.NOT_BOOK and v["proposed"] is None, v
    text = PW.card_text(v, SERV)
    assert text.startswith("🔢 На байке читается 9017") and "Предлагаю" not in text and "Кнопок нет" in text, text
    # 83: первая цифра под скобкой — «478» (не часть 9286, не на цифру от него)
    v = _v(_st(83, ("478", 1), ("478", 2)), 83, N83)
    assert v["kind"] == PW.KIND_NOTE and v["why"] == PW.NOT_BOOK, v
    # 69: прежний номер без доказательства — тоже не переименование
    v = _v(_st(69, ("5580", 1), ("5580", 2)), 69, "CLICK 125CC 5762")
    assert v["kind"] == PW.KIND_NOTE and v["why"] == PW.NOT_BOOK and "без доказательства" in v["detail"], v
    # заметка — тем же счётчиком раз в 7 суток, что и предупреждение
    st = PW.with_warned(_st(66, ("9017", 1), ("9017", 2)), 66, NOW - DAY)
    v = _v(st, 66, "CB 300CC R 461")
    assert v["kind"] is None and v["why"] == PW.WARN_RECENT and PW.NOT_BOOK in v["detail"], v
    # законные переименования остаются: прежний номер с парой моста и номер книги
    assert _v(_st(83, ("2478", 1), ("2478", 2)), 83, N83)["kind"] == PW.KIND_RENAME
    assert _v(_st(1190, ("9315", 1), ("9315", 2)), 1190, N1190)["kind"] == PW.KIND_RENAME
    v = _v(_st(83, ("9286", 1), ("9286", 2)), 83, "XADV 750CC GREY 2478", src=PW.SRC_PLATE)
    assert v["kind"] == PW.KIND_RENAME and v["proposed"] == N83, v
    # висящую карточку, которую нынешние чтения уже не повторили бы, нажатие не исполняет
    card = {"topic": 66, "name": "CB 300CC R 461", "d": "9017", "proposed": "CB 300CC R 9017", "ts": NOW}
    ok, why = PW.card_valid(_st(66, ("9017", 1), ("9017", 2)), card, "CB 300CC R 461", _book(66), NOW + 60)
    assert not ok and PW.NOT_BOOK in why, why


def test_r3_card_claims_the_bridge_route_only_when_the_map_has_it():
    v = _v(_st(83, ("2478", 4411), ("2478", 4520)), 83, N83)
    text = PW.card_text(v, SERV)
    assert "карта старых номеров моста (v96) переводит 2478 в строку книги 9286" in text, text
    fake = dict(v, d="2471", proposed="XADV 750CC GREY 2471")               # пары нет: слова честные
    assert "пары 2471 → 9286 в карте старых номеров моста (v96) нет" in PW.card_text(fake, SERV)


def test_r3_engine_size_as_the_last_word_is_no_topic_plate():
    """safety-engine-size-as-topic-plate: «NMAX 155» — имя без номера (мост так и считает), а не номер «155»."""
    for name in ("NMAX 155", "XMAX 300", "ADV 350"):
        assert PW.topic_plate(name) is None and S._plate_from_name(name) is None, name
        assert PW.propose(name, "4321") is None, name
        v = PW.verdict(_st(990155, ("4321", 1), ("4321", 2)), 990155, name, None, NOW, src=PW.SRC_EVENT)
        assert v["kind"] is None and v["why"] == PW.NO_TOPIC_PLATE, (name, v)


def test_r3_dissent_inside_the_window_is_never_truncated():
    """safety-dissent-truncated: одно верное 2478 двое суток назад, затем альбом из 12 ошибочных 2473 (один свидетель)
    и ещё одно 2473 — прежняя обрезка до 12 теряла несогласное чтение и давала RENAME «…2473»."""
    st = _st(83, ("2478", 1, None, 2.0))
    for i in range(12):
        st = PW.add_reading(st, 83, {"d": "2473"}, 100 + i, "alb12", NOW - DAY)
    st = PW.add_reading(st, 83, {"d": "2473"}, 200, None, NOW)
    assert len(PW.clean(st)["readings"]["83"]) == 14
    v = _v(st, 83, N83)
    assert v["kind"] is None and v["why"] == PW.SPLIT and "2478" in v["detail"], v
    # предохранитель диска: сверх KEEP_PER_TOPIC тема молчит, пока обрезанное не выйдет из окна
    st = PW.clean(None)
    for i in range(PW.KEEP_PER_TOPIC + 1):
        st = PW.add_reading(st, 83, {"d": "2478"}, 1000 + i, None, NOW - 3 * DAY + i * 60)
    assert len(st["readings"]["83"]) == PW.KEEP_PER_TOPIC and st["trunc"]["83"] == NOW - 3 * DAY
    v = _v(st, 83, N83)
    assert v["kind"] is None and v["why"] == PW.OVERFLOW, v
    later = NOW + 15 * DAY
    st = _st(83, ("2478", 5001), ("2478", 5002), base=later, st=st)
    assert _v(st, 83, N83, now=later)["kind"] == PW.KIND_RENAME


def test_r3_card_without_a_message_does_not_hold_the_topic():
    """correctness-zombie-card (чистая часть): карточка без сообщения — идёт отправка, пока моложе CARD_SEND_S;
    старше — отправка оборвалась, карточка снимается, а не держит тему 7 суток."""
    st = _st(83, ("2478", 1), ("2478", 2))
    v = _v(st, 83, N83)
    st, n = PW.next_seq(st)
    st = PW.with_card(st, v, n, NOW)                                         # msg None: отправка не дописала
    assert _v(st, 83, N83, now=NOW + 60)["why"] == PW.PENDING
    v2 = _v(st, 83, N83, now=NOW + PW.CARD_SEND_S + 1)
    assert v2["kind"] == PW.KIND_RENAME and v2.get("drop_card") and v2.get("card_lost"), v2
    st = PW.with_card_msg(st, 83, n, 7001, notify.HQ_CHAT_ID)                # доехала — держит тему
    assert _v(st, 83, N83, now=NOW + DAY)["why"] == PW.PENDING


# ============================================================================================
#  (2) ПРОМПТ снимка
# ============================================================================================
def test_prompt_asks_plate_of_the_photographed_bike_only():
    p = S.VISION_BIKE_SYSTEM
    assert "plate:" in p and "legible" in p and "digits" in p, p
    assert "на фоне" in p and "НЕ угадывай" in p
    assert "plate:" in S.VISION_BIKE_SYSTEM_POS
    # промпт положения байка по-прежнему дописывает «разобран» сразу перед notes
    extra = S.VISION_BIKE_SYSTEM_POS.replace(S.VISION_BIKE_SYSTEM.split("  notes:")[0], "", 1)
    assert extra.startswith("  disassembled:"), extra[:80]


def test_prompt_without_plate_when_knob_off():
    """Ревью r2 S8: выключенная ручка обязана откатывать и само поле промпта."""
    for name in ("VISION_BIKE_SYSTEM_NOPLATE", "VISION_BIKE_SYSTEM_POS_NOPLATE"):
        p = getattr(S, name)
        assert "plate" not in p and "legible" not in p, name
        assert "  dirt:" in p and "  kind:" in p and "  notes:" in p, name
    assert S.VISION_BIKE_SYSTEM_NOPLATE == S.VISION_BIKE_SYSTEM.replace(S._VISION_PLATE_BLOCK, "")
    assert "disassembled" in S.VISION_BIKE_SYSTEM_POS_NOPLATE
    assert S._VISION_PLATE_BLOCK.startswith("  plate:") and S._VISION_PLATE_BLOCK.endswith("цифры\n")
    prev = os.environ.get("PLATE_WATCH")
    try:
        for off in ("0", "false", "False", "off", "OFF", "нет", "no", ""):
            os.environ["PLATE_WATCH"] = off
            assert S._plate_watch_on() is False, repr(off)
            assert S._vision_bike_prompt(False) == (S.VISION_BIKE_SYSTEM_NOPLATE, 400)
            assert S._vision_bike_prompt(True) == (S.VISION_BIKE_SYSTEM_POS_NOPLATE, 400)
        for on in ("1", "true", "yes"):
            os.environ["PLATE_WATCH"] = on
            assert S._plate_watch_on() is True, repr(on)
            assert S._vision_bike_prompt(False) == (S.VISION_BIKE_SYSTEM, 500)
            assert S._vision_bike_prompt(True) == (S.VISION_BIKE_SYSTEM_POS, 500)
    finally:
        os.environ["PLATE_WATCH"] = prev if prev is not None else "1"


# ============================================================================================
#  Заглушки мира для живого `splinter.handle` и кнопок
# ============================================================================================
class _Bot:
    username = "tb_plate_test_bot"

    def __init__(self, rename_error=None):
        self.sent, self.renamed, self.rename_error = [], [], rename_error

    async def send_message(self, **kw):
        self.sent.append(kw)
        return types.SimpleNamespace(message_id=100 + len(self.sent))

    async def edit_forum_topic(self, **kw):
        self.renamed.append(kw)
        if self.rename_error:
            raise Exception(self.rename_error)
        return True

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self, rename_error=None):
        self.bot = _Bot(rename_error)


class _User:
    def __init__(self, username="testmech", uid=99005):
        self.id, self.username, self.is_bot, self.first_name = uid, username, False, "T"


class _Msg:
    def __init__(self, topic, mid, photo=True, text=None, group=None, reply_name=None, user=None, fu=None):
        self.chat_id = SERV
        self.text = text
        self.caption = None
        self.photo = ([types.SimpleNamespace(file_unique_id=fu)] if fu else [object()]) if photo else []
        self.message_id = mid
        self.message_thread_id = topic
        self.date = None
        self.from_user = user or _User()
        self.media_group_id = group
        self.forum_topic_created = None
        self.forum_topic_edited = None
        self.reply_to_message = (types.SimpleNamespace(forum_topic_created=types.SimpleNamespace(name=reply_name))
                                 if reply_name else None)


class _World:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def _any(*a, **kw):
            self.calls.append((name, kw))
            return {"ok": True, "items": [], "saved": True}
        return _any

    def find_bike(self, q):
        return {}

    def service_pending_get(self, *a, **kw):
        return {"ok": False, "error": "not_found"}


class _Claude:
    def __init__(self, vision):
        self.vision_q, self.systems, self.max_tokens = list(vision), [], []

    def quick(self, *a, **kw):
        return ""

    def vision(self, system, *a, **kw):
        self.systems.append(system)
        self.max_tokens.append(kw.get("max_tokens"))
        return json.dumps(self.vision_q.pop(0) if self.vision_q else {})


class _Mem:
    """memory.db-заглушка: та же форма вызовов, что у `memory.Memory` (и тот же замок 'manual'), без файла базы."""

    def __init__(self, names=None, sources=None):
        self.names, self.calls = dict(names or {}), []
        self.sources = dict(sources or {})

    def set_topic_bike(self, chat_id, topic_id, name, source="auto"):
        self.calls.append((chat_id, topic_id, name, source))
        if source != "manual" and self.sources.get((chat_id, topic_id)) == "manual":
            return
        self.names[(chat_id, topic_id)] = name
        self.sources[(chat_id, topic_id)] = source

    def get_topic_bike(self, chat_id, topic_id):
        return self.names.get((chat_id, topic_id), "")

    def topic_bike_source(self, chat_id, topic_id):
        return self.sources.get((chat_id, topic_id))

    def all_topic_bikes(self):
        return dict(self.names)


CARDS, FEEDS = [], []
SEND_DELAY = [0.0]
CLOCK = [NOW]


def _fake_send_card(text, buttons=None):
    if SEND_DELAY[0]:
        time.sleep(SEND_DELAY[0])
    CARDS.append({"text": text, "buttons": buttons, "mid": 7000 + len(CARDS) + 1})
    return CARDS[-1]["mid"], notify.HQ_CHAT_ID


def _fake_send_feed(text):
    FEEDS.append(text)
    return True


notify.send_card = _fake_send_card          # сеть не дёргаем ни при каких условиях
notify.send_feed = _fake_send_feed
S._plate_now = lambda: CLOCK[0]             # часы ветки — свои: свидетели разнесены часами
_SEQ = [0]


def _fresh(names=None, mem=None):
    """Чистая память номеров, подсказок и тем; memory.db — заглушка либо нет вовсе."""
    _SEQ[0] += 1
    os.environ["PLATE_WATCH_STATE"] = _tmpf(f"plate{_SEQ[0]}")
    os.environ["HINT_DEDUP_STATE"] = _tmpf(f"hint{_SEQ[0]}")
    S._HINT_SEEN = None
    S._PLATE_STATE = None
    S._PLATE_BROKEN = None
    S._PLATE_TASKS.clear()
    S._TOPIC_NAMES.clear()
    S._TOPIC_NAME_SRC.clear()
    S._TOPIC_BIKE_OVERRIDE.clear()
    S._TOPIC_NAMES.update({(SERV, t): n for t, n in (names or {}).items()})
    S.set_memory(mem)
    CARDS.clear()
    FEEDS.clear()
    SEND_DELAY[0] = 0.0
    CLOCK[0] = NOW


def _photo(topic, mid, vision, ctx=None, group=None, reply_name=None, knob="1", fu=None, step=GAP):
    """Снимок в тему через живой `S.handle`; фоновая сверка дожидается; часы уходят вперёд на `step`."""
    prev = os.environ.get("PLATE_WATCH")
    os.environ["PLATE_WATCH"] = knob
    ctx = ctx or _Ctx()
    claude = _Claude([vision])
    saved = S._download_photo

    async def _dl(pm):
        return b"\xff\xd8 test"

    async def _go():
        await S.handle(types.SimpleNamespace(message=_Msg(topic, mid, group=group, reply_name=reply_name, fu=fu)),
                       ctx, _World(), claude)
        await S._plate_drain()
    S._download_photo = _dl
    try:
        asyncio.run(_go())
    finally:
        S._download_photo = saved
        os.environ["PLATE_WATCH"] = prev if prev is not None else "1"
        CLOCK[0] += step
    ctx.claude = claude
    return ctx


class _Q:
    def __init__(self, data, user, mid, text="карточка"):
        self.data, self.from_user = data, _User(*user)
        self.message = types.SimpleNamespace(chat_id=notify.HQ_CHAT_ID, message_thread_id=1160, message_id=mid,
                                             text=text, chat=types.SimpleNamespace(id=notify.HQ_CHAT_ID))
        self.answers, self.edits = [], []

    async def answer(self, txt=None, **kw):
        self.answers.append((txt, kw))

    async def edit_message_text(self, text=None, **kw):
        self.edits.append(text)

    async def edit_message_reply_markup(self, **kw):
        self.edits.append(("markup", kw))


def _mid_of(data):
    for c in CARDS:
        if any(b[1] == data for row in (c["buttons"] or []) for b in row):
            return c["mid"]
    return 1


def _press(data, user, ctx=None, mid=None):
    ctx = ctx or _Ctx()
    q = _Q(data, user, mid if mid is not None else _mid_of(data))
    asyncio.run(S.handle_service_button(types.SimpleNamespace(callback_query=q), ctx, _World()))
    return q, ctx


def _plate_texts(ctx):
    """Сообщения в тему байка, похожие на эту ветку: их быть не должно НИ ОДНОГО."""
    marks = ("Номер на байке", "🔢", "зелёной книг", "Переименовать", "svc:pl")
    return [kw for kw in ctx.bot.sent if any(m in str(kw) for m in marks)]


def _two(topic, d, mid=4411, **kw):
    _photo(topic, mid, _plate(d), **kw)
    _photo(topic, mid + 1, _plate(d), **kw)


# ============================================================================================
#  (3) ЖИВОЙ `splinter.handle` + кнопки
# ============================================================================================
def test_live_83_card_to_owner_only_and_nothing_into_topic():
    _fresh({83: N83})
    c1 = _photo(83, 4411, _plate("2478", series="2กจ"))
    assert CARDS == [], "одно чтение — ничего"
    c2 = _photo(83, 4520, _plate("2478"))
    assert len(CARDS) == 1, CARDS
    card = CARDS[0]
    assert "⚠️ Номер на байке не совпадает с зелёной книгой (9286)" in card["text"], card["text"]
    assert "«XADV 750CC GREY 2478»" in card["text"] and "4411" in card["text"] and "4520" in card["text"]
    labels = [b[0] for row in card["buttons"] for b in row]
    datas = [b[1] for row in card["buttons"] for b in row]
    assert labels == ["Переименовать тему", "Оставить"], labels
    assert datas[0].startswith("svc:plren:") and datas[1].startswith("svc:plkeep:"), datas
    for c in (c1, c2):
        assert _plate_texts(c) == [], _plate_texts(c)
        assert not c.bot.renamed
        assert c.claude.systems == [S.VISION_BIKE_SYSTEM_POS] and c.claude.max_tokens == [500]
    pend = PW.clean(S._PLATE_STATE)["cards"]["83"]
    assert pend["msg"] == card["mid"] and pend["msg_chat"] == notify.HQ_CHAT_ID, pend
    # третье чтение того же номера — висящая карточка, второй нет; ни одной заметки в ленту
    _photo(83, 4600, _plate("2478"))
    assert len(CARDS) == 1 and FEEDS == [], (CARDS, FEEDS)


def test_feature_hands_never_write_into_the_topic():
    """Код-уровень: руки ветки (`splinter._plate_*`) не зовут ни одной отправки в группу. Наружу —
    только карточка владельцу (`notify.send_card`), заметка в ленту (`notify.send_feed`) и
    переименование темы по его нажатию."""
    tree = ast.parse(open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read())
    hands = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("_plate")]
    assert len(hands) >= 5, [h.name for h in hands]
    outward = {"send_message", "_send", "_send_retry", "_hint_send", "reply_text", "send_photo",
               "_send_bilingual", "copy_message", "forward_message", "pin_chat_message", "send_inbox"}
    for h in hands:
        used = {n.attr for n in ast.walk(h) if isinstance(n, ast.Attribute)} | \
               {n.id for n in ast.walk(h) if isinstance(n, ast.Name)}
        assert not used & outward, (h.name, used & outward)


def test_rename_survives_restart_owner_press_renames_topic():
    mem = _Mem({(SERV, 83): N83}, {(SERV, 83): "forum_created"})
    _fresh({83: N83}, mem=mem)
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    S._PLATE_STATE = None                     # перезапуск: память номеров — только с диска
    q, ctx = _press(ren, OWNER)
    assert ctx.bot.renamed == [{"chat_id": SERV, "message_thread_id": 83, "name": "XADV 750CC GREY 2478"}], \
        (ctx.bot.renamed, q.answers)
    assert S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 2478"
    assert mem.calls[-1] == (SERV, 83, "XADV 750CC GREY 2478", PW.SRC_PLATE), mem.calls
    assert S.bike_from_topic(SERV, 83) == "XADV 750CC GREY 2478"
    assert any("✅ Переименовано" in str(e) and "бот зовёт байк так же" in str(e) for e in q.edits), q.edits
    assert not ctx.bot.sent, "в тему байка ничего"
    # Лист1 зовёт байк по книге (9286) — тема для вопроса сотрудникам находится по номеру (ревью r2 S10)
    assert S._bike_topic_id(SERV, N83) == 83
    # повтор нажатия — карточки уже нет
    q2, ctx2 = _press(ren, OWNER)
    assert not ctx2.bot.renamed and q2.answers and q2.answers[0][1].get("show_alert"), q2.answers
    # теперь тема = табличка 2478, книга 9286: предупреждение не раньше 7 суток (карточка его уже несла)
    _photo(83, 4700, _plate("2478"))
    assert len(CARDS) == 1 and FEEDS == [], (CARDS, FEEDS)


def test_non_owner_press_refused():
    _fresh({83: N83})
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    for who in (PYM, ("testmech", 99005)):
        q, ctx = _press(ren, who)
        assert not ctx.bot.renamed, who
        assert q.answers and q.answers[0][1].get("show_alert") and "владел" in q.answers[0][0], q.answers
        assert not q.edits, q.edits
    assert S._TOPIC_NAMES[(SERV, 83)] == N83
    q, ctx = _press(ren, OWNER)                # карточка жива и после чужих нажатий
    assert ctx.bot.renamed, ("владелец переименовал", q.answers)


def test_press_on_another_message_refused():
    """Ревью r2 S3: номер в кнопке — не адрес; кнопка с тем же номером на ДРУГОМ сообщении не исполняется."""
    _fresh({83: N83})
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    q, ctx = _press(ren, OWNER, mid=CARDS[0]["mid"] + 50)
    assert not ctx.bot.renamed and q.answers[0][1].get("show_alert") and "не от этой карточки" in q.answers[0][0]
    assert PW.find_card(S._PLATE_STATE, int(ren.rsplit(":", 1)[1]))[1] is not None     # карточка жива
    q, ctx = _press(ren, OWNER)
    assert ctx.bot.renamed


def test_keep_press_silences_this_digits_for_this_name():
    _fresh({83: N83})
    _two(83, "2478")
    keep = CARDS[0]["buttons"][0][1][1]
    q, ctx = _press(keep, OWNER)
    assert not ctx.bot.renamed and any("Оставлено" in str(e) for e in q.edits), q.edits
    assert S._TOPIC_NAMES[(SERV, 83)] == N83
    _two(83, "2478", mid=4800)
    assert len(CARDS) == 1, CARDS


def test_rename_refused_when_topic_renamed_meanwhile():
    _fresh({83: N83})
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    S._TOPIC_NAMES[(SERV, 83)] = "XADV 750CC GREY 7777"     # кто-то переименовал руками
    q, ctx = _press(ren, OWNER)
    assert not ctx.bot.renamed and q.answers[0][1].get("show_alert"), q.answers
    assert S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 7777"


def test_old_card_refused_after_plate_fixed():
    """Ревью r2 S2: карточка предлагала 2478; через 30 суток на байке верная 9286 — сверка снимает карточку,
    а нажатие не переименовывает тему в 2478."""
    _fresh({83: N83})
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    CLOCK[0] += 30 * DAY
    _two(83, "9286", mid=5000)
    assert PW.clean(S._PLATE_STATE)["cards"] == {}, S._PLATE_STATE
    q, ctx = _press(ren, OWNER)
    assert not ctx.bot.renamed and q.answers[0][1].get("show_alert"), q.answers
    assert S._TOPIC_NAMES[(SERV, 83)] == N83 and len(CARDS) == 1


def test_card_older_than_ttl_refused_at_press():
    _fresh({83: N83})
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    CLOCK[0] += PW.CARD_TTL_S + 3600          # сверок между не было — карточка в памяти, но старая
    q, ctx = _press(ren, OWNER)
    assert not ctx.bot.renamed and PW.CARD_OLD in q.answers[0][0], q.answers
    assert any("Не переименовал" in str(e) for e in q.edits), q.edits


def test_live_82_nothing():
    _fresh({82: N82})
    _two(82, "5104", mid=900)
    assert CARDS == [] and FEEDS == []


def test_live_1190_card_with_warning():
    _fresh({1190: N1190})
    _two(1190, "9315", mid=70)
    assert len(CARDS) == 1 and "⚠️ Номер на байке не совпадает с зелёной книгой (8676)" in CARDS[0]["text"], CARDS
    assert "«XMAX 300CC NEW BROWN 9315»" in CARDS[0]["text"]


def test_live_neighbour_misread_no_card():
    """Ревью r2 M1 живьём: 4248 (тема 222), дважды прочитанный как 4246 (номер темы 381)."""
    names = {222: "XMAX 300CC GREEN 4248", 381: "XMAX 300CC GREY 4246"}
    _fresh(names)
    _two(222, "4246", mid=300)
    assert CARDS == [] and FEEDS == []
    _fresh(names)
    _two(222, "8950", mid=310)                # снят чужой байк — FORZA темы 70
    assert CARDS == [] and FEEDS == []
    _fresh(names)
    _two(222, "6157", mid=320)                # номер, которого в парке нет: r3 — заметка без кнопок, не карточка
    assert CARDS == [] and len(FEEDS) == 1 and "6157" in FEEDS[0] and "Предлагаю" not in FEEDS[0], (CARDS, FEEDS)


def test_background_bike_album_and_same_photo_are_nothing():
    _fresh({83: N83})
    _photo(83, 4411, _plate("5104", legible=False))          # чужой байк на фоне
    _photo(83, 4412, _plate("5104", legible=False))
    assert CARDS == []
    _photo(83, 4413, _plate("2478"), group="alb1")           # альбом — одна отправка
    _photo(83, 4414, _plate("2478"), group="alb1")
    assert CARDS == []
    _fresh({83: N83})
    _photo(83, 4415, _plate("2478"), fu="AgADsame")          # тот же снимок дважды — один свидетель
    _photo(83, 4416, _plate("2478"), fu="AgADsame")
    assert CARDS == []
    _fresh({83: N83})
    _photo(83, 4417, _plate("2478"), step=3)                 # две отправки через 3 секунды
    _photo(83, 4418, _plate("2478"))
    assert CARDS == []


def test_kill_switch_records_nothing_and_drops_the_prompt_field():
    for knob in ("0", "false"):
        _fresh({83: N83})
        c1 = _photo(83, 4411, _plate("2478"), knob=knob)
        _photo(83, 4520, _plate("2478"), knob=knob)
        assert CARDS == [] and PW.clean(S._PLATE_STATE)["readings"] == {}, knob
        assert c1.claude.systems == [S.VISION_BIKE_SYSTEM_POS_NOPLATE] and c1.claude.max_tokens == [400], knob
        _photo(83, 4600, _plate("2478"))                     # включили — прошлые не считались
        assert CARDS == []


def test_concurrent_ticks_send_one_card():
    """Ревью r2 S1 (проба 9): две сверки одной темы одновременно — одна карточка, и она же висит."""
    _fresh({83: N83})
    S._plate_keep(_st(83, ("2478", 1), ("2478", 2), base=CLOCK[0]))
    SEND_DELAY[0] = 0.3

    async def two():
        await asyncio.gather(S._plate_tick(SERV, 83), S._plate_tick(SERV, 83))
    asyncio.run(two())
    assert len(CARDS) == 1, CARDS
    n = int(CARDS[0]["buttons"][0][0][1].rsplit(":", 1)[1])
    assert PW.clean(S._PLATE_STATE)["cards"]["83"]["n"] == n


def test_keep_and_reading_during_send_are_not_lost():
    """Ревью r2 S1 (проба 10): «Оставить» по теме 1190 и новое чтение по 83, пришедшие, пока сверка 83 отправляет
    карточку, переживают её запись: карточка 1190 не воскресает, отказ не теряется, чтение лежит."""
    _fresh({83: N83, 1190: N1190})
    t = CLOCK[0]
    st = _st(1190, ("9315", 70), ("9315", 75), base=t)
    st = _st(83, ("2478", 1), ("2478", 2), base=t, st=st)
    v = PW.verdict(st, 1190, N1190, _book(1190), t, others=PW.fleet_numbers(BOOK, {}, 1190))
    assert v["kind"] == PW.KIND_RENAME, v
    st, n = PW.next_seq(st, floor=1)
    st = PW.with_card_msg(PW.with_card(st, v, n, t, chat_id=SERV), 1190, n, 9001, notify.HQ_CHAT_ID)
    S._plate_keep(st)
    SEND_DELAY[0] = 0.3
    qbox = []

    async def race():
        async def keep():
            await asyncio.sleep(0.05)
            q = _Q(f"svc:plkeep:{n}", OWNER, 9001)
            qbox.append(q)
            await S.handle_service_button(types.SimpleNamespace(callback_query=q), _Ctx(), _World())

        async def note():
            await asyncio.sleep(0.05)
            assert S._plate_note(SERV, 83, _Msg(83, 777), _plate("2478"))
        await asyncio.gather(S._plate_tick(SERV, 83), keep(), note())
    asyncio.run(race())
    fin = PW.clean(S._PLATE_STATE)
    assert "1190" not in fin["cards"] and fin["declined"]["1190"]["d"] == "9315", fin
    assert 777 in [r["mid"] for r in fin["readings"]["83"]], fin["readings"]["83"]
    assert fin["cards"]["83"]["msg"] == CARDS[0]["mid"], fin["cards"]
    assert any("Оставлено" in str(e) for e in qbox[0].edits), qbox[0].edits


def test_reply_does_not_wait_for_the_card():
    """Ревью r2 S11: сверка — фоновой задачей; медленная отправка карточки не держит ответ механику."""
    _fresh({83: N83})
    _photo(83, 4411, _plate("2478"))
    SEND_DELAY[0] = 0.6
    ctx, claude, saved = _Ctx(), _Claude([_plate("2478")]), S._download_photo
    box = {}

    async def _dl(pm):
        return b"\xff\xd8 test"

    async def go():
        t0 = time.monotonic()
        await S.handle(types.SimpleNamespace(message=_Msg(83, 4520)), ctx, _World(), claude)
        box["took"], box["cards_before"], box["pending"] = time.monotonic() - t0, len(CARDS), len(S._PLATE_TASKS)
        await S._plate_drain()
    S._download_photo = _dl
    try:
        asyncio.run(go())
    finally:
        S._download_photo = saved
    assert box["cards_before"] == 0 and box["pending"] >= 1 and box["took"] < 0.5, box
    assert len(CARDS) == 1, CARDS


def test_corrupt_memory_silences_and_keeps_the_file():
    """Ревью r2 S3: файл памяти есть, но не читается → ни чтений, ни карточек до перезапуска; файл не трогаем."""
    _fresh({83: N83})
    path = os.environ["PLATE_WATCH_STATE"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("{битый")
    _two(83, "2478")
    assert CARDS == [] and S._PLATE_BROKEN, S._PLATE_BROKEN
    with open(path, encoding="utf-8") as f:
        assert f.read() == "{битый"


def test_drifted_name_gives_no_card():
    """Ревью r2 M3 живьём: в memory.db у 82 уплывшее имя «…3902» с прежней меткой, Telegram зовёт тему «…5104»."""
    drift = "XADV 750 BLACK 3902"
    for d in ("5104", "3902"):                  # 3902 — старая табличка на байке: и «совпадает» тоже не говорим
        _fresh({82: drift}, mem=_Mem({(SERV, 82): drift}, {(SERV, 82): "forum_created"}))
        _two(82, d, mid=900)
        assert CARDS == [] and FEEDS == [], (d, CARDS, FEEDS)
    # контроль: то же уплывшее имя, но пришедшее событием переименования после правки, — сверка говорит
    _fresh({82: drift}, mem=_Mem({(SERV, 82): drift}, {(SERV, 82): PW.SRC_EVENT}))
    _two(82, "3902", mid=960)
    assert CARDS == [] and len(FEEDS) == 1, (CARDS, FEEDS)


def test_manual_binding_no_card_and_press_refused():
    """Ревью r2 S6: /bike держит имя байка — карточки нет; привязка появилась после карточки — нажатие отказывает
    словами, а не пишет «✅ Переименовано»."""
    _fresh({83: N83})
    S.set_topic_bike(SERV, 83, N83)
    _two(83, "2478")
    assert CARDS == []
    _fresh({83: N83})
    _two(83, "2478", mid=4430)
    ren = CARDS[0]["buttons"][0][0][1]
    S.set_topic_bike(SERV, 83, N83)
    q, ctx = _press(ren, OWNER)
    assert not ctx.bot.renamed and "/bike" in q.answers[0][0] and q.answers[0][1].get("show_alert"), q.answers
    assert not any("✅" in str(e) for e in q.edits), q.edits


def test_topic_not_modified_is_success():
    _fresh({83: N83})
    _two(83, "2478")
    ren = CARDS[0]["buttons"][0][0][1]
    q, ctx = _press(ren, OWNER, ctx=_Ctx(rename_error="Bad Request: TOPIC_NOT_MODIFIED"))
    assert ctx.bot.renamed and S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 2478"
    assert any("✅ Переименовано" in str(e) and "уже звалась так" in str(e) for e in q.edits), (q.edits, q.answers)
    assert PW.clean(S._PLATE_STATE)["cards"] == {}


def test_warning_goes_to_the_feed_not_the_inbox():
    """Ревью r2 S7: «имя = номер на байке, но ≠ книге» — заметка без кнопок; в инбокс 1160 ей пути нет."""
    _fresh({})
    ren = _Msg(83, 4000, photo=False)
    ren.forum_topic_edited = types.SimpleNamespace(name="XADV 750CC GREY 2478")
    S._remember_topic_name(SERV, 83, ren)                     # событие переименования — имени верим
    _two(83, "2478")
    assert CARDS == [] and len(FEEDS) == 1 and "⚠️ Номер на байке не совпадает с зелёной книгой (9286)" in FEEDS[0]
    _two(83, "2478", mid=4500)                                # неделю не повторяем
    assert len(FEEDS) == 1, FEEDS


def test_bike_topic_id_finds_topic_by_plate():
    _fresh({83: "XADV 750CC GREY 2478", 1190: N1190})
    assert S._bike_topic_id(SERV, N1190) == 1190                       # точное имя — как было
    assert S._bike_topic_id(SERV, N83) == 83                           # номер книги → тема книги
    assert S._bike_topic_id(SERV, "XADV 750 GREY 2478") == 83          # номер из имени
    _fresh({83: "XADV 750CC GREY 2478", 990083: "TEST 155CC 2478"})
    assert S._bike_topic_id(SERV, "XADV 750 GREY 2478") is None        # номер у двух тем — не гадаем
    assert S._bike_topic_id(SERV, "NO NUMBER") is None


# --- ревью r3, живьём ------------------------------------------------------------------------
def test_r3_live_old_plate_of_bike_83_posted_into_topic_70_no_card():
    """correctness-oldplate-not-other-bike живьём: все темы названы по книге (как после 24.10); байк темы 83 (на нём
    2478) дважды, через 7 ч, снят в теме 70 «FORZA 300CC WHITE 8950». Прежде — карточка «… 2478» владельцу."""
    _fresh({b["topic_id"]: b["name"] for b in BOOK["bikes"]})
    _two(70, "2478", mid=5001)
    assert CARDS == [] and FEEDS == [], (CARDS, FEEDS)


def test_r3_live_number_not_last_in_another_topic_name_no_card():
    """safety-other-bike-name живьём: чёрный ADV350 6699 (тема 4615 «ADV350 6699 black new») дважды снят в теме 62."""
    _fresh({62: "ADV 350CC BLACK 5662", 4615: "ADV350 6699 black new"})
    _two(62, "6699", mid=5101)
    assert CARDS == [] and FEEDS == [], (CARDS, FEEDS)
    assert S._bike_topic_id(SERV, "ADV 6699") == 4615                  # мост и бот находят 6699 у темы 4615


def test_r3_live_misread_of_an_old_plate_is_a_note_not_a_rename():
    """safety-unknown-plate-rename живьём: тема 66, на байке 9011, стёртая «1» читается «7» в двух заходах. Прежде —
    карточка «CB 300CC R 9017»; теперь заметка без кнопок в ленту, раз в 7 суток."""
    _fresh({66: "CB 300CC R 461"})
    _two(66, "9017", mid=5201)
    assert CARDS == [] and len(FEEDS) == 1, (CARDS, FEEDS)
    assert FEEDS[0].startswith("🔢 На байке читается 9017") and "Предлагаю" not in FEEDS[0], FEEDS[0]
    _two(66, "9017", mid=5210)
    assert CARDS == [] and len(FEEDS) == 1, FEEDS


def test_r3_live_engine_size_topic_name_no_card():
    """safety-engine-size-as-topic-plate живьём: тему нового байка создали как «NMAX 155» (событие создания — имени
    верим); на байке временная красная табличка 4321. Прежде — карточка «NMAX 4321», теряющая объём."""
    _fresh({})
    created = _Msg(990155, 4000, photo=False)
    created.forum_topic_created = types.SimpleNamespace(name="NMAX 155")
    S._remember_topic_name(SERV, 990155, created)
    _two(990155, "4321", mid=5301)
    assert CARDS == [] and FEEDS == [], (CARDS, FEEDS)


def test_r3_send_failure_or_cancel_frees_the_card_slot():
    """correctness-zombie-card: место карточки занято ДО отправки; упала отправка или задачу отменили (перезапуск,
    self-update) — место освобождается сразу, а не держит тему 7 суток."""
    _fresh({83: N83})
    S._plate_keep(_st(83, ("2478", 1), ("2478", 2), base=CLOCK[0]))

    def _boom(text, buttons=None):
        raise RuntimeError("сеть упала")
    notify.send_card = _boom
    try:
        asyncio.run(S._plate_tick(SERV, 83))
    finally:
        notify.send_card = _fake_send_card
    assert PW.clean(S._PLATE_STATE)["cards"] == {}, S._PLATE_STATE
    asyncio.run(S._plate_tick(SERV, 83))                                  # следующая сверка — карточка идёт
    assert len(CARDS) == 1 and PW.clean(S._PLATE_STATE)["cards"]["83"]["msg"] == CARDS[0]["mid"]

    # отмена посреди отправки: поток всё равно дошлёт карточку, но её место снято — кнопка её не исполнит
    _fresh({83: N83})
    S._plate_keep(_st(83, ("2478", 1), ("2478", 2), base=CLOCK[0]))
    SEND_DELAY[0] = 0.3
    box = {}

    async def cancel_mid_send():
        t = asyncio.ensure_future(S._plate_tick(SERV, 83))
        await asyncio.sleep(0.05)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            box["cancelled"] = True
    asyncio.run(cancel_mid_send())
    SEND_DELAY[0] = 0.0
    assert box.get("cancelled") and PW.clean(S._PLATE_STATE)["cards"] == {}, (box, S._PLATE_STATE)
    assert len(CARDS) == 1                                                 # доставленная, но отменённая
    q, ctx = _press(CARDS[0]["buttons"][0][0][1], OWNER)
    assert not ctx.bot.renamed and q.answers[0][1].get("show_alert"), q.answers
    asyncio.run(S._plate_tick(SERV, 83))
    assert len(CARDS) == 2 and PW.clean(S._PLATE_STATE)["cards"]["83"]["msg"] == CARDS[1]["mid"]

    # карточка без сообщения уже лежит на диске (оборвалась до этой правки) — следующая сверка её снимает
    _fresh({83: N83})
    st = _st(83, ("2478", 1), ("2478", 2), base=CLOCK[0])
    v = PW.verdict(st, 83, N83, _book(83), CLOCK[0] - 600, others=PW.fleet_numbers(BOOK, {}, 83))
    st, n = PW.next_seq(st)
    S._plate_keep(PW.with_card(st, v, n, CLOCK[0] - 600, chat_id=SERV))
    asyncio.run(S._plate_tick(SERV, 83))
    pend = PW.clean(S._PLATE_STATE)["cards"]["83"]
    assert len(CARDS) == 1 and pend["n"] != n and pend["msg"] == CARDS[0]["mid"], (CARDS, pend)


def test_r3_kill_switch_disarms_cards_already_sent():
    """correctness-killswitch-buttons / safety-kill-switch-not-disarming: PLATE_WATCH=0 после рассылки — нажатие
    «Переименовать тему» не переименовывает, карточка снимается со словами; «Оставить» работает; поиск темы по
    номеру тоже выключен."""
    prev = os.environ.get("PLATE_WATCH")
    try:
        _fresh({83: N83})
        _two(83, "2478")
        ren = CARDS[0]["buttons"][0][0][1]
        os.environ["PLATE_WATCH"] = "0"
        S._PLATE_STATE = None                                              # и перезапуск: память — с диска
        q, ctx = _press(ren, OWNER)
        assert not ctx.bot.renamed and q.answers[0][1].get("show_alert") and "выключено" in q.answers[0][0], q.answers
        assert any("Не переименовал" in str(e) for e in q.edits), q.edits
        assert PW.clean(S._PLATE_STATE)["cards"] == {} and S._TOPIC_NAMES[(SERV, 83)] == N83
        os.environ["PLATE_WATCH"] = "1"
        _fresh({83: N83})
        _two(83, "2478", mid=4900)
        keep = CARDS[0]["buttons"][0][1][1]
        os.environ["PLATE_WATCH"] = "0"
        q, ctx = _press(keep, OWNER)
        assert not ctx.bot.renamed and any("Оставлено" in str(e) for e in q.edits), q.edits
        _fresh({83: "XADV 750CC GREY 2478"})
        os.environ["PLATE_WATCH"] = "0"
        assert S._bike_topic_id(SERV, N83) is None                          # как до 25.10
        os.environ["PLATE_WATCH"] = "1"
        assert S._bike_topic_id(SERV, N83) == 83
    finally:
        os.environ["PLATE_WATCH"] = prev if prev is not None else "1"


def test_r3_press_during_send_waits_for_the_lock():
    """tests-deploy-1: замок S1 держит сверку и нажатие по одному. Владелец жмёт кнопку карточки, которую Telegram
    уже показал, пока `send_card` ещё ждёт ответа: без замка место ещё без сообщения, и нажатие отказывало бы «не от
    этой карточки»; с замком оно ждёт конца отправки и исполняется."""
    _fresh({83: N83})
    S._plate_keep(_st(83, ("2478", 1), ("2478", 2), base=CLOCK[0]))
    SEND_DELAY[0] = 0.3
    box = {}

    async def race():
        async def press():
            await asyncio.sleep(0.05)
            n = PW.clean(S._PLATE_STATE)["cards"]["83"]["n"]               # место занято до отправки
            box["q"] = q = _Q(f"svc:{S._PLATE_BTN_KEEP}:{n}", OWNER, 7001)   # 7001 — сообщение, куда ляжет карточка
            await S.handle_service_button(types.SimpleNamespace(callback_query=q), _Ctx(), _World())
        await asyncio.gather(S._plate_tick(SERV, 83), press())
    asyncio.run(race())
    q = box["q"]
    assert CARDS and CARDS[0]["mid"] == 7001, CARDS
    assert any("Оставлено" in str(e) for e in q.edits), (q.edits, q.answers)
    fin = PW.clean(S._PLATE_STATE)
    assert "83" not in fin["cards"] and fin["declined"]["83"]["d"] == "2478", fin


# ============================================================================================
#  (4) ДРЕЙФ ИМЕНИ ТЕМЫ
# ============================================================================================
def test_drift_ordinary_reply_to_creation_does_not_overwrite():
    """Живой случай 82: 16.06 переименована в «XADV 750 BLACK 5104», 21.10 09:23:30 UTC обычное фото
    @Pleummmm (reply на сообщение создания с ПЕРВЫМ именем) вернуло имя бота к «…3902»."""
    mem = _Mem({(SERV, 82): "XADV 750 BLACK 5104"})
    _fresh({82: "XADV 750 BLACK 5104"}, mem=mem)
    msg = _Msg(82, 13000, reply_name="XADV 750 BLACK 3902", user=_User("pleummmm", 99001))
    assert S._remember_topic_name(SERV, 82, msg) == "XADV 750 BLACK 5104"
    assert S._TOPIC_NAMES[(SERV, 82)] == "XADV 750 BLACK 5104" and mem.calls == [], mem.calls
    # и через живой путь фото (так и было 21.10)
    _photo(82, 13001, {"kind": "bike", "dirt": False}, reply_name="XADV 750 BLACK 3902")
    assert S.bike_from_topic(SERV, 82) == "XADV 750 BLACK 5104" and mem.calls == [], mem.calls
    # кэш пуст (до засева), имя знает только memory.db — тоже не переписываем
    S._TOPIC_NAMES.clear()
    S._remember_topic_name(SERV, 82, msg)
    assert S.bike_from_topic(SERV, 82) == "XADV 750 BLACK 5104" and mem.calls == [], mem.calls


def test_drift_missing_name_is_filled_and_events_stay_authoritative():
    # номера тем — вне живого форума: на сервере рядом лежит topics_map.json, и тема 82 в нём известна
    t, t2 = 990082, 990084
    mem = _Mem()
    _fresh({}, mem=mem)
    msg = _Msg(t, 13002, reply_name="XADV 750 BLACK 3902")
    assert S._remember_topic_name(SERV, t, msg) == "XADV 750 BLACK 3902"      # пусто → заполнить
    # r2 (M3): заполнение из reply — своя метка, сверка номера ему не верит
    assert mem.calls == [(SERV, t, "XADV 750 BLACK 3902", PW.SRC_REPLY)], mem.calls
    assert S._plate_name_src(SERV, t) == PW.SRC_REPLY
    ren = _Msg(t, 13003, photo=False)
    ren.forum_topic_edited = types.SimpleNamespace(name="XADV 750 BLACK 5104")
    assert S._remember_topic_name(SERV, t, ren) == "XADV 750 BLACK 5104"      # переименование пишет всегда
    assert mem.calls[-1] == (SERV, t, "XADV 750 BLACK 5104", PW.SRC_EVENT), mem.calls
    assert S._plate_name_src(SERV, t) == PW.SRC_EVENT
    created = _Msg(t2, 13004, photo=False)
    created.forum_topic_created = types.SimpleNamespace(name="NEW BIKE 1234")
    S._TOPIC_NAMES[(SERV, t2)] = "OLD 1"
    assert S._remember_topic_name(SERV, t2, created) == "NEW BIKE 1234"       # создание — тоже
    icon_only = _Msg(t, 13005, photo=False, reply_name="XADV 750 BLACK 3902")
    icon_only.forum_topic_edited = types.SimpleNamespace(name=None)          # сменили только значок
    assert S._remember_topic_name(SERV, t, icon_only) == "XADV 750 BLACK 5104"
    # после перезапуска происхождение знает memory.db; ручная привязка там сильнее всего
    S._TOPIC_NAME_SRC.clear()
    assert S._plate_name_src(SERV, t) == PW.SRC_EVENT
    mem.sources[(SERV, t)] = "manual"
    assert S._plate_name_src(SERV, t) == PW.SRC_MANUAL
    S.set_memory(None)


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    S.set_memory(None)
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
