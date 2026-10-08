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
