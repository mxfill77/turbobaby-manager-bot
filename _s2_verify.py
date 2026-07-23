"""Read-only контроль: правки в KB_MASTER/roadmap_master на местах."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
m = c._call("read_doc", id="1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc").get("text", "")
rm = c._call("read_doc", name="roadmap_master").get("text", "")
checks = [
    ("§3 ступень 2", "ОРКЕСТРАТОР СТУПЕНЬ 2 (O4) СОБРАНА ЦЕЛИКОМ" in m),
    ("§3 TurboControl", "TurboControl" in m),
    ("§3 доктрина", "ДОКТРИНА ПОДТВЕРЖДЕНИЙ (02.07, ea92795" in m),
    ("§4 [O4] собрана", "[O4] Ступень 2 — ✅ СОБРАНА ЦЕЛИКОМ" in m),
    ("§4 старый статус убран", "В ПРОЕКТИРОВАНИИ (план в KB_review 03.07" not in m),
    ("§7 обкатка ст2", "ОБКАТКА СТУПЕНИ 2 O4" in m),
    ("§7 старый хвост убран", "O4 ДЕКОМПОЗЕР (ступень 2 оркестратора) — после обкатки O3" not in m),
    ("§3 СРЕДА-блок цел", "СРЕДА «РУЛЮ С ТЕЛЕФОНА, ВСЁ В МОЗГ»:" in m),
    ("roadmap блок 03.07", "АКТУАЛИЗАЦИЯ 03.07.2026 (ступень 2 O4 собрана) — ЧИТАТЬ ПЕРВЫМ" in rm),
    ("roadmap 29.06 сохранён", "АКТУАЛИЗАЦИЯ 29.06.2026 (ревизия, веха 4255 закрыта)" in rm),
    ("roadmap хвост закрыт", "Хвост «O4 декомпозер» из списка 29.06 ЗАКРЫТ" in rm),
]
for name, ok in checks:
    print(("OK " if ok else "FAIL") + " | " + name)
print("ИТОГ:", "все OK" if all(ok for _, ok in checks) else "ЕСТЬ FAIL")
