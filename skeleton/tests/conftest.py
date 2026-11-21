"""Test setup that must run before the agent module is imported, and shared fixtures."""

import os

# main.py refuses to start without MODEL_ID. The tests replace the model with a
# fake, so any value works here.
os.environ.setdefault("MODEL_ID", "test.provider.model")
{%- if values.enable_slack_app %}

from collections import namedtuple
{%- endif %}

import pytest


@pytest.fixture
def state():
    """Stand in for the agent's state."""
    import example
    return example.FakeState()


@pytest.fixture
def test_skill(monkeypatch):
    """Give the agent the tests' own skill in place of its real ones."""
    import example
    import loader
    monkeypatch.setattr(loader, "SKILLS", example.SKILLS)
    return example.SKILLS[example.SKILL]
{%- if values.enable_slack_app %}


@pytest.fixture()
def lambda_function_context():
    """Return a factory for the context object Lambda passes to a handler."""
    def _factory(function_name: str, object_name: str = 'LambdaContext'):
        context_info = {
            'aws_request_id': '00000000-0000-0000-0000-000000000000',
            'function_name': function_name,
            'invoked_function_arn': f'arn:aws:lambda:us-east-1:012345678910:function:{function_name}',
            'memory_limit_in_mb': 128,
        }
        Context = namedtuple(object_name, context_info.keys())
        return Context(*context_info.values())
    return _factory
{%- endif %}
