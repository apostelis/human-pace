"""Module-level isolation for tests that exercise plugin entry points."""
import os
import tempfile
from unittest.mock import patch


def isolated_analytics():
    state = {}
    def setup():
        state['tmp'] = tempfile.TemporaryDirectory()
        state['env'] = patch.dict(os.environ, {'HUMAN_PACE_ANALYTICS_DIR': state['tmp'].name + '/analytics'})
        state['env'].start()
    def teardown():
        state['env'].stop()
        state['tmp'].cleanup()
    return setup, teardown
