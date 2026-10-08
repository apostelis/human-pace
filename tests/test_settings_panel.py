import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import pace_config as pc
import preview

class PanelTest(unittest.TestCase):
    def test_authenticated_save_round_trips_and_rejects_invalid_or_foreign_requests(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'HUMAN_PACE_CONFIG': str(Path(directory) / 'config.json'),
            'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'commands'}):
            server = preview.create_server('test-token')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_port
            def request(path, data, origin=None):
                conn = http.client.HTTPConnection('127.0.0.1', port)
                headers = {'Content-Type': 'application/json'}
                if origin: headers['Origin'] = origin
                conn.request('POST', path, json.dumps(data), headers)
                response = conn.getresponse()
                body = response.read()
                conn.close()
                return response.status, body
            try:
                cfg = {**pc.defaults(), 'length': 350, 'driftGuard': 4}
                self.assertEqual(request('/test-token/save', cfg)[0], 200)
                self.assertEqual(pc.load_config()[0], cfg)
                self.assertEqual(request('/wrong/save', cfg)[0], 403)
                self.assertEqual(request('/test-token/save', cfg, 'https://evil.example')[0], 403)
                self.assertEqual(request('/test-token/save', {**cfg, 'length': -1})[0], 400)
                self.assertEqual(request('/test-token/save', {'length': 50})[0], 400)
                self.assertEqual(pc.load_config()[0], cfg)
            finally:
                server.shutdown()
                server.server_close()

    def test_native_save_uses_claude_configuration_and_reports_reload(self):
        with patch.dict(os.environ, {'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native'}), patch('preview.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stderr = ''
            message = preview.save_settings(pc.defaults())
            self.assertIn('reload', message.lower())
            values = json.loads(run.call_args.kwargs['input'])
            self.assertEqual(values['configurationSource'], 'native')
            self.assertEqual(values['length'], '200')
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_native_failure_does_not_claim_saved(self):
        with patch.dict(os.environ, {'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native'}), patch('preview.subprocess.run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = 'plugin not installed'
            with self.assertRaisesRegex(ValueError, 'plugin not installed'):
                preview.save_settings(pc.defaults())


from analytics_test_support import isolated_analytics
setUpModule, tearDownModule = isolated_analytics()
