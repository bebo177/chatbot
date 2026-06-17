"""FastAPI server exposing the chatbot.

Endpoints:
  POST /chat   { "session_id": "...", "message": "..." }  →  { "reply": "...", ... }
  POST /reset  { "session_id": "..." }                    →  { "ok": true }
  GET  /       → minimal HTML test page

Run with:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from catalog import FaultCatalog
from conversation import Chatbot

# Load the catalog once, at module import time. 520 entries → a few MB,
# negligible. For multi-worker deploys each worker pays this cost once.
CATALOG_PATH = Path(__file__).parent / "faults.json"
catalog = FaultCatalog(CATALOG_PATH)
bot = Chatbot(catalog)

app = FastAPI(title="Automotive Fault Chatbot", version="1.0.0")


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ResetRequest(BaseModel):
    session_id: str


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    return bot.handle(req.session_id, req.message)


@app.post("/reset")
def reset(req: ResetRequest) -> dict:
    bot.reset(req.session_id)
    return {"ok": True}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "faults_loaded": len(catalog.faults)}


# ── Minimal test UI ───────────────────────────────────────────────────────
# Self-contained, no build step. Open http://localhost:8000/ and chat.
_INDEX_HTML = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>Car Fault Bot</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
  #log { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; height: 480px; overflow-y: auto; background: #fafafa; }
  .msg { margin: .5rem 0; padding: .6rem .8rem; border-radius: 12px; max-width: 80%; white-space: pre-wrap; }
  .user { background: #d4edff; margin-right: auto; }
  .bot  { background: #fff; border: 1px solid #eee; margin-left: auto; }
  form { display: flex; gap: .5rem; margin-top: 1rem; }
  input[type=text] { flex: 1; padding: .6rem; border: 1px solid #ccc; border-radius: 8px; font-size: 1rem; }
  button { padding: .6rem 1.2rem; border: 0; border-radius: 8px; background: #1c64f2; color: white; font-weight: 600; cursor: pointer; }
</style>
</head>
<body>
<h2>🚗 شات بوت تشخيص أعطال السيارة</h2>
<div id="log"></div>
<form id="f">
  <input id="m" type="text" placeholder="اكتب هنا..." autocomplete="off" autofocus>
  <button type="submit">إرسال</button>
</form>
<script>
  const sid = 'web-' + Math.random().toString(36).slice(2);
  const log = document.getElementById('log');
  const f = document.getElementById('f');
  const m = document.getElementById('m');

  function add(role, text) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = m.value.trim();
    if (!text) return;
    add('user', text);
    m.value = '';
    try {
      const r = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid, message: text }),
      });
      const data = await r.json();
      add('bot', data.reply);
    } catch (err) {
      add('bot', '⚠️ خطأ في الاتصال بالسيرفر.');
    }
  });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML
