#!/usr/bin/env python3
"""Serveur EVJF — Lance avec : python3 server.py"""

import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 3000
DB_PATH = os.path.join(os.path.dirname(__file__), "evjf.db")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".json": "application/json",
    ".png":  "image/png",
    ".ico":  "image/x-icon",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            question   TEXT NOT NULL,
            done       INTEGER DEFAULT 0,
            trashed    INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    try:
        conn.execute("ALTER TABLE questions ADD COLUMN trashed INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE questions ADD COLUMN skipped INTEGER DEFAULT 0")
    except Exception:
        pass
    # Migration : supprime la colonne author si elle existe (SQLite ne supporte pas DROP COLUMN avant 3.35)
    conn.commit()
    return conn


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, mime):
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/questions":
            include_all = params.get("all", ["0"])[0] == "1"
            with get_db() as db:
                if include_all:
                    rows = db.execute(
                        "SELECT * FROM questions ORDER BY trashed ASC, created_at ASC"
                    ).fetchall()
                else:
                    rows = db.execute(
                        "SELECT * FROM questions WHERE trashed = 0 ORDER BY created_at ASC"
                    ).fetchall()
                self.send_json(200, [dict(r) for r in rows])
            return

        if path in ("/cartes", "/cartes/"):
            self.send_file(os.path.join(PUBLIC_DIR, "cartes.html"), "text/html; charset=utf-8")
            return

        if path in ("/admin", "/admin/"):
            self.send_file(os.path.join(PUBLIC_DIR, "admin.html"), "text/html; charset=utf-8")
            return

        if path == "/" or path == "":
            path = "/index.html"

        file_path = os.path.join(PUBLIC_DIR, path.lstrip("/"))
        ext = os.path.splitext(file_path)[1]
        mime = MIME.get(ext, "application/octet-stream")
        self.send_file(file_path, mime)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/questions/reset":
            with get_db() as db:
                db.execute("UPDATE questions SET done = 0, skipped = 0 WHERE trashed = 0")
                db.commit()
            self.send_json(200, {"ok": True})
            return
        if parsed.path == "/api/questions":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            question = (body.get("question") or "").strip()
            if not question:
                self.send_json(400, {"error": "La question est requise."})
                return
            with get_db() as db:
                cur = db.execute("INSERT INTO questions (question) VALUES (?)", (question,))
                db.commit()
                row = db.execute("SELECT * FROM questions WHERE id = ?", (cur.lastrowid,)).fetchone()
                self.send_json(200, dict(row))
        else:
            self.send_json(404, {"error": "Not found"})

    def do_PATCH(self):
        parsed = urlparse(self.path)
        parts = parsed.path.split("/")
        if len(parts) == 5 and parts[1] == "api" and parts[2] == "questions":
            qid = parts[3]
            action = parts[4]
            mapping = {
                "done":    ("done",    1),
                "undone":  ("done",    0),
                "trash":   ("trashed", 1),
                "restore": ("trashed", 0),
                "skip":    ("skipped", 1),
                "unskip":  ("skipped", 0),
            }
            if action not in mapping:
                self.send_json(400, {"error": "Action inconnue"})
                return
            col, val = mapping[action]
            with get_db() as db:
                db.execute(f"UPDATE questions SET {col} = ? WHERE id = ?", (val, qid))
                db.commit()
            self.send_json(200, {"ok": True})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts = parsed.path.split("/")
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "questions":
            qid = parts[3]
            with get_db() as db:
                db.execute("DELETE FROM questions WHERE id = ?", (qid,))
                db.commit()
            self.send_json(200, {"ok": True})
        else:
            self.send_json(404, {"error": "Not found"})


if __name__ == "__main__":
    get_db()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n✨  EVJF App lancée !\n")
    print(f"  Lien participants  →  http://localhost:{PORT}/")
    print(f"  Lien mariée        →  http://localhost:{PORT}/cartes")
    print(f"  Lien admin (toi)   →  http://localhost:{PORT}/admin")
    print(f"\nAppuyez sur Ctrl+C pour arrêter.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur arrêté. À bientôt ! 💖")
        sys.exit(0)
