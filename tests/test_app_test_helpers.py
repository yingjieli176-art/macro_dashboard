"""Protect isolated app fixtures against startup I/O and cross-test mutation."""
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from app_test_helpers import load_functions


class AppFixtureIsolationTests(unittest.TestCase):
    def test_loading_a_function_does_not_run_streamlit_startup(self):
        ns = load_functions({'chart_height'}, {'compact_mode': False})
        self.assertEqual(ns['chart_height'](300,420),420)
        ns['compact_mode'] = True
        self.assertEqual(ns['chart_height'](300,420),300)

    def test_stripping_decorators_cannot_poison_another_fixture(self):
        # Both callers reuse a parsed source; only the first strips decorators.
        plain = load_functions({'_poll_source_completion'}, {}, strip_decorators=True)
        self.assertTrue(callable(plain['_poll_source_completion']))
        fragment = Mock(return_value=lambda function: function)
        decorated = load_functions({'_poll_source_completion'}, {'st':SimpleNamespace(fragment=fragment)})
        fragment.assert_called_once_with(run_every=2, key='source_completion')
        self.assertTrue(callable(decorated['_poll_source_completion']))


if __name__ == '__main__': unittest.main()
