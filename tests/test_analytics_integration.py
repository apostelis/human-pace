import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import inject
import pace
import pace_config as pc
import pace_analytics as a
import preview

class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {'HUMAN_PACE_ANALYTICS_DIR': str(self.root / 'analytics'),
                    'HUMAN_PACE_CONFIG': str(self.root / 'config.json'),
                    'HUMAN_PACE_LOG': str(self.root / 'ratings.jsonl'),
                    'HUMAN_PACE_STATE': str(self.root / 'state'),
                    'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'commands'}
        self.patch = patch.dict(os.environ, self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.store = a.default_store()
        self.store.configure(enabled=True)

    def send(self, event='UserPromptSubmit', session='s1', prompt='hello', extra=None):
        output = io.StringIO()
        env = {**self.env, **(extra or {})}
        inject.main(io.StringIO(json.dumps({'hook_event_name': event, 'session_id': session, 'prompt': prompt})), output, env)
        return output.getvalue()

    def events(self):
        return self.store.read(now=datetime.now(timezone.utc), days=30)['events']

    def test_hooks_count_silent_prompts_and_resume_as_one_session(self):
        self.send('SessionStart')
        self.send()
        self.assertEqual(self.send(), '')
        self.send('SessionStart')
        records = self.events()
        self.assertEqual(sum(e['event'] == 'prompt_observed' for e in records), 2)
        self.assertEqual(len({e['session_key'] for e in records if e['session_key']}), 1)

    def test_skip_controls_and_plugin_commands_excluded_from_prompt_counts(self):
        self.send(extra={'HUMAN_PACE': '0'})
        self.send(extra={'CLAUDE_CODE_ENTRYPOINT': 'sdk-cli'})
        for prompt in ['/pace', '/pace-settings', '/pace-preview', '/human-pace:pace-settings']:
            self.send(prompt=prompt)
        self.assertEqual(self.events(), [])
        self.send(prompt='/pace-other')
        self.assertEqual(sum(e['event'] == 'prompt_observed' for e in self.events()), 1)

    def test_native_changes_and_invalid_fallbacks_are_recorded(self):
        self.send('SessionStart')
        self.send(extra={'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native', 'CLAUDE_PLUGIN_OPTION_LENGTH': '350'})
        self.send(extra={'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native', 'CLAUDE_PLUGIN_OPTION_LENGTH': 'bad'})
        records = self.events()
        self.assertEqual(sum(e['event'] == 'config_observed_changed' for e in records), 2)
        errors = [e for e in records if e['event'] == 'settings_error']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['settings']['length'], 200)
        self.assertNotIn(str(self.root), json.dumps(records))

    def test_analytics_failure_preserves_hook_output(self):
        with patch.object(a.AnalyticsStore, 'observe', side_effect=OSError('disk failure')):
            output = self.send('SessionStart')
        self.assertIn('additionalContext', json.loads(output)['hookSpecificOutput'])

    def test_command_saves_and_controls_are_counted_separately(self):
        pace.run(['analytics', 'on'])
        pace.run(['bionic', 'off'])
        pace.run(['bionic', 'off'])
        records = self.events()
        self.assertEqual(sum(e['event'] == 'command_invoked' for e in records), 2)
        self.assertEqual(sum(e['event'] == 'config_saved' for e in records), 1)
        before = len(records)
        for args in [['analytics'], ['report'], ['report', 'usage', '30'], ['report', 'compare'], ['analytics', 'export']]:
            self.assertNotEqual(pace.run(args), pace.USAGE)
        self.assertEqual(len(self.events()), before)

    def test_rating_note_stays_only_in_legacy_log(self):
        pace.run(['rate', '4', 'SENTINEL_PRIVATE_NOTE'])
        self.assertIn('SENTINEL_PRIVATE_NOTE', (self.root / 'ratings.jsonl').read_text())
        exported = pace.run(['analytics', 'export'])
        self.assertNotIn('SENTINEL_PRIVATE_NOTE', exported)
        records = [json.loads(line) for line in exported.splitlines()]
        self.assertEqual(sum(e['event'] == 'rating_submitted' for e in records), 1)
        self.assertTrue(pace.run(['report']).startswith(pace.report()))
        self.assertIn('Local usage', pace.run(['report']))

    def test_native_mode_permits_analytics_and_failed_mutations_have_no_save(self):
        with patch.dict(os.environ, {'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native'}):
            self.assertNotEqual(pace.run(['analytics']), pace.USAGE)
            out = pace.run(['length', '350'])
            self.assertIn('native configuration', out)
            self.assertIn('Local usage', pace.run(['report', 'usage']))
        records = self.events()
        self.assertEqual(sum(e['event'] == 'config_saved' for e in records), 0)
        self.assertEqual([e['outcome'] for e in records if e['event'] == 'command_invoked'], ['invalid'])

    def test_clear_preserves_ratings_and_preferences_and_disabled_stops_events(self):
        pace.run(['rate', '3'])
        pace.run(['analytics', 'retention', '2'])
        pace.run(['reset'])
        self.assertEqual(self.store.preferences()['retention_days'], 2)
        pace.run(['analytics', 'off'])
        count = len(self.events())
        pace.run(['status-invalid'])
        self.send()
        self.assertEqual(len(self.events()), count)
        pace.run(['analytics', 'clear'])
        self.assertEqual(self.events(), [])
        self.assertFalse(self.store.preferences()['enabled'])
        self.assertIn('3.0 avg', pace.report())

    def test_settings_save_events_and_failures(self):
        cfg = {**pc.defaults(), 'length': 350}
        preview.save_settings(cfg)
        preview.save_settings(cfg)
        self.assertEqual(sum(e['event'] == 'config_saved' for e in self.events()), 1)
        with self.assertRaises(ValueError):
            preview.save_settings({**cfg, 'length': -1})
        self.assertEqual(sum(e['event'] == 'config_saved' for e in self.events()), 1)
        with patch.dict(os.environ, {'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native'}), patch('preview.subprocess.run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = 'SENTINEL_ERROR_PATH'
            with self.assertRaises(ValueError):
                preview.save_settings(cfg)
        self.assertNotIn('SENTINEL_ERROR_PATH', json.dumps(self.events()))
        self.assertEqual(sum(e['event'] == 'config_saved' for e in self.events()), 1)

    def test_failed_recording_does_not_fail_save_or_rating(self):
        with patch.object(a.AnalyticsStore, 'record', side_effect=OSError('disk')):
            self.assertIn('next prompt', pace.run(['length', '350']))
            self.assertIn('Logged', pace.run(['rate', '5']))
            self.assertIn('Saved', preview.save_settings({**pc.defaults(), 'length': 400}))
        self.assertEqual(pc.load_config()[0]['length'], 400)

    def test_invalid_control_arguments_change_nothing_and_cli_errors_are_nonzero(self):
        for args in [['analytics', 'retention', '0'], ['analytics', 'retention', '366'],
                     ['analytics', 'on', 'extra'], ['report', 'usage', '0']]:
            self.assertEqual(pace.run(args), pace.USAGE)
        from contextlib import redirect_stdout, redirect_stderr
        (self.root / 'analytics' / 'preferences.json').write_text('{bad')
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = pace.main(['analytics export'])
        self.assertNotEqual(code, 0)
        self.assertEqual(stdout.getvalue(), '')
        self.assertTrue(stderr.getvalue())

    def test_preview_parent_is_counted_once_and_failed_output_is_recorded(self):
        from contextlib import redirect_stdout
        with patch.object(sys, 'argv', ['preview', '--output', str(self.root / 'preview.html')]), redirect_stdout(io.StringIO()):
            preview.main()
        invocations = [e for e in self.events() if e['event'] == 'command_invoked']
        self.assertEqual([(e['operation'], e['outcome']) for e in invocations], [('preview', 'success')])
        with patch.object(sys, 'argv', ['preview', '--output', str(self.root / 'missing' / 'preview.html')]):
            with self.assertRaises(OSError):
                preview.main()
        invocations = [e for e in self.events() if e['event'] == 'command_invoked']
        self.assertEqual(invocations[-1]['outcome'], 'error')
        count = len(invocations)
        with patch.object(sys, 'argv', ['preview', '--serve']), patch('preview.serve'):
            preview.main()
        self.assertEqual(sum(e['event'] == 'command_invoked' for e in self.events()), count)

    def test_full_usage_journey(self):
        import pace_analytics_report as reports
        self.send('SessionStart')
        self.send()
        self.send()
        pace.run(['bionic', 'off'])
        pace.run(['bionic', 'off'])
        self.send()
        self.send()
        pace.run(['bionic', 'on'])
        self.send()
        pace.run(['rate', '4'])
        summary = reports.summarize(self.events(), now=datetime.now(timezone.utc), days=30)
        aid = a.config_identity(pc.defaults())['format_config_id']
        bid = a.config_identity({**pc.defaults(), 'bionic': False})['format_config_id']
        self.assertEqual(summary['configurations'][aid]['share'], 3/5)
        self.assertEqual(summary['configurations'][bid]['share'], 2/5)
        self.assertEqual(summary['transitions'], {(aid, bid): 1, (bid, aid): 1})
        self.assertEqual(summary['editing']['saves'], 2)
        self.assertEqual(summary['ratings'][aid]['count'], 1)
        count = len(self.events())
        pace.run(['report'])
        pace.run(['report', 'compare'])
        self.assertEqual(len(self.events()), count)
        for line in pace.run(['analytics', 'export']).splitlines():
            self.assertIsNotNone(a.validate_event(json.loads(line)))

    def test_unauthorized_panel_requests_produce_no_events(self):
        import http.client
        import threading
        server = preview.create_server('token')
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            conn.request('POST', '/wrong/save', json.dumps(pc.defaults()), {'Content-Type': 'application/json'})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
        self.assertEqual(self.events(), [])

    def test_existing_test_runners_cannot_record_into_callers_store(self):
        import subprocess
        repo = Path(__file__).resolve().parents[1]
        for args in ([str(repo / 'tests' / 'test_pace.py')],
                     ['-m', 'unittest', 'discover', '-s', str(repo / 'tests'), '-p', 'test_gradient.py']):
            result = subprocess.run([sys.executable, *args], cwd=repo, env=dict(os.environ),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.events(), [], 'test runner polluted caller analytics store')
