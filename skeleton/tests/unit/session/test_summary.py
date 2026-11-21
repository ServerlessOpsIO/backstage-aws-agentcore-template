"""Unit tests for what the model is told about the session."""

import pytest

import example
from session.record import Record
from session.summary import END_WARNING, NO_SESSION, NOTES_RULE, summarise

ANA, BEN = "Ana Souza", "Ben Okafor"


@pytest.fixture
def session():
    record = Record.start(example.SKILL, example.SCHEMA, "Login service", ANA, "2026-11-22")
    record.complete_stage()
    record.add_item("part", {"name": "API"})
    record.complete_stage()
    record.add_item("finding", {"part": "P1", "text": "No rate limit"})
    return record


def test_no_session_is_said_plainly():
    assert summarise(None) == NO_SESSION


def test_the_summary_gives_the_session_its_stages_and_its_people(session):
    text = summarise(session)
    assert f'Session: {example.SKILL}, on the system "Login service", in progress.' in text
    assert ("Stages: scope (complete), parts (complete), findings (in progress), rating (not started), "
            "plan (not started), report (not started). Current stage: findings.") in text
    assert f"Participants: {ANA}." in text


def test_every_entry_is_given_with_its_identifier(session):
    text = summarise(session)
    assert "Parts:\n  P1 name: API" in text
    assert "Findings:\n  F1 part: P1 (API); finding: No rate limit" in text
    assert "Scope:" not in text and "Fixes:" not in text  # nothing recorded of these kinds


def test_what_the_stage_has_still_to_fill_is_listed(session):
    assert "Still to fill" not in summarise(session)
    session.complete_stage()
    assert "Still to fill in during this stage:\n  F1: level" in summarise(session)
    session.update_item("F1", {"level": "high"})
    assert "Still to fill" not in summarise(session)


def test_a_pending_change_and_open_questions_are_shown(session):
    session.add_person(BEN)
    session.request_change("finish")
    session.add_open_question("Who owns the table?")
    text = summarise(session)
    assert "Pending: finish, announced." in text
    assert "Open questions:\n  Q1: Who owns the table?" in text


def test_notes_of_this_stage_are_shown_with_the_rule_and_others_only_counted(session):
    session.give_hint("P1", "who may call it")
    session.add_note("not_raised", "backups")
    here = summarise(session)
    assert NOTES_RULE in here
    assert "H1 hint about P1 (API) (not taken up): who may call it" in here
    assert "N1 note (not_raised) about the stage: backups" in here

    session.complete_stage()
    later = summarise(session)
    assert NOTES_RULE not in later and "backups" not in later and "who may call it" not in later
    assert "Hints already given in other stages: Findings: P1 (API)." in later
    assert "Notes kept in other stages: 1." in later


def test_held_findings_are_counted_and_not_described():
    record = Record.start(example.SKILL, example.SCHEMA, "Shop", ANA, "2026-11-22")
    record.add_finding("differs", "shop", "README.md", "There is a flamingo queue.", ["README.md"])
    text = summarise(record)
    assert "Repository findings held back until the Parts stage is complete: 1." in text
    assert "flamingo" not in text


def test_after_the_notes_the_model_is_told_changes_are_marked(session):
    session.request_change("finish")
    session.next_turn()
    session.resolve_change(True)
    session.add_person(BEN)
    text = summarise(session)
    assert "The facilitator's notes have been posted." in text
    assert f"Joined after the session: {BEN}." in text and "finished." in text


def test_repositories_and_the_thread_s_end_are_given_with_or_without_a_session(session):
    repositories = [{"name": "shop", "listed": True, "filesRead": ["README.md"]},
                    {"name": "other", "listed": False}]
    for record in (None, session):
        text = summarise(record, repositories, "2026-11-29 10:00", warn_end=True)
        assert "Repositories listed: shop (1 files read)." in text and "other" not in text
        assert "This thread stops being answered at 2026-11-29 10:00 (UTC)." in text
        assert text.endswith(END_WARNING)
