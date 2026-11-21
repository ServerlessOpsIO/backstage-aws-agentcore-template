"""What the unit tests of the session engine share: a skill of their own and a fake state.

The engine is tested against the skill in tests/unit/support/skills, not against
the agent's own skills, so that changing or replacing a skill in src/agent/skills
does not break these tests.
"""

import json
from pathlib import Path

import loader

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL = "test-review"
SKILLS = loader.load_skills(SKILLS_DIR)
SCHEMA = SKILLS[SKILL].schema


class FakeState:
    """Stands in for the agent's state. It refuses anything that is not JSON, as the real one does."""

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        json.dumps(value)
        self.values[key] = value
