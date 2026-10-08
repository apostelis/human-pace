import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import pace_config as pc
import inject

class NativeConfigTest(unittest.TestCase):
    def test_native_values_override_local_without_changing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"bionic": true, "length": 99}')
            env = {'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native',
                   'CLAUDE_PLUGIN_OPTION_BIONIC': 'false',
                   'CLAUDE_PLUGIN_OPTION_LENGTH': '300',
                   'CLAUDE_PLUGIN_OPTION_BIONICAPPROACH': 'vowels'}
            cfg, error = pc.load_effective_config(path, env)
            self.assertFalse(cfg['bionic'])
            self.assertEqual(cfg['length'], 300)
            self.assertEqual(cfg['bionicApproach'], 'vowels')
            self.assertIsNone(error)
            self.assertEqual(json.loads(path.read_text())['length'], 99)

    def test_invalid_native_values_fall_back_and_report(self):
        cfg, error = pc.load_effective_config(Path('/tmp/no-human-pace-config'), {
            'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native',
            'CLAUDE_PLUGIN_OPTION_LENGTH': '-1',
            'CLAUDE_PLUGIN_OPTION_BIONIC': 'yes'})
        self.assertEqual(cfg, pc.defaults())
        self.assertIn('length', error)
        self.assertIn('bionic', error)

    def test_commands_source_ignores_native_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"length": 99}')
            cfg, _ = pc.load_effective_config(path, {'CLAUDE_PLUGIN_OPTION_LENGTH': '200'})
            self.assertEqual(cfg['length'], 99)

    def test_hook_reads_supplied_native_environment(self):
        output = io.StringIO()
        inject.main(io.StringIO('{"hook_event_name":"SessionStart"}'), output, {
            'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native',
            'CLAUDE_PLUGIN_OPTION_LENGTH': '321'})
        self.assertIn('321', output.getvalue())

    def test_native_mode_declines_command_changes_and_reports_active_values(self):
        import os
        from unittest.mock import patch
        import pace
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'HUMAN_PACE_CONFIG': str(Path(directory) / 'config.json'),
            'CLAUDE_PLUGIN_OPTION_CONFIGURATIONSOURCE': 'native',
            'CLAUDE_PLUGIN_OPTION_LENGTH': '321'}):
            self.assertIn('length 321', pace.run([]))
            self.assertIn('Configure options', pace.run(['length', '10']))
            self.assertFalse((Path(directory) / 'config.json').exists())

from analytics_test_support import isolated_analytics
setUpModule, tearDownModule = isolated_analytics()
