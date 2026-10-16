"""Loopback-only manual refresh service. No inference or GitHub secrets in the website."""
import argparse
import base64
import copy
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone

REPO = 'pavelkohout-dotcom/sentiment'
SITE = 'https://pavelkohout-dotcom.github.io'
PORT = 8766
LOCAL = f'http://127.0.0.1:{PORT}'
CACHE = 'state/llama_scores.json'
API = f'https://api.github.com/repos/{REPO}'


def request_json(url, token=None, data=None, method=None):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'MSM-local-control'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, headers=headers, method=method,
                                 data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def merge_cache(local, remote):
    for key in ('model', 'model_digest', 'prompt_hash', 'options'):
        if local.get(key) != remote.get(key):
            raise ValueError('Incompatible cache')
    result = copy.deepcopy(max((local, remote), key=lambda c: c.get('last_attempt', '')))
    result['ratings'] = copy.deepcopy(remote['ratings'])
    for key, value in local['ratings'].items():
        old = result['ratings'].get(key)
        if old is None or value['rated_at'] > old['rated_at']:
            result['ratings'][key] = value
    return result


def publish(cache, token):
    # Re-read the blob on every retry; never push a stale checkout or generated data.
    for attempt in range(3):
        blob = request_json(API + '/contents/' + CACHE + '?ref=main', token)
        remote = json.loads(base64.b64decode(blob['content']))
        merged = merge_cache(cache, remote)
        content = json.dumps(merged, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        try:
            result = request_json(API + '/contents/' + CACHE, token, {
                'branch': 'main', 'sha': blob['sha'],
                'message': 'data: refresh local Llama ratings (manual)',
                'content': base64.b64encode(content.encode()).decode()}, 'PUT')
            return result['commit']['sha'], merged
        except urllib.error.HTTPError as ex:
            if ex.code not in (409, 422) or attempt == 2:
                raise
    raise RuntimeError('Concurrent update')


class Controller:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.secret = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.guard = threading.Lock()
        self.state = {'phase': 'idle', 'message': 'Připraveno k aktualizaci.'}

    @property
    def token_path(self):
        return self.directory / 'github-token'

    def status(self):
        with self.guard:
            return {**self.state, 'configured': self.token_path.exists(),
                    'running': self.lock.locked(), 'nonce': self.secret}

    def update(self, phase, message, **extra):
        with self.guard:
            self.state = {'phase': phase, 'message': message, **extra}

    def configure(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 512 or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError('Invalid token')
        repo = request_json(API, token)
        if not repo.get('permissions', {}).get('push'):
            raise ValueError('Missing write permission')
        fd, name = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(token)
            os.replace(name, self.token_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def start(self):
        if not self.token_path.exists():
            return 428
        if not self.lock.acquire(blocking=False):
            return 409
        self.update('starting', 'Připravuji nové hodnocení…')
        threading.Thread(target=self.run, daemon=True).start()
        return 202

    def run(self):
        try:
            token = self.token_path.read_text().strip()
            # Fail before inference when credentials are invalid.
            request_json(API, token)
            with tempfile.TemporaryDirectory(prefix='refresh-', dir=self.directory) as tmp:
                root = Path(tmp) / 'repo'
                env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
                subprocess.run(['git', 'clone', '--depth', '1', '--branch', 'main',
                                f'https://github.com/{REPO}.git', str(root)],
                               check=True, timeout=120, capture_output=True, env=env)
                original = json.loads((root / CACHE).read_text())
                pending = self.directory / 'pending-scores.json'
                if pending.exists():
                    recovered = merge_cache(json.loads(pending.read_text()), original)
                    (root / CACHE).write_text(json.dumps(recovered, ensure_ascii=False))
                self.update('rating', 'Llama hodnotí nové titulky na tomto Macu…')
                result = subprocess.run([sys.executable, '-B', '-m', 'msm.rate_local'],
                                        cwd=root, env=env, capture_output=True, timeout=1800)
                cache = json.loads((root / CACHE).read_text())
                if result.returncode not in (0, 1) or cache.get('last_attempt') == original.get('last_attempt'):
                    raise RuntimeError('Local rating failed')
                count = len(cache['ratings']) - len(original['ratings'])
                errors = len(cache.get('errors', []))
                # Retain valid results even when publication fails; token is never copied here.
                (self.directory / 'pending-scores.json').write_text(json.dumps(cache, ensure_ascii=False))
                self.update('publishing', 'Odesílám platná hodnocení na GitHub…', added=count, errors=errors)
                commit, merged = publish(cache, token)
                published_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                pending.unlink(missing_ok=True)
            self.update('deploying', 'Hodnocení jsou odeslaná. Čekám na aktualizaci webu…', added=count, errors=errors)
            target = merged.get('last_success')
            for _ in range(20):
                time.sleep(15)
                try:
                    live = request_json(SITE + '/sentiment/data/latest.json?t=' + str(time.time_ns()))
                    deployed = live.get('llama', {}).get('last_refresh_at', '')
                    if target and deployed and deployed >= target and live.get('generated_at', '') >= published_at:
                        self.update('done', f'Web aktualizován. Nová hodnocení: {count}. Vynechané chyby: {errors}.', commit=commit)
                        return
                except (OSError, ValueError):
                    pass
            self.update('published', 'Hodnocení jsou na GitHubu; nasazení webu zatím není potvrzené.', commit=commit)
        except urllib.error.HTTPError as ex:
            self.update('error', f'GitHub nebo zdroj odmítl požadavek (HTTP {ex.code}). Zkontrolujte místní připojení GitHubu; zveřejnění není potvrzené.')
        except Exception as ex:
            self.update('error', f'Aktualizace se nedokončila ({type(ex).__name__}). Zkontrolujte internet a běžící Ollamu. Zveřejnění není potvrzené.')
        finally:
            self.lock.release()


SETUP = '''<!doctype html><html lang="cs"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>MSM · Tento Mac</title>
<style>body{font:17px system-ui;color:#172b3a;background:#f5f7f9;max-width:650px;margin:60px auto;padding:24px}button,input{font:inherit;padding:12px}input{width:90%;margin:12px 0}button{background:#086b68;color:white;border:0;border-radius:6px}a{color:#086b68}p{line-height:1.6}</style>
<h1>Aktualizace z tohoto Macu</h1><p id="status" role="status">Načítám připojení…</p>
<form id="setup"><h2>Jednorázové připojení GitHubu</h2><p>Vytvořte <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener noreferrer">omezený přístupový token na GitHubu</a>: vlastník <b>pavelkohout-dotcom</b>, pouze repozitář <b>sentiment</b>, oprávnění <b>Contents: Read and write</b>. Ostatní oprávnění ponechte vypnutá.</p><label for="token">Přístupový token (ukládá se pouze na tomto Macu)</label><input id="token" type="password" autocomplete="off" required><button>Připojit GitHub</button><p>Nevkládejte token do chatu. Po jeho vypršení jej zde můžete nahradit.</p></form>
<p><button id="run" disabled>Aktualizovat sentiment teď</button></p><p><a href="https://pavelkohout-dotcom.github.io/sentiment/">Otevřít veřejný web ↗</a></p>
<script src="/setup.js"></script></html>'''
SETUP_JS = '''let nonce;const status=document.getElementById('status'),run=document.getElementById('run');
async function poll(){try{const s=await(await fetch('/status')).json();nonce=s.nonce;status.textContent=s.configured?s.message:'Ještě je potřeba připojit GitHub.';run.disabled=!s.configured||s.running;}catch{status.textContent='Místní pomocník není dostupný.';run.disabled=true;}}
document.getElementById('setup').onsubmit=async e=>{e.preventDefault();const field=document.getElementById('token');const token=field.value;field.value='';try{const r=await fetch('/configure',{method:'POST',headers:{'Content-Type':'application/json','X-MSM-Token':nonce},body:JSON.stringify({token})});if(!r.ok)throw Error();await poll();}catch{status.textContent='Připojení se nezdařilo. Zkontrolujte token, přístup k repozitáři a internet.';}};
run.onclick=async()=>{run.disabled=true;try{const r=await fetch('/refresh',{method:'POST',headers:{'Content-Type':'application/json','X-MSM-Token':nonce},body:'{}'});if(!r.ok&&r.status!==409)throw Error();await poll();}catch{status.textContent='Spuštění se nezdařilo.';run.disabled=false;}};poll();setInterval(poll,3000);'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed(self):
        return (self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
                and self.headers.get('Origin') in (None, SITE, self.local_origin))

    @property
    def local_origin(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def reply(self, code, data, mime='application/json'):
        body = (json.dumps(data) if mime == 'application/json' else data).encode()
        self.send_response(code)
        origin = self.headers.get('Origin')
        if origin in (SITE, self.local_origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-MSM-Token')
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.reply(200 if self.allowed() else 403, {})

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {})
        if self.path == '/status':
            return self.reply(200, self.server.controller.status())
        if self.path in ('/', '/setup.js') and self.headers.get('Origin') in (None, self.local_origin):
            return self.reply(200, SETUP if self.path == '/' else SETUP_JS,
                              'text/html' if self.path == '/' else 'application/javascript')
        self.reply(404, {})

    def do_POST(self):
        control = self.server.controller
        if (not self.allowed() or self.headers.get('Origin') not in (SITE, self.local_origin)
                or not secrets.compare_digest(self.headers.get('X-MSM-Token', ''), control.secret)):
            return self.reply(403, {})
        if self.headers.get('Content-Type') != 'application/json':
            return self.reply(415, {})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2048:
                return self.reply(413, {})
            data = json.loads(self.rfile.read(size))
            if self.path == '/configure':
                if self.headers.get('Origin') != self.local_origin:
                    return self.reply(403, {})
                control.configure(data['token'])
                return self.reply(200, {'ok': True})
            if self.path == '/refresh':
                return self.reply(control.start(), control.status())
            self.reply(404, {})
        except Exception:
            self.reply(400, {'error': 'Požadavek se nezdařil.'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.controller = Controller(args.directory)
    server.serve_forever()


if __name__ == '__main__':
    main()
