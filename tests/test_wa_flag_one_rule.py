#!/usr/bin/env python3
"""ОДНО ПРАВИЛО ФЛАГА WA_AGENT_ATTACH у службы и у вебхука (INTEG-0710, доработка Д6 к Б3в NIGHT0710-B3v).

Замечание финального проверяющего Б3в: «правило флага вебхука — вторая реализация `flag_on`; нужен тест „наборы
равны“». Выключатель WA_AGENT_ATTACH читают три места, и все три объявляют одно правило «1/true/yes/on после
strip+lower — вкл, всё прочее — выкл»:
  · служба wa-agent — `wa_agent_svc.attach_of` → `wa_agent_tg.flag_on(environ.get(F_ATTACH))` (это и есть правило);
  · вебхук wa-webhook — `wa_webhook.statuses_on(environ)`: квитанции `wa_status` под тем же выключателем (R15) —
    СВОЯ копия правила;
  · ядро PDF — `wa_agent_attach.enabled(env)` — тоже своя копия (с `flag_on` её уже сравнивает
    `test_wa_attach_svc.test_flag_one_rule_true_equals_one` на 11 значениях; здесь — на том же наборе, что вебхук).
Копия у вебхука НАМЕРЕННАЯ: он тонкий транзит, импорт ровно `wa_kind`; `import wa_agent_tg` потянул бы в процесс
приёма весь агент. Поэтому копию не сносим, а держим равной: один и тот же набор значений → один и тот же ответ.

ДОМЕН — значения окружения: строка или «переменной нет» (None). Вне домена (int/bool) копии расходятся формой
(`flag_on` падает AttributeError, `statuses_on` приводит `str()`), но окружение процесса таких значений не держит —
это не расхождение правила (названо в заметках доработки, код не правлен).

Всё — чистые функции: ни сети, ни файлов, ни базы, временного каталога нет вовсе. Окружение процесса меняется только
в одной проверке (путь вебхука по умолчанию, environ=None) и возвращается в finally.
Все проверки — «как раньше»: на дереве без правки (правки нет — копии равны) набор зелёный; зубы показаны мутантами
(расхождение любой одной копии → красное)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_webhook as W  # noqa: E402

KEY = S.F_ATTACH          # имя выключателя берётся у СЛУЖБЫ: опечатка в ключе вебхука — тоже расхождение

# Невидимые и «чужие» знаки строятся через chr(), а не литералом: глазом их не отличить, редактор их не сбережёт.
NBSP, EMSP, IDSP = chr(0x00A0), chr(0x2003), chr(0x3000)      # пробелы: str.strip их СНИМАЕТ
ZWSP, BOM = chr(0x200B), chr(0xFEFF)                            # не пробелы: str.strip их НЕ снимает
LONG_S = chr(0x017F)                                            # «длинное s»: lower() оставляет, casefold() даёт «s»


def _fw(text):
    """Полноширинная запись ASCII-строки («１», «ｏｎ»): на вид то же слово, по знакам — другое."""
    return "".join(chr(ord(c) + 0xFEE0) for c in text)


# Набор Штаба (Д6) дословно — с ответом, который правило даёт сегодня («как раньше»).
GOLDEN = (
    (None, False), ("", False), ("0", False), ("1", True), ("true", True), ("TRUE", True), (" yes ", True),
    ("on", True), ("off", False), ("no", False), ("2", False), ("да", False), ("false", False), ("True ", True),
    ("\t1\n", True),
)
# Родня набора: каждое из четырёх слов в разных регистрах и с пробелами любого вида (str.strip снимает и NBSP, и
# широкий пробел, и разделители \x1c–\x1f); похожие, но чужие слова; числа; кавычки; невидимые не-пробелы.
MORE = (
    "yes", "YES", "Yes", "yEs", "ON", "On", "oN", "True", "tRuE", "1 ", " 1", " on", "off ", " no", "FALSE",
    " ", "\t", "\n", "\r\n1\r\n", "\x0bon\x0c", "\x1c1\x1f", NBSP + "1" + NBSP, EMSP + "on" + EMSP,
    IDSP + "yes" + IDSP, ZWSP + "1", BOM + "1", "1\x00", _fw("1"), _fw("on"), _fw("yes"), "ye" + LONG_S,
    "01", "00", "+1", "-1", "1.0", "10", "11", "y", "t", "n", "f", "yes!", "on.", "1;", "'1'", '"on"', "1 1",
    "o n", "t r u e", "yes please", "onn", "trueish", "enable", "enabled", "вкл", "истина", "нет", "ДА", "None",
    "null",
)
VALUES = tuple(v for v, _ in GOLDEN) + MORE


def _env(v):
    """Окружение, в котором выключатель имеет значение v; None — переменной нет вовсе."""
    return {} if v is None else {KEY: v}


def _service(env):
    """Как служба судит выключатель: правило `flag_on` над тем, что она читает (`attach_of`, wa_agent_svc.py)."""
    return G.flag_on(env.get(KEY))


def _service_reader(env):
    """Сам читатель службы `attach_of`: флаг не запрошен → (False, None, None) — строки старта нет; запрошен (без
    черновиков) → строка «флаг 1, черновиков нет …». Сети, моста и модели при drafts=False он не касается."""
    return S.attach_of(env, False, None) != (False, None, None)


def test_webhook_equals_service_on_one_set():
    """Д6: один набор значений → вебхук отвечает ровно то же, что правило службы, и оба отвечают bool."""
    diff = []
    for v in VALUES:
        envs = [_env(v)] + ([{KEY: None}] if v is None else [])    # «нет переменной» и «None в окружении»
        for env in envs:
            svc, hook = _service(env), W.statuses_on(env)
            if type(svc) is not bool or type(hook) is not bool or svc is not hook:
                diff.append((v, env == {}, svc, hook))
    assert not diff, "копии правила флага разошлись (значение, переменной нет?, служба, вебхук): %r" % diff[:12]


def test_golden_as_before():
    """Как раньше: набор Штаба даёт у обеих копий тот же ответ, что и сегодня (правило не менялось)."""
    bad = [(v, want, G.flag_on(v), W.statuses_on(_env(v))) for v, want in GOLDEN
           if G.flag_on(v) is not want or W.statuses_on(_env(v)) is not want]
    assert not bad, "набор Штаба (значение, ждали, служба, вебхук): %r" % bad


def test_webhook_default_environ_same_rule():
    """Путь службы wa-webhook: `WAQueueDB(path)` зовёт `statuses_on()` без окружения — читается окружение ПРОЦЕССА.
    На нём тот же набор → тот же ответ, что у службы. Чего окружение процесса не держит (NUL — нигде; не-ASCII — только
    при не-UTF-8 кодировке ФС), то вне домена и не сравнивается; при UTF-8 вне домена ровно одно значение — с NUL."""
    saved = os.environ.get(KEY)
    utf8 = sys.getfilesystemencoding().lower().replace("-", "") == "utf8"
    cant, seen, diff = [], 0, []
    try:
        for v in VALUES:
            if v is None:
                os.environ.pop(KEY, None)
            else:
                try:
                    os.environ[KEY] = v
                except (ValueError, UnicodeError):
                    cant.append(v)
                    continue
            seen += 1
            svc, hook = G.flag_on(os.environ.get(KEY)), W.statuses_on()
            if svc is not hook:
                diff.append((v, svc, hook))
    finally:
        if saved is None:
            os.environ.pop(KEY, None)
        else:
            os.environ[KEY] = saved
    assert "1\x00" in cant and all("\x00" in v or not v.isascii() for v in cant), cant
    assert seen == len(VALUES) - len(cant) and (not utf8 or cant == ["1\x00"]), (cant, seen, utf8)
    assert not diff, "окружение процесса: вебхук разошёлся со службой (значение, служба, вебхук): %r" % diff[:12]


def test_service_reader_and_core_same_set():
    """Тот же набор у двух других читателей того же слова: `wa_agent_svc.attach_of` (служба) и
    `wa_agent_attach.enabled` (ядро PDF) — ответ правила `flag_on`; имя выключателя у всех трёх одно."""
    import wa_agent_attach as X
    assert X.F_ATTACH == KEY == W.STATUS_FLAG == "WA_AGENT_ATTACH", (X.F_ATTACH, KEY, W.STATUS_FLAG)
    diff = []
    for v in VALUES:
        want = G.flag_on(v)
        got = (_service_reader(_env(v)), X.enabled(_env(v)))
        if got != (want, want):
            diff.append((v, want, got))
    assert X.enabled(None) is False and W.statuses_on({}) is False and _service_reader({}) is False
    assert not diff, "читатели WA_AGENT_ATTACH разошлись с правилом (значение, правило, (служба, ядро)): %r" % diff[:12]


def test_set_has_teeth():
    """Набор не пуст по смыслу: в нём есть и «вкл», и «выкл»; каждое из четырёх слов — дословно, в чужом регистре и с
    пробелом; есть похожие, но чужие слова — иначе равенство копий было бы равенством на пустом месте."""
    assert len(set(VALUES)) == len(VALUES), "в наборе повторы"
    on = [v for v in VALUES if G.flag_on(v)]
    off = [v for v in VALUES if not G.flag_on(v)]
    assert len(on) >= 20 and len(off) >= 30, (len(on), len(off))
    for word in ("1", "true", "yes", "on"):
        assert word in VALUES, word
        assert any(v != word and v.strip() != v and v.strip().lower() == word for v in on), "с пробелом: " + word
        assert word == "1" or any(v != v.lower() and v.lower() == word for v in on), "в чужом регистре: " + word
    for near in ("2", "да", "y", "t", "enable", "off", "no", "false", "1.0", "01", ZWSP + "1", _fw("1"),
                 "ye" + LONG_S):
        assert near in off, repr(near)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    on = sum(1 for v in VALUES if G.flag_on(v))
    print("набор: значений %d (Штаба %d, родни %d) · вкл %d · выкл %d" % (
        len(VALUES), len(GOLDEN), len(MORE), on, len(VALUES) - on))
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:600])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
