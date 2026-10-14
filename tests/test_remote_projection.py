import unittest
from remote_test_support import NOW, pc, analytics
import pace_remote_projection as p
import pace_remote_contract as c
class ProjectionTest(unittest.TestCase):
    def test_identifier_and_timestamp_exclusion(self):
        local=analytics.make_event('prompt_observed',now=NOW,integration='claude',source='hook',session_key='a'*64,cfg=pc.defaults(),config_source='commands',enabled=True)
        remote=p.project(local,identity='b'*32,secret=b'c'*32,sequence=1,previous=None)
        raw=c.encode_event(remote)
        self.assertNotIn(local['event_id'].encode(),raw);self.assertNotIn(local['session_key'].encode(),raw)
        self.assertNotIn(b'timestamp',raw);self.assertEqual(remote['day'],'2026-10-08')
    def test_no_preconsent_change_and_notes(self):
        local=analytics.make_event('config_observed_changed',now=NOW,integration='claude',source='hook',session_key='a'*64,cfg=pc.defaults(),config_source='commands',previous_settings={**pc.defaults(),'length':300})
        self.assertIsNone(p.project(local,identity='b'*32,secret=b'c'*32,sequence=None,previous=None))
        with self.assertRaises(c.ContractError):p.project({**local,'note':'secret'},identity='b'*32,secret=b'c'*32,sequence=None,previous=pc.defaults())
