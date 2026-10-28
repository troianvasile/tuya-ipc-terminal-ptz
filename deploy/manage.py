#!/usr/bin/env python3
"""Local-only, Supervisor-independent account UI and RTSP supervisor."""
import base64
import html
import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

import qrcode

LOG = logging.getLogger("tuya-manager")
DATA = Path("/data/.tuya-data")
REGIONS = ("eu-central", "eu-east", "us-west", "us-east", "china", "india")
MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERS = os.environ["WEB_USERNAME"]
PASSWORD = os.environ["WEB_PASSWORD"]
PORT = int(os.environ.get("WEB_PORT", "8788"))
RTSP_PORT = int(os.environ.get("RTSP_PORT", "8554"))
CHECK_EVERY = max(300, int(os.environ.get("SESSION_CHECK_SECONDS", "3600")))
JOBS = {}
LOCK = threading.Lock()
RTSP = None
STATUS = {"accounts": {}, "rtsp": "stopped", "last_check": None}


def cli(*args, timeout=30):
    return subprocess.run(["tuya-ipc-terminal", *args], cwd="/data",
                          text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def accounts():
    # Matches the storage manager's per-account filenames, not untrusted paths.
    return sorted(DATA.glob("user_*.json")) if DATA.is_dir() else []


def notify(notification_id, title=None, message=None):
    url = os.getenv("HA_URL", "").rstrip("/")
    token = os.getenv("HA_TOKEN", "")
    if not url or not token:
        return
    action = "create" if title else "dismiss"
    payload = ({"notification_id": notification_id, "title": title, "message": message}
               if title else {"notification_id": notification_id})
    req = Request(url + "/api/services/persistent_notification/" + action,
                  data=json.dumps(payload).encode(), method="POST",
                  headers={"Authorization": "Bearer " + token,
                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=8) as response:
            response.read()
    except Exception as exc:
        LOG.warning("HA notification delivery failed: %s", type(exc).__name__)


def session_check():
    info = {}
    for file in accounts():
        try:
            session = json.loads(file.read_text())
            region = session.get("region") or session.get("Region")
            email = session.get("email") or session.get("Email")
            if not isinstance(region, str) or region not in REGIONS or not isinstance(email, str) or not MAIL.fullmatch(email):
                raise ValueError("Unexpected session record")
            result = cli("auth", "test", region, email, timeout=25)
            valid = result.returncode == 0 and "Session is valid" in result.stdout
            key = region + "/" + email
            info[key] = "valid" if valid else "reauthentication needed"
            nid = "tuya_bridge_reauth_" + hashlib.sha256(key.encode()).hexdigest()[:20]
            if valid:
                notify(nid)
            else:
                notify(nid, "Tuya camera login expired",
                       "Reauthenticate the Tuya account via the private bridge management UI.")
        except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            LOG.warning("Unable to validate a stored session: %s", type(exc).__name__)
    STATUS["accounts"] = info
    STATUS["last_check"] = int(time.time())
    notify("tuya_bridge_no_accounts",
           "Tuya bridge: no accounts" if not accounts() else None,
           "Add an account through the bridge management UI." if not accounts() else None)


def supervise():
    global RTSP
    last_check = 0
    last_set = None
    while True:
        current = tuple(str(f) for f in accounts())
        if time.monotonic() - last_check >= CHECK_EVERY or current != last_set:
            try:
                session_check()
            except Exception:
                LOG.exception("Account validation unexpectedly failed")
            last_check = time.monotonic()
        if current:
            if RTSP is None or RTSP.poll() is not None or current != last_set:
                if RTSP is not None and RTSP.poll() is None:
                    RTSP.terminate()
                    try:
                        RTSP.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        RTSP.kill()
                        RTSP.wait()
                try:
                    cli("cameras", "refresh", timeout=40)
                except subprocess.SubprocessError:
                    LOG.warning("Camera refresh failed; continuing")
                RTSP = subprocess.Popen(
                    ["tuya-ipc-terminal", "rtsp", "start", "--port", str(RTSP_PORT)],
                    cwd="/data", stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                LOG.info("RTSP bridge started (pid=%s)", RTSP.pid)
        elif RTSP is not None:
            if RTSP.poll() is None:
                RTSP.terminate()
                RTSP.wait(timeout=10)
            RTSP = None
        STATUS["rtsp"] = "running" if RTSP is not None and RTSP.poll() is None else "stopped"
        last_set = current
        time.sleep(10)


def do_qr(jobid, region, email):
    job = JOBS[jobid]
    proc = None
    killer = None
    try:
        proc = subprocess.Popen(
            ["tuya-ipc-terminal", "auth", "add", region, email, "--qr"],
            cwd="/data", env={**os.environ, "TUYA_QR_WEB": "1"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        killer = threading.Timer(180, proc.kill)
        killer.daemon = True
        killer.start()
        for line in iter(proc.stdout.readline, ""):
            stripped = line.strip()
            if stripped.startswith("QR_LOGIN_URL:"):
                job["payload"] = stripped[len("QR_LOGIN_URL:"):]
                job["status"] = "scan the QR code"
            elif "Do you want to re-authenticate?" in stripped or "Continue anyway?" in stripped:
                proc.stdin.write("y\n")
                proc.stdin.flush()
            elif "Press Enter after scanning" in stripped:
                proc.stdin.write("\n")
                proc.stdin.flush()
            elif "Successfully added user" in stripped:
                job["status"] = "success"
        if proc.wait(timeout=10) != 0 and job["status"] != "success":
            job["status"] = "error"
        elif job["status"] != "success":
            job["status"] = "error"
    except Exception as exc:
        LOG.warning("QR login ended: %s", type(exc).__name__)
        job["status"] = "error"
    finally:
        if killer is not None:
            killer.cancel()
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        job["payload"] = None
        job["completed"] = time.time()


def page():
    rows = "".join("<li>" + html.escape(k) + ": " + html.escape(v) + "</li>"
                   for k, v in sorted(STATUS["accounts"].items())) or "<li>No accounts yet</li>"
    options = "".join('<option value="' + r + '">' + r + "</option>" for r in REGIONS)
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tuya IPC Bridge</title><style>
body{font:16px system-ui;max-width:650px;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}
input,select,button{padding:.6rem;margin:.4rem 0}button{cursor:pointer}code{color:#9fe}
#qr{background:white;padding:10px;display:none;width:256px}li{margin:.4rem 0}
</style></head><body><h1>Tuya IPC Bridge</h1>
<p>RTSP: <b>""" + html.escape(STATUS["rtsp"]) + """</b>. Accounts:</p><ul>""" + rows + """</ul>
<h2>Authenticate with QR code</h2><form id="form">
<label>Region <select name="region">""" + options + """</select></label>
<label>Email <input type="email" name="email" required></label>
<button>Start QR login</button></form>
<p id="status" aria-live="polite"></p><img id="qr" width="256" height="256" alt="Tuya login QR">
<p>Scan with the QR scanner in Tuya Smart / Smart Life (not the phone Camera app).</p>
<script>
const form=document.querySelector('#form'), label=document.querySelector('#status'),img=document.querySelector('#qr');
form.addEventListener('submit',async e=>{
 e.preventDefault();img.style.display='none';label.textContent='Starting...';
 const response=await fetch('/api/qr',{method:'POST',body:new URLSearchParams(new FormData(form))});
 const j=await response.json();if(!response.ok){label.textContent=j.error||'Failed';return}
 const id=j.id;let shown=false;
 async function tick(){
  const r=await fetch('/api/qr/'+id+'/status');if(!r.ok){label.textContent='Job expired';return}
  const data=await r.json();label.textContent=data.status;
  if(data.ready&&!shown){img.src='/api/qr/'+id+'/image';img.style.display='block';shown=true}
  if(data.status==='success'){setTimeout(()=>location.reload(),1200);return}
  if(data.status!=='error')setTimeout(tick,1500);
 }
 tick();
});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def reply(self, status, data, content_type="application/json"):
        payload = data if isinstance(data, bytes) else data.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:], validate=True).decode()
        except (ValueError, UnicodeDecodeError):
            return False
        expected = USERS + ":" + PASSWORD
        return secrets.compare_digest(raw.encode(), expected.encode())

    def check(self):
        if self.authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Tuya Bridge"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.check():
            return
        if self.path == "/api/health":
            with LOCK:
                running = STATUS["rtsp"]
                entries = dict(STATUS["accounts"])
                checked = STATUS["last_check"]
            self.reply(200, json.dumps({
                "service": "tuya-ipc-bridge",
                "rtsp": running,
                "account_count": len(accounts()),
                "accounts": entries,
                "last_check": checked,
            }))
            return
        if self.path == "/":
            self.reply(200, page(), "text/html; charset=utf-8")
            return
        match = re.fullmatch(r"/api/qr/([a-f0-9]{32})/(status|image)", self.path)
        if match:
            with LOCK:
                job = JOBS.get(match[1])
                if not job:
                    self.reply(404, '{"error":"unknown job"}')
                    return
                status, payload = job["status"], job["payload"]
            if match[2] == "status":
                self.reply(200, json.dumps({"status": status, "ready": bool(payload)}))
            elif payload:
                buf = io.BytesIO()
                qrcode.make(payload).save(buf, format="PNG")
                self.reply(200, buf.getvalue(), "image/png")
            else:
                self.reply(404, '{"error":"QR not ready"}')
            return
        self.reply(404, '{"error":"not found"}')

    def do_POST(self):
        if not self.check():
            return
        if self.path != "/api/qr":
            self.reply(404, '{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 2048:
                raise ValueError()
            body = parse_qs(self.rfile.read(length).decode())
            region, email = body["region"][0], body["email"][0]
            if region not in REGIONS or not MAIL.fullmatch(email):
                raise ValueError()
        except (ValueError, KeyError, IndexError, UnicodeDecodeError):
            self.reply(400, '{"error":"invalid region or email"}')
            return
        with LOCK:
            for job in JOBS.values():
                if job["status"] not in ("success", "error") and time.time() - job["created"] < 200:
                    self.reply(409, '{"error":"another login is running"}')
                    return
            for k in list(JOBS):
                if time.time() - JOBS[k]["created"] > 600:
                    del JOBS[k]
            key = uuid.uuid4().hex
            JOBS[key] = {"status": "starting", "payload": None, "created": time.time()}
        threading.Thread(target=do_qr, args=(key, region, email), daemon=True).start()
        self.reply(202, json.dumps({"id": key}))


if __name__ == "__main__":
    if not USERS or len(PASSWORD) < 20 or PASSWORD.startswith("REPLACE"):
        raise SystemExit("Set a nonempty WEB_USERNAME and a strong WEB_PASSWORD (20+ chars)")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    threading.Thread(target=supervise, daemon=True).start()
    LOG.info("Starting private UI port %d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
