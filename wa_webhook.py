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
  WA_VERIFY_TOKEN     — token agreed with Meta developer portal (required)
  WA_APP_SECRET       — app secret for HMAC-SHA256 signature verification (required)
  WA_PHONE_NUMBER_ID  — our WA phone-number-id (used for echo detection)
  WA_WEBHOOK_PORT     — HTTP listen port (default: 8765)
  WA_BIND_HOST        — listen address (default: 127.0.0.1 — loopback only, see below)
  WA_QUEUE_DB         — path to SQLite queue file (default: wa_queue.db next to this file)
  WA_360_SANDBOX_KEY  — 360dialog sandbox API key (D360-API-KEY header)
  WA_D360_PATH_SECRET — random hex secret embedded in the 360dialog webhook path
  WA_PULL_SECRET      — random hex secret in the PC pull/ack path (absent → those doors 404)

Endpoints:
  GET  /wa-webhook                            — Meta hub.verify-token handshake
  POST /wa-webhook                            — Meta Cloud API v2 (HMAC-verified)
  POST /wa-webhook/d360/<WA_D360_PATH_SECRET> — 360dialog v1 (auth by path secret, no HMAC)
  GET  /wa-queue/pull/<WA_PULL_SECRET>        — PC takes up to 20 undelivered rows (leases them)
  POST /wa-queue/ack/<WA_PULL_SECRET>         — PC confirms it processed the given ids

BIND IS LOOPBACK BY DEFAULT (06.09.2026). TLS and the outside world are Caddy's job; the
webhook itself has no reason to be reachable on a public interface. Direction of doubt is
INWARD: an empty/blank WA_BIND_HOST falls back to 127.0.0.1, never to 0.0.0.0 — a typo in
.env must not silently publish the port.

Queue schema (wa_inbox table in wa_queue.db):
  id, ts_queued, channel, from_number, name, msg_type, text, media_id,
  ts_msg, echo, history, status, raw (JSON), wamid,
  source, delivered_at, acked_at   ← added 06.09.2026 for the PC pull/ack doors

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
        "verify_token":     os.environ.get("WA_VERIFY_TOKEN", ""),
        "app_secret":       os.environ.get("WA_APP_SECRET", ""),
        "phone_id":         os.environ.get("WA_PHONE_NUMBER_ID", ""),
        "port":             int(os.environ.get("WA_WEBHOOK_PORT", "8765")),
        "bind_host":        bind_host(os.environ.get("WA_BIND_HOST")),
        "queue_db":         os.environ.get("WA_QUEUE_DB", os.path.join(ROOT, "wa_queue.db")),
        "d360_key":         os.environ.get("WA_360_SANDBOX_KEY", ""),
        "d360_path_secret": os.environ.get("WA_D360_PATH_SECRET", ""),
        "pull_secret":      os.environ.get("WA_PULL_SECRET", ""),
    }


DEFAULT_BIND = "127.0.0.1"


def bind_host(raw) -> str:
    """Resolve the listen address. Unset / blank / whitespace → loopback.

    Deliberately NOT a passthrough: the only way to publish this port is to name a host
    explicitly. A missing or empty variable is the commonest accident, and its cost here is
    an open port on the public interface — so that case resolves inward, not outward.
    """
    host = (raw or "").strip()
    return host or DEFAULT_BIND


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

# Columns added after the table already existed in production (06.09.2026). Adding them is
# the only migration this file performs: ALTER TABLE ADD COLUMN never touches existing rows,
# so a live wa_queue.db keeps every byte it had. Pre-migration rows get source='' — that is
# read as "not recorded", NOT guessed into 'meta' or 'd360'.
_ADDED_COLUMNS = (
    ("source",       "TEXT"),
    ("delivered_at", "INTEGER"),
    ("acked_at",     "INTEGER"),
)

_PULL_INDEX = "CREATE INDEX IF NOT EXISTS idx_wa_pull ON wa_inbox(acked_at, delivered_at, id)"

# How long a pulled row stays leased to the PC before it becomes available again.
LEASE_SECS = 300     # 5 minutes — PC took it and went silent → someone must get it again
PULL_LIMIT = 20      # rows handed out per pull


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
            have = {r[1] for r in conn.execute("PRAGMA table_info(wa_inbox)")}
            for col, decl in _ADDED_COLUMNS:
                if col not in have:
                    conn.execute("ALTER TABLE wa_inbox ADD COLUMN " + col + " " + decl)
            conn.execute(_PULL_INDEX)
            conn.commit()

    def enqueue(self, events: list, source: str = "") -> int:
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
                                ts_msg, echo, history, status, raw, wamid, source)
                               VALUES (?,?,?,?,?,?,?,?,?,?,'new',?,?,?)""",
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
                                ev.get("source") or source or "",
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

    # ── PC pull/ack doors (06.09.2026) ────────────────────────────────────────
    #
    # NOTHING IS EVER DELETED HERE. A row's whole life is three timestamps: it arrives
    # (ts_queued), it is handed to the PC (delivered_at), the PC says it dealt with it
    # (acked_at). Both later columns only ever go from NULL to a number; no branch in this
    # class issues DELETE. Losing a client's message because a lease bookkeeping bug ate the
    # row would be the one unrecoverable failure of a transit queue, so the queue is
    # append-and-stamp only, and it grows — that is the deliberate trade.
    #
    # LEASE, NOT CLAIM. delivered_at is a *lease*: if the PC takes rows and dies, after
    # LEASE_SECS they become available again. Handing the same row out twice is a nuisance
    # (the PC dedupes by id); handing it out never is a lost client.

    def pull(self, limit: int = PULL_LIMIT, lease_secs: int = LEASE_SECS, now: int = None) -> list:
        """Hand out up to `limit` rows the PC has not acked and whose lease has expired.

        Selecting and stamping happen under one lock and one transaction, so two concurrent
        pulls cannot be handed the same row.
        """
        now = int(now if now is not None else time.time())
        cutoff = now - int(lease_secs)
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT id, from_number, name, msg_type, text, ts_msg, source
                         FROM wa_inbox
                        WHERE acked_at IS NULL
                          AND (delivered_at IS NULL OR delivered_at < ?)
                        ORDER BY id
                        LIMIT ?""",
                    (cutoff, int(limit)),
                ).fetchall()
                items = [
                    {
                        "id":     r[0],
                        "from":   r[1] or "",
                        "name":   r[2] or "",
                        "type":   r[3] or "",
                        "text":   r[4],
                        "ts":     r[5] or 0,
                        "source": r[6] or "",
                    }
                    for r in rows
                ]
                if items:
                    conn.executemany(
                        "UPDATE wa_inbox SET delivered_at=? WHERE id=?",
                        [(now, it["id"]) for it in items],
                    )
                conn.commit()
        return items

    def ack(self, ids, now: int = None) -> int:
        """Mark the given ids as processed. Returns how many rows actually changed.

        Idempotent: an id already acked, or an id that does not exist, changes nothing and is
        not an error — the PC may retry an ack whose response it never saw.
        """
        now = int(now if now is not None else time.time())
        clean = []
        for i in (ids or []):
            try:
                clean.append(int(i))
            except (TypeError, ValueError):
                continue          # junk id is ignored, it cannot ack anything
        if not clean:
            return 0
        changed = 0
        with self._lock:
            with self._conn() as conn:
                for i in clean:
                    conn.execute(
                        "UPDATE wa_inbox SET acked_at=? WHERE id=? AND acked_at IS NULL",
                        (now, i),
                    )
                    changed += conn.execute("SELECT changes()").fetchone()[0]
                conn.commit()
        return changed


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


# ─── 360dialog v1 normalisation ──────────────────────────────────────────────────────

def normalize_d360_v1_payload(payload: dict) -> list:
    """Extract and normalise a 360dialog v1 webhook payload (waba-sandbox.360dialog.io).

    360dialog v1 uses the on-premise WA Business API format: a flat top-level dict with
    'messages', 'contacts', and 'statuses' keys — no entry/changes/value nesting.

    Returns a list of normalised event dicts with the same schema as normalize_wa_payload().
    """
    events = []
    now = int(time.time())

    # Build contact name lookup: wa_id → display name
    contacts = {
        c["wa_id"]: c.get("profile", {}).get("name", "")
        for c in payload.get("contacts", [])
        if isinstance(c, dict) and c.get("wa_id")
    }

    # ── incoming messages ──────────────────────────────────────────
    for msg in payload.get("messages", []):
        if not isinstance(msg, dict):
            continue

        sender   = msg.get("from", "")
        msg_type = msg.get("type", "")
        ts       = int(msg.get("timestamp") or 0)
        wamid    = msg.get("id")

        text     = None
        media_id = None
        if msg_type == "text":
            text = (msg.get("text") or {}).get("body")
        elif msg_type in _MEDIA_TYPES:
            media_id = (msg.get(msg_type) or {}).get("id")
        elif msg_type == "location":
            loc  = msg.get("location") or {}
            text = f"{loc.get('latitude')},{loc.get('longitude')}"
        elif msg_type == "interactive":
            intr = msg.get("interactive") or {}
            kind = intr.get("type", "")
            if kind == "button_reply":
                text = (intr.get("button_reply") or {}).get("title")
            elif kind == "list_reply":
                text = (intr.get("list_reply") or {}).get("title")

        history = ts > 0 and (now - ts) > _HISTORY_THRESHOLD_SECS

        events.append({
            "channel":  "wa",
            "from":     sender,
            "name":     contacts.get(sender, ""),
            "type":     msg_type,
            "text":     text,
            "media_id": media_id,
            "ts":       ts,
            "echo":     False,   # sandbox: messages are always from real users
            "history":  history,
            "wamid":    wamid,
            "raw":      msg,
        })

    # ── status updates (delivery/read receipts for outbound messages) ──
    for status in payload.get("statuses", []):
        if not isinstance(status, dict):
            continue
        ts = int(status.get("timestamp") or 0)
        events.append({
            "channel":  "wa",
            "from":     status.get("recipient_id", ""),
            "name":     "",
            "type":     "status",
            "text":     status.get("status"),
            "media_id": None,
            "ts":       ts,
            "echo":     True,
            "history":  ts > 0 and (now - ts) > _HISTORY_THRESHOLD_SECS,
            "wamid":    status.get("id"),
            "raw":      status,
        })

    return events


# ─── HMAC signature verification ─────────────────────────────────────────────────────

def path_secret_ok(configured: str, given: str) -> bool:
    """Is the secret embedded in the URL path the one we configured?

    FAIL-CLOSED: no secret configured → False, always. A door whose key was never set is a
    door that does not open — otherwise forgetting the variable would publish the queue.
    That is why nothing here needs `.env` to be writable to be safe: the doors stay 404
    until the owner puts a real value in, and 404 is the correct state until then.

    Compared with compare_digest so the answer's timing says nothing about the secret.
    """
    if not configured or not given:
        return False
    return hmac.compare_digest(str(configured), str(given))


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

    verify_token:     str = ""
    app_secret:       str = ""
    our_phone:        str = ""
    db:               WAQueueDB = None
    d360_path_secret: str = ""
    pull_secret:      str = ""

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

    def _send_json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json")

    # GET dispatcher — routes by path
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/wa-queue/pull/"):
            self._do_pull(parsed.path)
            return
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

    # POST dispatcher — routes by path
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/wa-webhook":
            self._do_meta_post()
        elif path.startswith("/wa-webhook/d360/"):
            self._do_d360_post(path)
        elif path.startswith("/wa-queue/ack/"):
            self._do_ack(path)
        else:
            self._send(404, "Not found")

    # ── PC pull/ack doors ─────────────────────────────────────────────────────
    #
    # Wrong secret answers exactly like an unknown URL — 404 with the same body. A 401 would
    # confirm the endpoint exists and turn a blind guess into a target list; the d360 door
    # above answers the same way for the same reason.

    def _pull_secret_from(self, path: str, verb: str) -> str:
        """Return the secret segment of /wa-queue/<verb>/<secret>, or '' if malformed."""
        parts = path.split("/")
        # ['', 'wa-queue', verb, secret]
        return parts[3] if len(parts) > 3 and parts[2] == verb else ""

    # GET /wa-queue/pull/<secret>
    def _do_pull(self, path: str):
        if not path_secret_ok(self.pull_secret, self._pull_secret_from(path, "pull")):
            self._send(404, "Not found")
            return
        try:
            items = self.db.pull() if self.db else []
        except Exception as e:
            log.error("WA pull: %s", e, exc_info=True)
            self._send_json(500, {"ok": False, "error": "pull_failed"})
            return
        # Count only — the payload is client correspondence and does not belong in our log.
        log.info("WA pull: %d rows leased to PC", len(items))
        self._send_json(200, {"ok": True, "count": len(items), "items": items})

    # POST /wa-queue/ack/<secret>  body: {"ids": [1,2,3]}
    def _do_ack(self, path: str):
        if not path_secret_ok(self.pull_secret, self._pull_secret_from(path, "ack")):
            self._send(404, "Not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            log.warning("WA ack: JSON parse error: %s", e)
            self._send_json(400, {"ok": False, "error": "bad_json"})
            return
        ids = payload.get("ids")
        if not isinstance(ids, list):
            self._send_json(400, {"ok": False, "error": "ids_must_be_list"})
            return
        try:
            n = self.db.ack(ids) if self.db else 0
        except Exception as e:
            log.error("WA ack: %s", e, exc_info=True)
            self._send_json(500, {"ok": False, "error": "ack_failed"})
            return
        log.info("WA ack: %d of %d ids marked processed", n, len(ids))
        self._send_json(200, {"ok": True, "acked": n})

    # POST /wa-webhook — Meta Cloud API v2, HMAC-verified
    def _do_meta_post(self):
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
                n = self.db.enqueue(events, source="meta") if self.db else 0
                log.info("WA POST: %d events, %d enqueued (dupes skipped)", len(events), n)
            else:
                log.debug("WA POST: payload contained 0 normalised events")
        except Exception as e:
            log.error("WA POST: processing error: %s", e, exc_info=True)

    # POST /wa-webhook/d360/<secret> — 360dialog v1, auth by path secret (no HMAC)
    def _do_d360_post(self, path: str):
        # Extract secret from path: /wa-webhook/d360/<secret>
        # Wrong secret → 404 (not 401 — don't reveal endpoint existence)
        parts = path.split("/")
        secret_in_path = parts[3] if len(parts) > 3 else ""
        if not path_secret_ok(self.d360_path_secret, secret_in_path):
            self._send(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            log.warning("D360 POST: JSON parse error: %s", e)
            self._send(400, "Bad request")
            return

        self._send(200, "ok")
        try:
            self.wfile.flush()
        except Exception:
            pass

        try:
            events = normalize_d360_v1_payload(payload)
            if events:
                n = self.db.enqueue(events, source="d360") if self.db else 0
                log.info("D360 POST: %d events, %d enqueued", len(events), n)
            else:
                log.debug("D360 POST: payload contained 0 events")
        except Exception as e:
            log.error("D360 POST: processing error: %s", e, exc_info=True)


# ─── server bootstrap ─────────────────────────────────────────────────────────────────

def make_server(env: dict) -> ThreadingHTTPServer:
    """Configure and return a ThreadingHTTPServer with WAWebhookHandler.

    ThreadingHTTPServer spawns a daemon thread per request so a slow/hung
    client or a slow db.enqueue() never blocks other incoming connections.
    """
    db = WAQueueDB(env["queue_db"])

    class _Handler(WAWebhookHandler):
        pass

    _Handler.verify_token     = env["verify_token"]
    _Handler.app_secret       = env["app_secret"]
    _Handler.our_phone        = env["phone_id"]
    _Handler.db               = db
    _Handler.d360_path_secret = env.get("d360_path_secret", "")
    _Handler.pull_secret      = env.get("pull_secret", "")

    server = ThreadingHTTPServer((bind_host(env.get("bind_host")), env["port"]), _Handler)
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
        "WA webhook listening on %s:%d  db=%s  pull=%s",
        server.server_address[0], env["port"], env["queue_db"],
        "on" if env.get("pull_secret") else "OFF (WA_PULL_SECRET not set → pull/ack answer 404)",
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
