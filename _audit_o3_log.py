import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()

cc_entry = (
    "DONE 2026-07-14 10:10 UTC: [куратор 357 шаг 1] Аудит O3 08-14.07. "
    "(1) 5 событий тайской команды в Обслуживании — 3×return "
    "(10.07: X MAX 300 4724, NMAX 155 5960; 14.07: NINJA 400 6334) "
    "+ 1×intake + 1×handover (14.07 NINJA 400 6334); "
    "12 repair, 32 photo, 79 сообщений. "
    "(2) Карточки во Входящих: 1 — ВЫДАЧА NINJA 400 14.07 09:38, "
    "бронь не найдена, помечено на ручную обработку. "
    "Кнопки в логе НЕТ. Row 1270 появился в CRM — вручную через лист. "
    "ПРИЁМ-карточки не генерировались (все 3 return — идемпотентный путь). "
    "(3) CRM: NINJA 400 row 1270 В аренде (14-17 Jul); "
    "NMAX 155 5960 row 703 (Sostrand, due 11.07) ещё В аренде — "
    "return 10.07 нашёл старый закрытый row 1204 (2025) вместо текущей строки. "
    "(4) Вердикт: круг живёт базово (команда пишет ежедневно, события парсятся); "
    "баг: closing_get возвращает старую завершённую строку вместо актуальной аренды. "
    "Хвост: row 703 открыт."
)

pulse_text = (
    "2026-07-14 10:10 UTC | 🟡 | Аудит O3 08-14.07 готов: "
    "5 return/handover, 1 ВЫДАЧА-карточка, CRM-баг (closing_get старый row) — "
    "NMAX 155 row 703 не закрыт | ничего не жду | детали→cc_log DONE 14.07 аудит O3"
)

r = bc._call("read_doc", name="cc_log")
if not r.get('ok'):
    print('ERROR read cc_log:', r)
    sys.exit(1)
content = r.get('text', r.get('content', ''))
print(f'cc_log read ok, length={len(content)}')

lines = content.split('\n')
insert_pos = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped and all(c == '═' for c in stripped) and i > 0:
        insert_pos = i + 1
        break

if insert_pos == 0:
    new_content = cc_entry + '\n\n' + content
else:
    new_content = '\n'.join(lines[:insert_pos]) + '\n' + cc_entry + '\n' + '\n'.join(lines[insert_pos:])

wr = bc.write_doc(text=new_content, name='cc_log')
print('cc_log write:', wr.get('ok'), wr.get('error', ''))

pr = bc.write_doc(text=pulse_text, name='pulse')
print('pulse write:', pr.get('ok'), pr.get('error', ''))
