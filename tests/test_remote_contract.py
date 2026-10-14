import copy
import json
import unittest
from remote_test_support import prompt, pc
import pace_remote_contract as c
class ContractTest(unittest.TestCase):
    def test_valid_prompt_and_unknown_fields(self):
        e = prompt()
        self.assertEqual(c.validate_event(e), e)
        for k, v in [('note', 'secret'), ('schema_version', 2), ('prompt_sequence', True),
                     ('day', '2026-10-08T00:00:00Z'), ('timestamp', 'secret'),
                     ('installation_id', '../path'), ('config_id', 'wrong')]:
            with self.subTest(k=k), self.assertRaises(c.ContractError):
                c.validate_event({**e, k: v})
    def test_duplicate_keys_depth_and_nonfinite(self):
        for raw in [b'{"schema_version":1,"schema_version":2}', b'{"x":NaN}',
                    b'[' * 20 + b'0' + b']' * 20]:
            with self.assertRaises(c.ContractError):
                c.strict_json(raw, max_bytes=1000)
    def test_all_types_and_config_validation(self):
        for kind, fields in [('session_observed', {}), ('config_saved', {'previous_settings': {**pc.defaults(), 'length':300}, 'changed_fields':['length']}),
            ('config_observed_changed', {'previous_settings':{**pc.defaults(), 'length':300},'changed_fields':['length']}),
            ('command_invoked', {'operation':'rate','outcome':'success'}), ('rating_submitted', {'score':5}),
            ('settings_error', {'category':'save_failed','invalid_fields':[]})]:
            e = prompt(); e.pop('prompt_sequence'); e.pop('enabled'); e['event'] = kind; e.update(fields)
            self.assertEqual(c.validate_event(e), e)
        e = prompt(); e['settings']['length'] = True
        with self.assertRaises(c.ContractError): c.validate_event(e)
    def test_batch_bounds_and_null_sequence(self):
        self.assertEqual(json.loads(c.encode_batch([prompt(session=None)]))['schema_version'], 1)
        with self.assertRaises(c.ContractError): c.encode_batch([prompt()] * 101)
        with self.assertRaises(c.ContractError): c.validate_event({**prompt(session=None), 'prompt_sequence':1})
