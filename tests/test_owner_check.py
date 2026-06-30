"""Единый owner-гейт is_owner_user (двухаккаунтный владелец). Фикс класса: строгий ==id молча
отвергал второй аккаунт (баг /pin_info_all 29.06 — @turbophuket1 id=6879003264)."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

class U:
    def __init__(self, uid, uname=None): self.id = uid; self.username = uname
class M:
    def __init__(self, u): self.from_user = u

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

print("OWNER_IDS =", S.OWNER_IDS)
res.append(ok(S.OWNER_IDS == {504608015, 6879003264, 5466425480}, "OWNER_IDS = ТРИ аккаунта владельца"))

print("is_owner_user — по id:")
res.append(ok(S.is_owner_user(U(6879003264)) is True, "id 6879003264 (@turbophuket1) → владелец"))
res.append(ok(S.is_owner_user(U(504608015)) is True, "id 504608015 (HQ-личный, без username) → владелец"))
res.append(ok(S.is_owner_user(U(5466425480)) is True, "id 5466425480 (@samhold, 3-й — добавлен 30.06) → владелец"))

print("is_owner_user — по username (id чужой):")
res.append(ok(S.is_owner_user(U(999, "turbophuket1")) is True, "username turbophuket1 → владелец"))
res.append(ok(S.is_owner_user(U(999, "TurboPhuket")) is True, "username регистр-независим → владелец"))

print("is_owner_user — чужие:")
res.append(ok(S.is_owner_user(U(999)) is False, "чужой id без username → НЕ владелец"))
res.append(ok(S.is_owner_user(U(999, "randomguy")) is False, "чужой id + чужой username → НЕ владелец"))
res.append(ok(S.is_owner_user(None) is False, "None → НЕ владелец (без падения)"))

print("_is_owner(msg) делегирует в is_owner_user:")
res.append(ok(S._is_owner(M(U(6879003264))) is True, "msg от 6879003264 → владелец (раньше username-only давал False)"))
res.append(ok(S._is_owner(M(U(999, "turbophuket"))) is True, "msg по username → владелец"))
res.append(ok(S._is_owner(M(U(999))) is False, "msg чужой → НЕ владелец"))
res.append(ok(S._is_owner(M(None)) is False, "msg без from_user → НЕ владелец (без падения)"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
