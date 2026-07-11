"""Фикс аудита row9 (08.07, тема 222): тайский блок квитанций приёмки работ нёс только
«รับงานแล้วครับ … ส่งเลขไมล์» БЕЗ списка работ → TH 49 симв < 40% от RU 175 (style_issue).
Теперь список работ в ОБОИХ блоках: 🇹🇭 тайские названия (_works_th_str/_work_th), 🇷🇺 русские.
Покрывает msg_work_receipt + msg_works_logged (тот же класс) + хелпер _works_th_str."""
import os, sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

# Ровно набор работ из аудит-кейса row9 (X MAX GREEN 4248, 08.07 06:11)
ROW9_WORKS = ["замена аккумулятора", "замена моторного масла", "замена масла в редукторе",
              "замена масляного фильтра", "замена рамки номерного знака"]
CYR = re.compile(r"[А-Яа-яЁё]")
THAI = re.compile(r"[฀-๿]")


def _th_ru_lines(msg):
    th = next(l for l in msg.split("\n") if l.startswith("🇹🇭"))
    ru = next(l for l in msg.split("\n") if l.startswith("🇷🇺"))
    return th, ru


def test_receipt_row9_works_translated():
    """Кейс row9 дословно: тайский блок несёт список работ, без кириллицы."""
    msg = S.msg_work_receipt("X MAX GREEN 4248", ROW9_WORKS)
    th, ru = _th_ru_lines(msg)
    for lbl in ("แบตเตอรี่", "เปลี่ยนน้ำมันเครื่อง", "น้ำมันเกียร์", "ไส้กรองน้ำมันเครื่อง"):
        assert lbl in th, f"в 🇹🇭 нет {lbl!r}: {th}"
    assert "งานอื่น ๆ" in th, f"неизвестная работа (рамка номера) → 'งานอื่น ๆ': {th}"
    assert not CYR.search(th), f"кириллица в 🇹🇭: {th}"
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
    """msg_works_logged — тот же класс: список работ в обоих блоках, 🇹🇭 чистый."""
    msg = S.msg_works_logged("NMAX 4255", 29275, ["замена моторного масла", "воздушный фильтр"])
    th, ru = _th_ru_lines(msg)
    assert "เปลี่ยนน้ำมันเครื่อง" in th and "ไส้กรองอากาศ" in th, th
    assert not CYR.search(th), f"кириллица в 🇹🇭: {th}"
    assert "29275" in th and "29275" in ru, "км в обоих блоках"
    assert "замена моторного масла" in ru and "воздушный фильтр" in ru


def test_th_dedup_and_unknown():
    """Хелпер: дедуп переводов (две неизвестные → один 'งานอื่น ๆ'; дубль работы → один лейбл)."""
    s = S._works_th_str(["рамка номера", "покраска зеркала", "замена моторного масла",
                         "моторное масло"])
    assert s.count("งานอื่น ๆ") == 1, s
    assert s.count("เปลี่ยนน้ำมันเครื่อง") == 1, s


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов тайского списка работ (фикс row9)")
