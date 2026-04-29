"""
api/themes.py — Vercel serverless function: /api/themes

Returns the theme & group taxonomy for the frontend sidebar.
This rarely changes (only when you edit config.py + redeploy), so
it's cached aggressively at the edge.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import THEMES, THEME_GROUPS  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "groups": THEME_GROUPS,
            "themes": {
                k: {
                    "label_en": v["label_en"],
                    "label_zh": v["label_zh"],
                    "groups": v.get("groups", []),
                }
                for k, v in THEMES.items()
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # Cache 1 day at edge — themes rarely change
        self.send_header("Cache-Control",
                         "public, s-maxage=86400, stale-while-revalidate=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
