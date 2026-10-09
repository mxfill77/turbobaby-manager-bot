# -*- coding: utf-8 -*-
"""Минимальные PDF живого формата для тестов (K3-FIX F4, 09.10.2026): после проверки скелета PDF перед дверью
(`wa_agent_attach.pdf_shape`) фикстура «%PDF-1.4 какие-то байты» перестала быть PDF и уходить не обязана. Сборка — без
библиотек, смещения в таблице ссылок точные (как `minimal_pdf` стенда К3: stand/gen_data.py:28-56).

    classic(label)      — PDF 1.4: таблица «xref», одна страница; label — текст страницы и комментарий (разные label —
                          разные байты и sha256, как у прежних фикстур);
    xref_stream(label)  — PDF 1.5: поток ссылок /XRef (+ предиктор PNG) и поток объектов /ObjStm (каталог и страницы сжаты);
    incremental(label)  — classic + раздел обновления с /Prev (цепочка таблиц ссылок).
Не тест: в гейт (`tests/test_*.py`) не попадает."""
import zlib


def _esc(b):
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _objs(label):
    stream = b"BT /F1 12 Tf 72 770 Td (" + _esc(label) + b") Tj ET\n"
    return [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
    ]


def classic(label=b"K3 test contract"):
    if isinstance(label, str):
        label = label.encode("utf-8")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n%" + label.replace(b"\n", b" ") + b"\n")
    offs = []
    objs = _objs(label)
    for n, body in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def xref_stream(label=b"K3 xref stream", predictor=True):
    if isinstance(label, str):
        label = label.encode("utf-8")
    objs = _objs(label)
    inner = list(enumerate(objs[:4], 1))                    # 1..4 — в потоке объектов 6
    body, offs = b"", []
    for _n, ob in inner:
        offs.append(len(body))
        body += ob + b"\n"
    head = b" ".join(b"%d %d" % (n, o) for (n, _ob), o in zip(inner, offs)) + b"\n"
    stm = zlib.compress(head + body)
    out = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n%" + label.replace(b"\n", b" ") + b"\n")
    pos = {5: len(out)}
    out += b"5 0 obj\n" + objs[4] + b"\nendobj\n"
    pos[6] = len(out)
    out += (b"6 0 obj\n<< /Type /ObjStm /N 4 /First %d /Filter /FlateDecode /Length %d >>\nstream\n"
            % (len(head), len(stm)) + stm + b"\nendstream\nendobj\n")
    pos[7] = len(out)
    rows = [(0, 0, 65535)] + [(2, 6, i) for i in range(4)] + [(1, pos[5], 0), (1, pos[6], 0), (1, pos[7], 0)]
    raw = b"".join(bytes([t]) + f2.to_bytes(4, "big") + f3.to_bytes(2, "big") for t, f2, f3 in rows)
    parms = b""
    if predictor:                                           # PNG Up: строка = 1 байт типа + 7 байт записи
        data, prev = bytearray(), bytes(7)
        for k in range(0, len(raw), 7):
            r = raw[k:k + 7]
            data += b"\x02" + bytes((r[i] - prev[i]) & 255 for i in range(7))
            prev = r
        raw = bytes(data)
        parms = b" /DecodeParms << /Columns 7 /Predictor 12 >>"
    comp = zlib.compress(raw)
    out += (b"7 0 obj\n<< /Type /XRef /Size 8 /W [1 4 2] /Root 1 0 R /Filter /FlateDecode%s /Length %d >>\nstream\n"
            % (parms, len(comp)) + comp + b"\nendstream\nendobj\n")
    out += b"startxref\n%d\n%%%%EOF\n" % pos[7]
    return bytes(out)


def incremental(label=b"K3 incremental"):
    """classic + раздел обновления: объект 2 (корень дерева) переписан, новая таблица с /Prev на прежнюю."""
    base = bytearray(classic(label))
    old_xref = int(bytes(base).rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    off = len(base)
    base += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 /K3 (update) >>\nendobj\n"
    xref = len(base)
    base += b"xref\n0 1\n0000000000 65535 f \n2 1\n%010d 00000 n \n" % off
    base += b"trailer\n<< /Size 6 /Root 1 0 R /Prev %d >>\nstartxref\n%d\n%%%%EOF\n" % (old_xref, xref)
    return bytes(base)
