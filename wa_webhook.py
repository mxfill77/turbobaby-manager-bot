#!/usr/bin/env python3
"""WA-0: WhatsApp Cloud API webhook receiver (thin transit, VPS).

Isolation §4: NO content logic here — client text is generated only on PC.
This module receives WA events, validates them, normalises to a common schema,
and enqueues to a local SQLite wa_queue.db for the PC orchestrator to consume.
It NEVER sends any message back to WhatsApp.

Endpoints:
  GET  /wa-webhook  — Meta hub.verify-token handshake (→ echo challenge or 403)
  POST /wa-webhook  — Incoming events, verified by X-Hub-Signature-256 HMAC

Environment (.env):
  WA_VERIFY_TOKEN   — token agreed with Meta developer portal (required)
  WA_APP_SECRET     — app secret for HMAC-SHA256 signature verification (required)
  WA_PHONE_NUMBER_ID — our WA phone-number-id (used for echo detection)
  WA_WEBHOOK_PORT   — HTTP listen port (default: 8765)
  WA_QUEUE_DB       — path to SQLite queue file (default: wa_queue.db next to this file)

Queue schema (wa_inbox table in wa_queue.db):
  id, ts_queued, channel, from_number, name, msg_type, text, media_id,
  ts_msg, echo, history, status, raw (JSON), wamid

Usage (standalone service):
  venv/bin/python3 wa_webhook.py
"""

import os
import sys
import hmac
import hashlib
import json
import sqlite3
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("wa_webhook")

# Suppress noisy default BaseHTTPRequestHandler logging (we log ourselves)
logging.getLogger("http.server").setLevel(logging.WARNING)


# ─── env (loaded lazily so tests can patch os.environ before import side-effects) ─────

def _env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass
    return {
        "verify_token": os.environ.get("WA_VERIFY_TOKEN", ""),
        "app_secret":   os.environ.get("WA_APP_SECRET", ""),
        "phone_id":     os.environ.get("WA_PHONE_NUMBER_ID", ""),
        "port":         int(os.environ.get("WA_WEBHOOK_PORT", "8765")),
        "queue_db":     os.environ.get("WA_QUEUE_DB", os.path.join(ROOT, "wa_queue.db")),
    }


# ─── SQLite queue ──────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_inbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_queued   INTEGER NOT NULL,
    channel     TEXT    NOT NULL DEFAULT 'wa',
    from_number TEXT,
    name        TEXT,
    msg_type    TEXT,
    text        TEXT,
    media_id    TEXT,
    ts_msg      INTEGER,
    echo        INTEGER NOT NULL DEFAULT 0,
    history     INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'new',
    raw         TEXT,
    wamid       TEXT
);
CREATE INDEX IF NOT EXISTS idx_wa_status ON wa_inbox(status, ts_queued);
"""

# UNIQUE on wamid deduplicates retried deliveries; NULL wamid (status updates w/o id) not deduplicated.
_WAMID_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_wamid ON wa_inbox(wamid)"


class WAQueueDB:
    """Thread-safe SQLite queue for incoming WA events."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)

    def _init_db(self):
        with self._conn() as conn:
            for stmt in _SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            try:
                conn.execute(_WAMID_INDEX)
            except sqlite3.OperationalError:
                pass  # index already exists
            conn.commit()

    def enqueue(self, events: list) -> int:
        """Insert normalised events. Returns number actually inserted (dupes skipped)."""
        now = int(time.time())
        inserted = 0
        with self._lock:
            with self._conn() as conn:
                for ev in events:
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO wa_inbox
                               (ts_queued, channel, from_number, name, msg_type, text, media_id,
                                ts_msg, echo, history, status, raw, wamid)
                               VALUES (?,?,?,?,?,?,?,?,?,?,'new',?,?)""",
                            (
                                now,
                                ev.get("channel", "wa"),
                                ev.get("from"),
                                ev.get("name") or "",
                                ev.get("type"),
                                ev.get("text"),
                                ev.get("media_id"),
                                ev.get("ts"),
                                1 if ev.get("echo") else 0,
                                1 if ev.get("history") else 0,
                                json.dumps(ev.get("raw"), ensure_ascii=False),
                                ev.get("wamid"),
                            ),
                        )
                        inserted += conn.execute("SELECT changes()").fetchone()[0]
                    except Exception as e:
                        log.warning("wa_queue enqueue error: %s", e)
                conn.commit()
        return inserted

    def count_pending(self) -> int:
        """Count rows with status='new' (pending for PC)."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM wa_inbox WHERE status='new'"
            ).fetchone()[0]


# ─── normalisation ────────────────────────────────────────────────────────────────────

# WA Cloud API media types that carry a media_id under the type-named key
_MEDIA_TYPES = {"image", "audio", "video", "document", "sticker", "voice"}

# Messages older than this many seconds from now are classified as history-sync
_HISTORY_THRESHOLD_SECS = 86400  # 24 hours


def normalize_wa_payload(payload: dict, our_phone_number: str = "") -> list:
    """Extract and normalise a WA Cloud API webhook payload.

    Returns a list of normalised event dicts (one per message or status entry).
    Incoming messages, status updates, and history-sync events all flow through here.

    Each output dict has:
      channel, from, name, type, text, media_id, ts, echo, history, wamid, raw
    """
    events = []
    now = int(time.time())

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            our_display = metadata.get("display_phone_number", our_phone_number)

            # Build contact name lookup: wa_id → display name
            contacts = {
                c["wa_id"]: c.get("profile", {}).get("name", "")
                for c in value.get("contacts", [])
                if isinstance(c, dict) and c.get("wa_id")
            }

            # ── incoming messages ──────────────────────────────────────────
            for msg in value.get("messages", []):
                if not isinstance(msg, dict):
                    continue

                sender = msg.get("from", "")
                msg_type = msg.get("type", "")
                ts = int(msg.get("timestamp") or 0)
                wamid = msg.get("id")

                text = None
                media_id = None
                if msg_type == "text":
                    text = (msg.get("text") or {}).get("body")
                elif msg_type in _MEDIA_TYPES:
                    media_id = (msg.get(msg_type) or {}).get("id")
                elif msg_type == "location":
                    loc = msg.get("location") or {}
                    text = f"{loc.get('latitude')},{loc.get('longitude')}"
                elif msg_type == "interactive":
                    intr = msg.get("interactive") or {}
                    kind = intr.get("type", "")
                    if kind == "button_reply":
                        text = (intr.get("button_reply") or {}).get("title")
                    elif kind == "list_reply":
                        text = (intr.get("list_reply") or {}).get("title")

                # echo: message sent FROM our own business phone (bounced back)
                echo = bool(our_display and sender == our_display)

                # history-sync: timestamp significantly in the past
                history = ts > 0 and (now - ts) > _HISTORY_THRESHOLD_SECS

                events.append({
                    "channel":  "wa",
                    "from":     sender,
                    "name":     contacts.get(sender, ""),
                    "type":     msg_type,
                    "text":     text,
                    "media_id": media_id,
                    "ts":       ts,
                    "echo":     echo,
                    "history":  history,
                    "wamid":    wamid,
                    "raw":      msg,
                })

            # ── status updates (delivery/read receipts for our outbound msgs) ──
            for status in value.get("statuses", []):
                if not isinstance(status, dict):
                    continue
                ts = int(status.get("timestamp") or 0)
                events.append({
                    "channel":  "wa",
                    "from":     status.get("recipient_id", ""),
                    "name":     "",
                    "type":     "status",
                    "text":     status.get("status"),  # sent/delivered/read/failed
                    "media_id": None,
                    "ts":       ts,
                    "echo":     True,   # statuses are receipts for messages WE sent
                    "history":  ts > 0 and (now - ts) > _HISTORY_THRESHOLD_SECS,
                    "wamid":    status.get("id"),
                    "raw":      status,
                })

    return events


# ─── HMAC signature verification ─────────────────────────────────────────────────────

def verify_signature(body: bytes, signature_header: str, app_secret: str) -> bool:
    """Return True if X-Hub-Signature-256 header matches body HMAC.

    If app_secret is empty the check is skipped (dev/test mode) and True is returned.
    The signature_header format is 'sha256=<hex>'.
    """
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ─── HTTP handler ─────────────────────────────────────────────────────────────────────

class WAWebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for /wa-webhook.

    Class attributes set before starting the server:
      verify_token  str
      app_secret    str
      phone_id      str   (WA phone number id — used to resolve our own phone for echo detection)
      our_phone     str   (display_phone_number, resolved lazily from metadata)
      db            WAQueueDB
    """

    verify_token: str = ""
    app_secret: str = ""
    our_phone: str = ""
    db: WAQueueDB = None

    # Socket r/w timeout per request — a slow/stalled client closes the connection
    # rather than holding the thread indefinitely (incident 15.07: TCP open, HTTP hung).
    timeout = 10

    def log_message(self, fmt, *args):
        log.debug("WA HTTP: " + fmt, *args)

    def _send(self, code: int, body: str = "", content_type: str = "text/plain"):
        enc = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    # GET /wa-webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/wa-webhook":
            self._send(404, "Not found")
            return

        params = parse_qs(parsed.query)
        mode      = (params.get("hub.mode")         or [""])[0]
        token     = (params.get("hub.verify_token") or [""])[0]
        challenge = (params.get("hub.challenge")    or [""])[0]

        if mode == "subscribe" and token == self.verify_token:
            log.info("WA verify-token handshake OK → challenge sent")
            self._send(200, challenge)
        else:
            log.warning("WA verify-token handshake FAILED mode=%r token=%r", mode, token)
            self._send(403, "Forbidden")

    # POST /wa-webhook — incoming events
    def do_POST(self):
        if urlparse(self.path).path != "/wa-webhook":
            self._send(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        sig = self.headers.get("X-Hub-Signature-256", "")

        if not verify_signature(body, sig, self.app_secret):
            log.warning("WA POST: bad/missing signature — rejected")
            self._send(403, "Forbidden")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            log.warning("WA POST: JSON parse error: %s", e)
            self._send(400, "Bad request")
            return

        # Respond 200 immediately and flush — Meta retries if we exceed ~5s.
        # Processing (normalise + enqueue) happens AFTER the flush in this thread;
        # ThreadingHTTPServer gives each request its own thread, so a slow enqueue
        # never blocks other incoming connections (incident 15.07).
        self._send(200, "ok")
        try:
            self.wfile.flush()
        except Exception:
            pass

        try:
            events = normalize_wa_payload(payload, our_phone_number=self.our_phone)
            if events:
                n = self.db.enqueue(events) if self.db else 0
                log.info("WA POST: %d events, %d enqueued (dupes skipped)", len(events), n)
            else:
                log.debug("WA POST: payload contained 0 normalised events")
        except Exception as e:
            log.error("WA POST: processing error: %s", e, exc_info=True)


# ─── server bootstrap ─────────────────────────────────────────────────────────────────

def make_server(env: dict) -> ThreadingHTTPServer:
    """Configure and return a ThreadingHTTPServer with WAWebhookHandler.

    ThreadingHTTPServer spawns a daemon thread per request so a slow/hung
    client or a slow db.enqueue() never blocks other incoming connections.
    """
    db = WAQueueDB(env["queue_db"])

    class _Handler(WAWebhookHandler):
        pass

    _Handler.verify_token = env["verify_token"]
    _Handler.app_secret   = env["app_secret"]
    _Handler.our_phone    = env["phone_id"]
    _Handler.db           = db

    server = ThreadingHTTPServer(("0.0.0.0", env["port"]), _Handler)
    server.daemon_threads = True
    return server


def main():
    env = _env()
    if not env["verify_token"]:
        log.error("WA_VERIFY_TOKEN not set — cannot start webhook (set in .env)")
        sys.exit(1)
    if not env["app_secret"]:
        log.warning("WA_APP_SECRET not set — HMAC signature check DISABLED (dev mode only)")

    server = make_server(env)
    log.info(
        "WA webhook listening on port %d  db=%s",
        env["port"], env["queue_db"],
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("WA webhook stopped")


if __name__ == "__main__":
    main()
