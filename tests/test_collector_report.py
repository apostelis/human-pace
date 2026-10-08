import unittest
from datetime import date
from remote_test_support import prompt, pc, analytics
from collector import report
class ReportTest(unittest.TestCase):
    def test_prompt_share_and_installation_adoption(self):
        events=[prompt(sequence=n) for n in range(1,10)]
        events.append(prompt(identity='c'*32,session='d'*64,cfg={**pc.defaults(),'length':300}))
        s=report.summarize(events,start=date(2026,10,8),end=date(2026,10,8))
        key=analytics.config_identity(pc.defaults())['format_config_id']
        self.assertEqual(s['configurations'][key]['prompt_share'],(9,10))
        self.assertEqual(s['configurations'][key]['installation_adoption'],(1,2))
        self.assertNotIn(key,report.render(s))
    def test_transition_gaps_and_unknown_sessions(self):
        other={**pc.defaults(),'length':300}
        events=[prompt(sequence=1),prompt(sequence=2),prompt(sequence=4,cfg=other),prompt(sequence=5),prompt(session=None)]
        s=report.summarize(events,start=date(2026,10,8),end=date(2026,10,8))
        self.assertEqual(sum(x['count'] for x in s['transitions'].values()),1)
        self.assertEqual(s['unknown_session_prompts'],1)
    def test_mature_cohort_and_duplicate_events(self):
        first=prompt(day='2026-09-24');ret=prompt(day='2026-10-02',sequence=2)
        immature=prompt(identity='c'*32,session='d'*64,day='2026-10-01')
        s=report.summarize([first,ret,ret,immature],start=date(2026,9,24),end=date(2026,10,8))
        self.assertEqual(s['cohort_return'],(1,1));self.assertEqual(s['prompt_count'],3)
    def test_suppress_complement_and_show_supported_configs(self):
        events=[prompt(identity=f'{n:032x}',session=f'{n:064x}') for n in range(1,6)]
        s=report.summarize(events,start=date(2026,10,8),end=date(2026,10,8))
        key=analytics.config_identity(pc.defaults())['format_config_id']
        self.assertIn(key,report.render(s))
        events.append(prompt(identity='f'*32,session='e'*64,cfg={**pc.defaults(),'length':300}))
        s=report.summarize(events,start=date(2026,10,8),end=date(2026,10,8))
        self.assertNotIn(key,report.render(s));self.assertIn('suppressed',report.render(s))
    def test_off_denominator_empty_and_separate_changes(self):
        off={**pc.defaults(),**{k:False for k in pc.SWITCHES},'length':0}
        e=prompt(cfg=off);s=report.summarize([prompt(),e],start=date(2026,10,8),end=date(2026,10,8))
        self.assertEqual(s['active_installations'],1);self.assertEqual(s['enabled_prompt_count'],1)
        self.assertIn('not enough data',report.render(report.summarize([],start=date(2026,10,8),end=date(2026,10,8))))
