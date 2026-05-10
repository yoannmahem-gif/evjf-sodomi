import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

_schema_initialized = False


def get_conn():
    global _schema_initialized
    conn = psycopg2.connect(DATABASE_URL)
    if not _schema_initialized:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id         SERIAL PRIMARY KEY,
                    question   TEXT NOT NULL,
                    done       INTEGER DEFAULT 0,
                    trashed    INTEGER DEFAULT 0,
                    skipped    INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        conn.commit()
        _schema_initialized = True
    return conn


def normalize_path(raw_path):
    """Strip query string and ensure leading /api."""
    p = urlparse(raw_path).path
    if not p.startswith("/api"):
        p = "/api" + p if p.startswith("/") else "/api/" + p
    return p


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = normalize_path(self.path)
        params = parse_qs(urlparse(self.path).query)

        if path == "/api/questions":
            include_all = params.get("all", ["0"])[0] == "1"
            try:
                with get_conn() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        if include_all:
                            cur.execute("SELECT * FROM questions ORDER BY trashed ASC, created_at ASC")
                        else:
                            cur.execute("SELECT * FROM questions WHERE trashed = 0 ORDER BY created_at ASC")
                        rows = cur.fetchall()
                self._send_json(200, [dict(r) for r in rows])
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = normalize_path(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        try:
            if path == "/api/questions/reset":
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE questions SET done = 0, skipped = 0 WHERE trashed = 0")
                    conn.commit()
                self._send_json(200, {"ok": True})
                return

            if path == "/api/questions":
                question = (body.get("question") or "").strip()
                if not question:
                    self._send_json(400, {"error": "La question est requise."})
                    return
                with get_conn() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(
                            "INSERT INTO questions (question) VALUES (%s) RETURNING *",
                            (question,)
                        )
                        row = cur.fetchone()
                    conn.commit()
                self._send_json(200, dict(row))
                return

            self._send_json(404, {"error": "Not found"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_PATCH(self):
        path = normalize_path(self.path)
        parts = [p for p in path.split("/") if p]
        # /api/questions/:id/:action
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "questions":
            qid = parts[2]
            action = parts[3]
            mapping = {
                "done":    ("done",    1),
                "undone":  ("done",    0),
                "trash":   ("trashed", 1),
                "restore": ("trashed", 0),
                "skip":    ("skipped", 1),
                "unskip":  ("skipped", 0),
            }
            if action not in mapping:
                self._send_json(400, {"error": "Action inconnue"})
                return
            col, val = mapping[action]
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE questions SET {col} = %s WHERE id = %s",
                            (val, qid)
                        )
                    conn.commit()
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        self._send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        path = normalize_path(self.path)
        parts = [p for p in path.split("/") if p]
        # /api/questions/:id
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "questions":
            qid = parts[2]
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM questions WHERE id = %s", (qid,))
                    conn.commit()
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        self._send_json(404, {"error": "Not found"})
