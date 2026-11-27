"""Unit tests for the written document and the facilitator's notes."""

import pytest

import example
from session import render
from session.record import Record

ANA, BEN = "Ana Souza", "Ben Okafor"
TODAY = "2026-11-23"


@pytest.fixture
def session():
    record = Record.start(example.SKILL, example.SCHEMA, "Login service", ANA, "2026-11-22")
    record.add_person(BEN)
    record.add_item("scope_item", {"kind": "included", "text": "the API"})
    record.complete_stage()
    record.add_item("part", {"name": "API", "description": "Signs people in"})
    record.add_item("part", {"name": "Table"})
    record.complete_stage()
    record.add_item("finding", {"part": "P1", "text": "No rate limit", "level": "high"})
    record.complete_stage()
    record.complete_stage()
    record.add_item("fix", {"text": "Add a limit", "findings": ["F1"], "agreed_by": [ANA, BEN],
                            "owner": "Ben"})
    return record


def document(record, repositories=None):
    return render.written_document(record, repositories, TODAY, "Dee")


def section(text, heading):
    return text.split(f"\n{heading}\n\n", 1)[1].split("\n## ", 1)[0].strip()


def finish(record):
    record.request_change("finish")
    record.next_turn()
    record.resolve_change(True)


def test_the_document_has_a_section_for_each_kind_in_order(session):
    text = document(session)
    assert text.startswith("# Review: Login service\n\n> Status: **In progress**.")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## Summary", "## Scope", "## Parts", "## Findings", "## Fixes",
                        "## Open questions", "## Method"]
    assert headings == render.headings(example.SCHEMA)


def test_the_summary_says_what_who_and_how_much(session):
    summary = section(document(session), "## Summary")
    assert "- **System**: Login service" in summary
    assert f"- **Date**: {TODAY}" in summary and "- **Session started**: 2026-11-22" in summary
    assert f"- **Participants**: {ANA}, {BEN}" in summary
    assert "- **Recorded**: Scope 1, Parts 2, Findings 1, Fixes 1" in summary
    assert "Joined after" not in summary


def test_a_table_has_a_column_for_each_field_and_a_dash_for_what_is_empty(session):
    assert section(document(session), "## Parts") == (
        "| ID | Name | Description |\n|---|---|---|\n"
        "| P1 | API | Signs people in |\n| P2 | Table | — |"
    )
    assert "| F1 | P1 (API) | No rate limit | High |" in section(document(session), "## Findings")


def test_a_grouped_list_has_a_heading_for_each_choice(session):
    assert section(document(session), "## Scope") == (
        "**Included**\n\n- S1: the API\n\n**Excluded**\n\nNone recorded."
    )


def test_a_list_gives_the_first_text_then_the_other_fields(session):
    assert section(document(session), "## Fixes") == (
        f"- FX1: Add a limit (Addresses: F1; Agreed by: {ANA}, {BEN}; Owner: Ben)"
    )


def test_what_people_wrote_cannot_break_the_layout(session):
    session.add_item("part", {"name": "a | b\n# heading", "description": "> quote"})
    parts = section(document(session), "## Parts")
    assert "| P3 | a \\| b # heading | \\> quote |" in parts


def test_stages_skipped_or_not_reached_are_said(session):
    session.go_to_stage("findings")
    session.request_change("skip_stage")
    session.next_turn()
    session.resolve_change(True)
    text = document(session)
    assert "> Skipped: Findings." in text
    assert section(text, "## Findings").startswith("Skipped: Findings.\n\n| ID |")
    assert "> Not finished: Plan." in text  # the plan stage was left in progress


def test_a_stage_never_started_is_marked_in_its_section():
    record = Record.start(example.SKILL, example.SCHEMA, "Shop", ANA, "2026-11-22")
    text = document(record)
    assert section(text, "## Parts") == "Not finished: Parts.\n\nNone recorded."
    assert "> Not finished: Report." not in text  # the last stage is this document


@pytest.mark.parametrize("ending, word", [("finish", "Finished"), ("abandon", "Abandoned")])
def test_the_status_says_how_the_session_ended(session, ending, word):
    session.request_change(ending)
    session.next_turn()
    session.resolve_change(True)
    assert f"> Status: **{word}**." in document(session)


def test_a_session_with_every_stage_complete_is_complete(session):
    session.complete_stage()
    finish(session)
    assert "> Status: **Complete**." in document(session)


def test_changes_after_the_notes_are_marked(session):
    finish(session)
    session.add_person("Cai Lin")
    session.update_item("F1", {"level": "low"})
    session.remove("P2")
    text = document(session)
    assert "| F1† |" in text and "| P1 |" in text
    assert "Entries marked † were added or changed after" in text
    assert "> Removed after the facilitator's notes were posted: P2." in text
    assert "- **Joined after the session**: Cai Lin" in text


def test_open_questions_are_numbered(session):
    assert section(document(session), "## Open questions") == "None."
    session.add_open_question("Who owns the table?")
    assert section(document(session), "## Open questions") == "1. Who owns the table?"


def test_repository_files_have_a_section_only_when_some_were_read(session):
    assert "## Repository files read" not in document(session)
    repositories = [{"name": "shop", "commit": "0123456789abcdef", "filesRead": ["README.md"],
                     "unread": "too_large"}]
    files = section(document(session, repositories), "## Repository files read")
    assert files == "- `shop@0123456`: `README.md`\n\n`shop` could not be read in full."


def test_the_method_names_the_agent_and_adds_the_skill_s_words(session):
    method = section(document(session), "## Method")
    assert method.startswith("> This document was made in a session led by Dee, an AI agent.")
    assert method.endswith("Checked by hand.")


def test_the_same_record_always_gives_the_same_document(session):
    assert document(session) == document(session)


def test_file_names_come_from_the_subject(session):
    assert render.filename(session, render.DOCUMENT) == "review-login-service.md"
    assert render.filename(session, render.NOTES) == "facilitator-notes-login-service.md"
    assert render.title(session, render.DOCUMENT) == "Review: Login service"
    session.data["subject"] = "¡¡¡"
    assert render.filename(session, render.DOCUMENT) == "review.md"
    session.data["subject"] = "x" * 200
    assert len(render.filename(session, render.DOCUMENT)) <= 63


def test_the_notes_hold_hints_not_taken_up_and_every_note(session):
    taken = session.give_hint("P1", "who may call it")
    session.hint_taken_up(taken["id"])
    session.give_hint("P2", "who may read it")
    session.give_hint("", "the admin pages")
    session.add_note("not_raised", "backups", "P2")
    session.add_note("questioned_kept", "high seemed too high", "F1")
    notes = render.facilitator_notes(session, "Dee")

    assert notes.startswith("# Facilitator's notes: Login service\n\n> These are Dee's own observations")
    assert section(notes, "## Hinted at, and not taken up") == (
        "- Plan, P2 (Table): who may read it\n- Plan, Plan: the admin pages"
    )
    assert section(notes, "## Not raised in the session") == (
        "- Plan, P2 (Table): backups (not raised in the session)"
    )
    assert section(notes, "## Questioned, and kept") == "- F1: high seemed too high"
    assert "who may call it" not in notes


def test_empty_notes_say_nothing_in_each_part(session):
    notes = render.facilitator_notes(session, "Dee")
    assert notes.count("\n\nNothing.") == 3


def test_a_noun_is_given_its_article():
    assert render.a("option") == "an option" and render.a("decision") == "a decision"
