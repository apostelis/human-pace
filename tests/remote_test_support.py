import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pace_analytics as analytics
import pace_config as pc
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
RELEASE = {'endpoint': 'https://collector.example.test', 'operator': 'Test operator',
           'contact': 'test@example.test', 'notice_version': 1}
def prompt(identity='a' * 32, session='b' * 64, sequence=1, cfg=None, day='2026-10-08'):
    import uuid
    cfg = pc.defaults() if cfg is None else cfg
    return dict(schema_version=1, event_id=uuid.uuid4().hex, event='prompt_observed', day=day,
                installation_id=identity, plugin_version='0.10.0', integration='claude',
                source='hook', session_key=session, prompt_sequence=sequence if session else None,
                config_source='commands', enabled=any(cfg[k] for k in pc.SWITCHES) or cfg['length'] > 0,
                **analytics.config_identity(cfg))
