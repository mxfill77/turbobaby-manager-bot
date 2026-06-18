"""Моки ЧАСТЬ A: чтение интервалов ТО из KB + фоллбэк + кэш."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S

# реальный фрагмент knowledge_base с блоком (как в docs)
KB_TEXT = """
### Регламенты ТО
  | Воздушный фильтр (кол.L) | 20 000 км | ВСЕ |
  ```json SERVICE_INTERVALS
  {
    "oil": {"scooter": 4000, "moto": 5000},
    "gear": {"scooter": 4000, "moto": null},
    "abs": 10000,
    "airfilter": 20000,
    "oilfilter": {"ref": 20000, "note": "столбца нет"},
    "scooter_keywords": ["nmax", "xmax", "adv", "forza", "pcx", "click"],
    "moto_default": 5000
  }
  ```
после блока другой текст с { фигурными } скобками — не должен мешать.
"""

class KBBridge:
    def __init__(self, ok=True, text=KB_TEXT): self.ok=ok; self.text=text; self.calls=0
    def _call(self, action, **kw):
        self.calls += 1
        return {"ok": self.ok, "text": self.text} if self.ok else {"ok": False, "error": "read_failed"}

def reset(): S._SVC_INTERVALS_CACHE["data"]=None; S._SVC_INTERVALS_CACHE["ts"]=0.0
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
res=[]

# 1) парсер достаёт блок (вложенные {} не ломают)
reset()
d = S._parse_service_intervals_block(KB_TEXT)
print("парсер блока SERVICE_INTERVALS:")
res.append(ok(d is not None and d.get("abs")==10000 and d["oil"]["scooter"]==4000, "блок распознан, вложенность ок"))
res.append(ok(d["gear"]["moto"] is None, "gear.moto = null → None"))

# 2) значения из KB по типам
reset(); br=KBBridge()
print("значения из книги знаний:")
res.append(ok(S._service_interval("oil","NMAX 7530",br)==4000, "oil скутер NMAX = 4000"))
res.append(ok(S._service_interval("oil","CB 650R",br)==5000, "oil мото CB = 5000"))
res.append(ok(S._service_interval("oil","XADV 2478",br)==5000, "oil XADV = 5000 (мото)"))
res.append(ok(S._service_interval("gear","NMAX 7530",br)==4000, "gear скутер = 4000"))
res.append(ok(S._service_interval("gear","CB 650R",br) is None, "gear мото = None (не трекать)"))
res.append(ok(S._service_interval("gear","XADV 2478",br) is None, "gear XADV = None (мото)"))
res.append(ok(S._service_interval("abs","что угодно",br)==10000, "abs = 10000 все"))
res.append(ok(S._service_interval("airfilter","что угодно",br)==20000, "возд.фильтр = 20000 все"))

# 3) КЭШ: повторные вызовы не дёргают read_doc (1 раз на загрузку)
print("кэш:")
res.append(ok(br.calls==1, f"read_doc вызван 1 раз на 8 запросов (calls={br.calls})"))

# 4) ФОЛЛБЭК: read_doc падает → те же числа из хардкода
reset(); bad=KBBridge(ok=False)
print("фоллбэк при обрыве read_doc:")
res.append(ok(S._service_interval("oil","NMAX 7530",bad)==4000, "oil скутер = 4000 (фоллбэк)"))
res.append(ok(S._service_interval("oil","CB 650R",bad)==5000, "oil мото = 5000 (фоллбэк)"))
res.append(ok(S._service_interval("abs","x",bad)==10000, "abs = 10000 (фоллбэк)"))
res.append(ok(S._service_interval("airfilter","x",bad)==20000, "возд.фильтр = 20000 (фоллбэк)"))
res.append(ok(S._service_interval("gear","CB 650R",bad) is None, "gear мото = None (фоллбэк)"))

# 5) кривой блок → фоллбэк
reset(); junk=KBBridge(text="нет блока тут")
res.append(ok(S._service_interval("oil","NMAX 7530",junk)==4000, "нет блока → фоллбэк 4000"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
