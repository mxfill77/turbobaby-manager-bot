"""Фикс аудита row9 (08.07, тема 222): тайский блок квитанций приёмки работ нёс только
«รับงานแล้วครับ … ส่งเลขไมล์» БЕЗ списка работ → TH 49 симв < 40% от RU 175 (style_issue).
Теперь список работ в ОБОИХ блоках: 🇹🇭 тайские названия (_works_th_str/_work_th), 🇷🇺 русские.
Покрывает msg_work_receipt + msg_works_logged (тот же класс) + хелпер _works_th_str.
Обновлено 14.07.2026: fallback неизвестных работ = 'งานอื่น ๆ (ru)' (с русским текстом в скобках);
дедуп теперь схлопывает только ИДЕНТИЧНЫЕ переводы, разные неизвестные — разные строки."""
import os, sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

# Ровно набор работ из аудит-кейса row9 (X MAX GREEN 4248, 08.07 06:11)
ROW9_WORKS = ["замена аккумулятора", "замена моторного масла", "замена масла в редукторе",
              "замена масляного фильтра", "замена рамки номерного знака"]
CYR = re.compile(r"[А-Яа-яЁё]")
THAI = re.compile(r"[฀-๿]")
# Кириллица ДОПУСТИМА только внутри скобок fallback «งานอื่น ๆ (…)» — проверяем ВНЕ скобок.
CYR_OUTSIDE_BRACKETS = re.compile(r"[А-Яа-яЁё](?![^(]*\))")


def _th_ru_lines(msg):
    th = next(l for l in msg.split("\n") if l.startswith("🇹🇭"))
    ru = next(l for l in msg.split("\n") if l.startswith("🇷🇺"))
    return th, ru


def test_receipt_row9_works_translated():
    """Кейс row9: известные работы имеют тайские лейблы; неизвестная (рамка) → fallback с русским."""
    msg = S.msg_work_receipt("X MAX GREEN 4248", ROW9_WORKS)
    th, ru = _th_ru_lines(msg)
    for lbl in ("แบตเตอรี่", "เปลี่ยนน้ำมันเครื่อง", "น้ำมันเกียร์", "ไส้กรองน้ำมันเครื่อง"):
        assert lbl in th, f"в 🇹🇭 нет {lbl!r}: {th}"
    # Неизвестная работа → fallback «งานอื่น ๆ (замена рамки номерного знака)»
    assert "งานอื่น ๆ" in th, f"неизвестная работа (рамка) должна дать fallback: {th}"
    assert "замена рамки номерного знака" in th, f"русский текст неизвестной работы в 🇹🇭: {th}"
    # Кириллица разрешена ТОЛЬКО внутри скобок fallback, не голым текстом
    th_no_brackets = re.sub(r"\([^)]*\)", "", th)
    assert not CYR.search(th_no_brackets), f"кириллица вне скобок в 🇹🇭: {th}"
    # RU-блок как был: полный список + просьба пробега
    for w in ROW9_WORKS:
        assert w in ru, f"в 🇷🇺 нет {w!r}"
    assert "пришли пробег" in ru and "รบกวนส่งเลขไมล์" in th


def test_receipt_passes_auditor_length_rule():
    """Само правило аудита row9: тайский блок ≥ 40% длины русского."""
    msg = S.msg_work_receipt("X MAX GREEN 4248", ROW9_WORKS)
    th, ru = _th_ru_lines(msg)
    th_len, ru_len = len(th) - len("🇹🇭 "), len(ru) - len("🇷🇺 ")
    assert th_len >= 0.4 * ru_len, f"TH {th_len} < 40% от RU {ru_len} — аудит снова флагнет"


def test_works_logged_same_class():
    """msg_works_logged — тот же класс: известные работы в 🇹🇭 без кириллицы вне скобок."""
    msg = S.msg_works_logged("NMAX 4255", 29275, ["замена моторного масла", "воздушный фильтр"])
    th, ru = _th_ru_lines(msg)
    assert "เปลี่ยนน้ำมันเครื่อง" in th and "ไส้กรองอากาศ" in th, th
    th_no_brackets = re.sub(r"\([^)]*\)", "", th)
    assert not CYR.search(th_no_brackets), f"кириллица вне скобок в 🇹🇭: {th}"
    assert "29275" in th and "29275" in ru, "км в обоих блоках"
    assert "замена моторного масла" in ru and "воздушный фильтр" in ru


def test_th_dedup_and_unknown():
    """Хелпер: две разные неизвестные → два разных fallback (не схлопываются);
    два синонима масла → один тайский лейбл (идентичный перевод дедупится)."""
    s = S._works_th_str(["рамка номера", "покраска зеркала", "замена моторного масла",
                         "моторное масло"])
    # Разные неизвестные → разные fallback «งานอื่น ๆ (ru1)» и «งานอื่น ๆ (ru2)»
    assert s.count("งานอื่น ๆ") == 2, f"ожидали 2 разных fallback: {s}"
    assert "рамка номера" in s, f"ru1 в fallback: {s}"
    assert "покраска зеркала" in s, f"ru2 в fallback: {s}"
    # Синонимы масла → один тайский лейбл (дедуп идентичных переводов цел)
    assert s.count("เปลี่ยนน้ำมันเครื่อง") == 1, f"дубль масла схлопывается: {s}"


def test_empty_works_no_dangling_colon():
    """Пустой/мусорный список работ → прежняя форма без висячего ': '."""
    for works in ([], ["", "  "]):
        msg = S.msg_work_receipt("NMAX 4255", works)
        th, ru = _th_ru_lines(msg)
        assert ": " not in th and ": " not in ru, msg
        assert "รับงานแล้วครับ NMAX 4255 —" in th, th
    m2 = S.msg_works_logged("NMAX 4255", 100, [])
    th2, _ = _th_ru_lines(m2)
    assert "แล้วครับ NMAX 4255 🛠️" in th2, th2


# ============ ГОЛДЕН кейс 6334 (NINJA 400, 14:53 14.07.2026) ============
CASE_6334_WORKS = ["сальники вилки", "колодки", "задняя звезда", "смазка цепи", "регулировка натяжения"]
CASE_6334_EXPECTED_TH = {
    "сальники вилки": "ซีลโช้คหน้า",
    "колодки": "ผ้าเบรก",          # стем «колод»
    "задняя звезда": "เฟืองโซ่หลัง",
    "смазка цепи": "หล่อลื่นโซ่",
    "регулировка натяжения": "ปรับตึงโซ่",
}


def test_golden_6334_all_specific():
    """Голден кейс 6334: 5 работ → 5 конкретных тайских строк, ни одна не «งานอื่น ๆ»."""
    for w, expected_th in CASE_6334_EXPECTED_TH.items():
        result = S._work_th(w)
        assert result == expected_th, f"_work_th({w!r}) = {result!r}, ожидали {expected_th!r}"
        assert not result.startswith("งานอื่น ๆ"), f"работа {w!r} попала в fallback: {result}"


def test_golden_6334_no_duplicates_in_summary():
    """В сводке 5 работ → 5 отдельных тайских строк, все уникальные — нет дублей."""
    th_list = [S._work_th(w) for w in CASE_6334_WORKS]
    assert len(th_list) == len(set(th_list)), f"дубли тайских переводов: {th_list}"
    for th in th_list:
        assert not th.startswith("งานอื่น ๆ"), f"работа попала в fallback: {th}"


def test_golden_6334_no_chain_duplicates():
    """Специфично для кейса 6334: смазка и натяжение цепи → РАЗНЫЕ тайские строки (не «โซ่» дважды)."""
    th_smazka = S._work_th("смазка цепи")
    th_natya = S._work_th("регулировка натяжения")
    assert th_smazka != th_natya, f"смазка и натяжение дали одинаковый перевод: {th_smazka}"
    assert th_smazka != "โซ่", f"смазка цепи схлопнулась в общий «цепь»: {th_smazka}"
    assert th_natya != "โซ่", f"натяжение схлопнулось в общий «цепь»: {th_natya}"


def test_golden_6334_receipt_5_lines():
    """msg_service_summary с 5 работами кейса 6334 → 5 отдельных тайских строк в 🇹🇭-блоке."""
    acc = {"works": CASE_6334_WORKS, "works_km": "43000", "current_km": "43000"}
    msg = S.msg_service_summary("NINJA 400 6334", acc)
    th_lines = [l.strip() for l in msg.split("\n") if l.strip().startswith("— ")]
    th_lines_th = [l for l in th_lines if THAI.search(l)]
    assert len(th_lines_th) >= 5, f"ожидали ≥5 тайских строк работ, получили {len(th_lines_th)}: {th_lines_th}"
    th_texts = [l.lstrip("— ").strip() for l in th_lines_th]
    assert len(th_texts) == len(set(th_texts)), f"дубли строк в сводке: {th_texts}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов тайского списка работ (row9 + голден 6334)")
