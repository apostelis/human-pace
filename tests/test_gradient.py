import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import inject
import pace
import pace_config as pc
import render_gradient


class GradientTest(unittest.TestCase):
    def test_commands_persist_validate_and_reset(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'HUMAN_PACE_CONFIG': str(Path(directory) / 'config.json')}):
            self.assertEqual(pc.load_config()[0]['bionicGradient'], 'off')
            for mode in pc.GRADIENTS:
                self.assertIn('Applies from', pace.run(['experimental', 'gradient', mode]))
                self.assertEqual(pc.load_config()[0]['bionicGradient'], mode)
            before = pc.load_config()[0]
            self.assertEqual(pace.run(['experimental', 'gradient', 'invalid']), pace.USAGE)
            self.assertEqual(pc.load_config()[0], before)
            pace.run(['experimental', 'gradient', 'both'])
            pace.run(['preset', 'off'])
            cfg = pc.load_config()[0]
            self.assertEqual(inject.build_rules(cfg), '')
            self.assertEqual(cfg['bionicGradient'], 'both')
            self.assertNotIn('bionicGradient', pace.effective_setting(cfg))
            pace.run(['reset'])
            self.assertEqual(pc.load_config()[0]['bionicGradient'], 'off')

    def test_rules_only_when_enabled_and_unsupported_surface_falls_back(self):
        self.assertNotIn('Experimental', inject.build_rules(pc.defaults()))
        rules = inject.build_rules({**pc.defaults(), 'bionicGradient': 'both'})
        self.assertIn('Experimental bionic gradient: both', rules)
        self.assertIn('otherwise use the selected Markdown bionic approach', rules)
        self.assertIn('bionicGradient', pc.validate({'bionicGradient': []})[1])

    def test_renderer_escapes_input_and_weights_decrease(self):
        rendered = render_gradient.render('<script>alert("x")</script> reading', 'weight')
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;', rendered)
        self.assertIn('font-weight:800', rendered)
        self.assertIn('font-weight:400', rendered)
        self.assertIn('hp-word hp-both', render_gradient.render('reading', 'both'))
        self.assertIn('class="hp-color"', render_gradient.render('reading', 'color'))
        with self.assertRaises(ValueError):
            render_gradient.render('reading', 'invalid')

from analytics_test_support import isolated_analytics
setUpModule, tearDownModule = isolated_analytics()
