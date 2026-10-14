#!/usr/bin/env python3
"""Open a local formatting preview or a settings page with Save."""
import argparse
import html
import json
import os
from pathlib import Path
import tempfile
import secrets
import subprocess
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import webbrowser
import pace_config
import pace_analytics as analytics
from datetime import datetime, timezone


def render(cfg, *, settings=False):
    template = (Path(__file__).resolve().parent.parent / 'preview' / 'index.html').read_text()
    # JSON is embedded in script text, where HTML closing tags must be escaped.
    passages = json.loads((Path(__file__).resolve().parent.parent / 'preview' / 'passages.json').read_text())
    controls = ''
    if settings:
        try:
            import pace_remote_store as remote
            store = analytics.default_store()
            notice = remote.RemoteStore(store.root).invitation(surface='settings', now=datetime.now(timezone.utc),
                local_enabled=store.preferences()['enabled'], release=remote.RELEASE)
            controls = sharing_controls(notice, remote.RELEASE)
        except Exception:
            controls = '<p>Sharing settings unavailable; check /pace analytics share.</p>'
    return (template.replace('__SHARING_CONTROLS__', controls).replace('__ANALYTICS_NOTICE__' , html.escape(analytics.recording_notice())).replace('__CONFIG__', json.dumps(cfg).replace('<', '\\u003c'))
            .replace('__PASSAGES__', json.dumps(passages).replace('<', '\\u003c')))


def sharing_controls(notice, release):
    import pace_remote_store as remote
    if not remote.valid_release(release):
        return '<p class="muted">Remote sharing is unavailable until a collecting release is configured.</p>'
    opened = ' open' if notice['visible'] else ''
    content = html.escape(remote.disclosure(release))
    return f'''<details id="sharing-panel"{opened}><summary>Sharing settings</summary>
<p>{content}</p><button type="button" data-share="enable">Enable sharing</button>
<button type="button" data-share="later">Not now</button>
<button type="button" data-share="never">Don't ask again</button>
<p id="sharing-status" role="status"></p></details>
<script>
document.querySelectorAll('[data-share]').forEach(button=>button.addEventListener('click',async()=>{{
const buttons=document.querySelectorAll('[data-share]');buttons.forEach(b=>b.disabled=true);
const status=document.getElementById('sharing-status');status.textContent='Saving choice…';
try{{const response=await fetch(new URL('sharing',location.href),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{action:button.dataset.share}})}});
const result=await response.json();if(!response.ok)throw new Error(result.message||'Sharing choice failed.');status.textContent=result.message;
}}catch(error){{status.textContent='Could not save sharing choice: '+error.message;}}
finally{{buttons.forEach(b=>b.disabled=false);}}
}}));
</script>'''


def preview_config():
    return pace_config.load_effective_config(env=pace_config.option_environment())[0]


def _save_settings(data):
    if not isinstance(data, dict) or set(data) != set(pace_config.DEFAULTS):
        raise ValueError("Supply all formatting settings and no unknown fields.")
    cfg, invalid = pace_config.validate(data)
    if invalid:
        raise ValueError("Invalid settings: " + ", ".join(invalid))
    env = pace_config.option_environment()
    if env.get("CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE") == "native":
        values = {key: value if isinstance(value, str) else json.dumps(value) for key, value in cfg.items()}
        values["configurationSource"] = "native"
        result = subprocess.run(["claude", "plugin", "configure", "human-pace@human-pace", "--values-stdin"],
                                input=json.dumps(values), text=True, capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError("Claude could not save native options: " + result.stderr.strip()[:500])
        return "Saved native options. Reload the plugin or restart the Claude session to apply them."
    pace_config.save_config(cfg)
    return "Saved. Your choices apply from your next ordinary prompt in Claude."


def save_settings(data):
    env = pace_config.option_environment()
    old = None
    try:
        # Claude's injected options describe process startup. The configure CLI writes
        # user options to disk, so refresh that saved baseline before each native save.
        baseline_env = env
        if env.get('CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE') == 'native':
            saved_env = pace_config.option_environment({})
            if saved_env.get('CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE') == 'native':
                baseline_env = saved_env
        old, _ = pace_config.load_effective_config(env=baseline_env)
    except Exception:
        pass  # Analytics baseline collection must never prevent a valid save.
    config_source = 'native' if env.get('CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE') == 'native' else 'commands'
    try:
        message = _save_settings(data)
    except (ValueError, OSError, subprocess.SubprocessError):
        valid = analytics.valid_config(data)
        analytics.record_action('settings_save', 'error' if valid else 'invalid', source='preview',
            cfg=old, config_source=config_source, now=datetime.now(timezone.utc), events=[{
                'event': 'settings_error', 'category': 'save_failed' if valid else 'invalid_settings', 'invalid_fields': []}])
        raise
    events = [{'event': 'config_saved', 'previous_settings': old}] if old is not None and old != data else []
    analytics.record_action('settings_save', 'success', source='preview', cfg=data,
        config_source=config_source, now=datetime.now(timezone.utc), events=events)
    return message


def create_server(token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body, content_type="application/json"):
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(encoded)

        def authorized(self):
            host = "127.0.0.1:" + str(self.server.server_port)
            return (self.headers.get("Host") == host and
                    self.headers.get("Origin", "http://" + host) == "http://" + host and
                    self.path.startswith("/" + token + "/"))

        def do_GET(self):
            if not self.authorized() or self.path != "/" + token + "/":
                self.respond(403, '{}')
                return
            self.respond(200, render(preview_config(), settings=True), "text/html; charset=utf-8")

        def do_POST(self):
            if not self.authorized() or self.path not in ("/" + token + "/save", "/" + token + "/sharing"):
                self.respond(403, '{}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Expected a small JSON settings object.")
                from pace_remote_contract import strict_json
                data = strict_json(self.rfile.read(length), max_bytes=8192)
                if self.path.endswith('/sharing'):
                    import pace_remote_store as remote
                    if not isinstance(data, dict) or set(data) != {'action'} or data['action'] not in ('enable','later','never'):
                        raise ValueError('Invalid sharing action.')
                    store = analytics.default_store()
                    remote.RemoteStore(store.root).choose_invitation(data['action'], now=datetime.now(timezone.utc),
                        local_enabled=store.preferences()['enabled'], release=remote.RELEASE)
                    message = 'Sharing enabled; future events queued for manual upload.' if data['action']=='enable' else 'Invitation dismissed. Sharing settings remain available here.'
                else:
                    message = save_settings(data)
                self.respond(200, json.dumps({"message": message}))
            except (ValueError, OSError, analytics.AnalyticsError, subprocess.SubprocessError) as error:
                self.respond(400, json.dumps({"message": str(error)}))

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    original_get_request = server.get_request
    def get_request():
        connection, address = original_get_request()
        connection.settimeout(5)
        return connection, address
    server.get_request = get_request
    return server


def serve():
    token = secrets.token_urlsafe(32)
    with create_server(token) as server:
        print("http://127.0.0.1:" + str(server.server_port) + "/" + token + "/", flush=True)
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            server.handle_request()


def _run_preview(args):
    if args.serve:
        serve()
        return
    if args.settings:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve'],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                 start_new_session=True)
        url = child.stdout.readline().strip()
        child.stdout.close()
        if not url.startswith('http://127.0.0.1:'):
            raise SystemExit('Could not start the local settings page.')
        print(url)
        if args.open:
            webbrowser.open(url)
        return
    if args.output:
        path = args.output.resolve()
        path.write_text(render(preview_config()), encoding='utf-8')
    else:
        fd, name = tempfile.mkstemp(prefix='human-pace-preview-', suffix='.html')
        path = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(render(preview_config()))
    print(path)
    if args.open:
        if not webbrowser.open(path.as_uri()):
            print('Open the HTML file above in a browser to view the preview.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--settings', action='store_true', help='Start the local settings page with Save')
    parser.add_argument('--open', action='store_true', help='Open the preview in your browser')
    parser.add_argument('--output', type=Path, help='Save to this HTML file')
    args = parser.parse_args()
    outcome = 'success'
    try:
        return _run_preview(args)
    except (OSError, ValueError, subprocess.SubprocessError, SystemExit):
        outcome = 'error'
        raise
    finally:
        if not args.serve:
            try:
                env = pace_config.option_environment()
                cfg, _ = pace_config.load_effective_config(env=env)
                analytics.record_action('settings_open' if args.settings else 'preview', outcome,
                    source='preview', cfg=cfg,
                    config_source='native' if env.get('CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE') == 'native' else 'commands',
                    now=datetime.now(timezone.utc))
            except Exception:
                pass


if __name__ == '__main__':
    main()
