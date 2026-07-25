"""Моки ПАКЕТ А — двуязычие RU-основа→TH-перевод + запрет «автомобиль» + аудитор-длина.
Сеть/LLM замоканы. Проверяет: helper RU→TH несёт конкретику, оба блока, no-car фильтр,
контракт пина (RU→двуязычный), аудитор флагает короткий TH и «автомобиль»."""
import os, sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S
import auditor as A

class FakeClaude:
    """quick(TRANSLATE_RU_TH, ru) → тайский, сохраняя числа/латиницу из ru (имитация перевода без потерь).
    Если в ru есть 'автомобиль' — вернём รถยนต์ (проверяем, что _no_car это вычистит)."""
    def quick(self, system, text, max_tokens=300, **kw):
        assert system == S.TRANSLATE_RU_TH, "перевод должен идти через TRANSLATE_RU_TH"
        nums = " ".join(re.findall(r"\d+", text))
        lat = " ".join(re.findall(r"[A-Za-z]{2,}", text))
        car = " รถยนต์" if ("автомобил" in text.lower() or "машин" in text.lower()) else ""
        return f"แจ้งเตือน รายละเอียด {nums} {lat}{car} ครับ".strip()

C = FakeClaude()

def test_translate_carries_detail():
    ru = "Пым, на фото повреждения: трещина облицовки, пробег 20316 на байке XMAX — посмотри по депозиту"
    th = S._translate_ru_th(C, ru)
    assert re.search(r"[฀-๿]", th), "должен быть тайский текст"
    assert not re.search(r"[а-яА-Я]", th), "в тайском НЕ должно быть кириллицы"
    assert "20316" in th, "число (конкретика) должно сохраниться в переводе"
    assert "XMAX" in th, "латинское имя байка сохраняется"

def test_both_blocks_present():
    msg = S.bilingual_from_ru(C, "Пробег 12345 принят на байке NMAX")
    assert "🇹🇭" in msg and "🇷🇺" in msg, "оба блока обязаны быть"
    assert S._SEP in msg, "разделитель между блоками"
    # тайский блок раньше русского (TH первым)
    assert msg.index("🇹🇭") < msg.index("🇷🇺")

def test_no_car_ru_side():
    # RU-сторона: «автомобиль/машину» в основе → байк (чистится до перевода и в 🇷🇺-блоке)
    msg = S.bilingual_from_ru(C, "Этот автомобиль на сервисе, проверь машину")
    assert "автомобил" not in msg.lower() and "машину" not in msg.lower(), "RU: авто/машина→байк"
    assert "байк" in msg.lower()

def test_no_car_th_side():
    # TH-сторона: LLM-переводчик СОСКОЛЬЗНУЛ на รถยนต์ → _translate_ru_th должен вычистить в รถมอเตอร์ไซค์
    class SlipClaude:
        def quick(self, system, text, max_tokens=300, **kw): return "รถยนต์ คันนี้เสียหาย ครับ"
    th = S._translate_ru_th(SlipClaude(), "байк повреждён")
    assert "รถยนต์" not in th, "TH: รถยนต์ должно быть заменено"
    assert "รถมอเตอร์ไซค์" in th

def test_pin_contract_ru_to_bilingual():
    # старый двуязычный пин на входе → берём RU-основу, пересобираем
    raw = "⚠️ 🇹🇭 generic\n🇷🇺 ДТП, разбит фонарь, пробег 5000"
    pin = S.bilingual_pin(C, raw)
    assert "🇹🇭" in pin and "🇷🇺" in pin
    assert "5000" in pin, "деталь из RU сохранена и в TH (число)"
    # чистый RU на входе (новый контракт) тоже ок
    pin2 = S.bilingual_pin(C, "Просрочка ТО масла, байк CB300, пробег 36500")
    assert "🇹🇭" in pin2 and "36500" in pin2

def test_translate_fallback_no_cyrillic():
    class Empty:
        def quick(self, *a, **k): return ""   # перевод не удался
    th = S._translate_ru_th(Empty(), "что-то важное")
    assert re.search(r"[฀-๿]", th), "фоллбэк = тайский указатель"
    assert not re.search(r"[а-яА-Я]", th), "фоллбэк без кириллицы (аудитор не должен флагать)"

# ---- аудитор ----
def test_auditor_flags_short_thai():
    aud = A.Auditor.__new__(A.Auditor)   # без __init__
    aud.bridge = type("B", (), {"audit_log": lambda *a, **k: None})()
    ru = "🇷🇺 Подробное описание повреждения облицовки под сиденьем, потёртость, если возврат посмотри по депозиту внимательно"
    short = "🇹🇭 ดูรูป\n" + S._SEP + "\n" + ru
    r = aud.check_response_text(answer=short, bilingual=True)
    assert r["verdict"] == "style_issue", r
    assert "короче" in r["detail"], r

def test_auditor_flags_car_word():
    aud = A.Auditor.__new__(A.Auditor)
    r = aud.check_response_text(answer="🇹🇭 รถยนต์ คันนี้\n" + S._SEP + "\n🇷🇺 Этот автомобиль на сервисе", bilingual=True)
    assert r["verdict"] == "style_issue" and ("автомоб" in r["detail"] or "รถยนต์" in r["detail"]), r

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов двуязычия/языка")
