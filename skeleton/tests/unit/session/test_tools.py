"""Unit tests for the tools the model calls."""

import asyncio
import logging

import pytest

import example
from session import record as rec
from session import tools
from session.tools import Turn

ANA, BEN = "Ana Souza", "Ben Okafor"


def turn_for(state, speaker=ANA, kind=tools.DIRECT_MESSAGE, ends=None):
    return Turn(state, speaker, example.SKILLS, kind, ends, today="2026-11-22", agent_name="Dee")


def load(state):
    return rec.load(state, example.SKILLS)


def next_message(state, speaker=ANA, **kwargs):
    """Move to the next message the way main.py does, and return its Turn."""
    session = load(state)
    session.next_turn()
    session.add_person(speaker)
    rec.save(state, session)
    return turn_for(state, speaker, **kwargs)


@pytest.fixture
def turn(state):
    t = turn_for(state)
    t.start_session(example.SKILL, "Login service")
    return t


@pytest.fixture
def reviewed(turn):
    """A session with a part and a finding, in the findings stage."""
    turn.complete_stage()
    turn.add_item("part", {"name": "API"})
    turn.complete_stage()
    turn.add_item("finding", {"part": "P1", "text": "No rate limit"})
    return turn


def call(tool, **arguments):
    """Call a tool made from session.yaml the way the framework does, and return its words."""
    async def run():
        return [event async for event in tool.stream({"toolUseId": "t1", "input": arguments}, {})]
    result = asyncio.run(run())[-1].tool_result
    assert result["toolUseId"] == "t1" and result["status"] == "success"
    return result["content"][0]["text"]


# --- which tools are offered -----------------------------------------------------


def test_without_a_session_only_starting_and_reading_are_offered():
    assert tools.tools_for(None) == ("start_session", "list_repository_files", "read_repository_file")


def test_each_stage_offers_its_own_recording_tools(turn, state):
    offered = set(tools.tools_for(load(state)))
    assert {"add_scope_item", "update_scope_item"} <= offered and "add_part" not in offered
    assert set(tools.SESSION_TOOLS) | set(tools.REPOSITORY_TOOLS) <= offered
    assert "start_session" not in offered

    turn.complete_stage()
    offered = set(tools.tools_for(load(state)))
    assert {"add_part", "update_part"} <= offered and "add_scope_item" not in offered


def test_a_stage_that_only_fills_offers_the_update_tool_alone(reviewed, state):
    reviewed.complete_stage()
    offered = set(tools.tools_for(load(state)))
    assert "update_finding" in offered and "add_finding" not in offered


def test_after_the_end_every_entry_can_still_be_changed_and_a_new_session_started(turn, state):
    turn.request_change("finish")
    next_message(state).resolve_change(True)
    offered = set(tools.tools_for(load(state)))
    assert {"start_session", "write_document", "remove_item", "add_open_question"} <= offered
    assert {"add_scope_item", "update_part", "add_finding", "update_fix"} <= offered
    assert not {"complete_stage", "give_hint", "add_note", "request_change"} & offered


def test_the_tools_put_in_place_are_exactly_those_offered(turn, state):
    static = tools.make_tools(turn, extra={"list_repository_files": lambda repository: ""})
    assert set(static) == set(tools.STATIC_TOOLS) | {"list_repository_files"}

    none = tools.current_tools(turn_for(example.FakeState()), static, None)
    assert set(none) == {"start_session", "list_repository_files"}  # only what exists is offered

    current = tools.current_tools(turn, static, load(state))
    assert {"add_scope_item", "update_scope_item", "complete_stage"} <= set(current)
    assert "add_part" not in current and "start_session" not in current


# --- starting ------------------------------------------------------------------------


def test_starting_gives_the_opening_from_the_skill(state):
    said = turn_for(state).start_session(example.SKILL, "Login service")
    assert said.startswith('Session started on "Login service".')
    assert "the 6 stages: scope, parts, findings, rating, plan, report" in said
    assert "you will not name findings" in said  # the skill's own point
    assert "Then name the scope stage" in said
    assert "stay quiet" not in said and "stops being answered" not in said
    assert load(state)["participants"] == [ANA]


def test_in_a_thread_the_opening_covers_quiet_guests_and_the_end(state):
    said = turn_for(state, kind=tools.CHANNEL_THREAD, ends="2026-11-29 10:00").start_session(
        example.SKILL, "Login service")
    assert "you may stay quiet" in said and "full members" in said
    assert "stops being answered at 2026-11-29 10:00 (UTC)" in said


def test_the_only_skill_is_used_when_none_or_a_wrong_one_is_named(state):
    assert turn_for(state).start_session("", "Login service").startswith("Session started")
    assert load(state)["skill"] == example.SKILL


def test_with_several_skills_one_must_be_named(state):
    skills = {"one": example.SKILLS[example.SKILL], "two": example.SKILLS[example.SKILL]}
    said = Turn(state, ANA, skills, today="2026-11-22").start_session("three", "Login service")
    assert said == "Not done. Say which skill the session uses. One of: one, two."
    assert state.get(rec.KEY_SESSION) is None


def test_a_session_in_progress_is_not_replaced(turn, state):
    said = turn.start_session(example.SKILL, "Another system")
    assert said.startswith('Not done. A session on "Login service" is in progress')
    assert load(state)["subject"] == "Login service"


def test_an_ended_session_is_replaced_only_after_a_warning_on_an_earlier_message(turn, state):
    turn.request_change("abandon")
    ended = next_message(state)
    ended.resolve_change(True)
    assert "replaces it" in ended.start_session(example.SKILL, "Shop")
    assert "replaces it" in ended.start_session(example.SKILL, "Shop")  # same message: still a warning
    assert load(state)["subject"] == "Login service"

    assert next_message(state).start_session(example.SKILL, "Shop").startswith("Session started")
    assert load(state)["subject"] == "Shop" and load(state)["items"] == []


def test_starting_forgets_which_repository_files_were_read(state):
    rec.save_repositories(state, [{"name": "shop", "listed": True, "filesRead": ["README.md"]}])
    turn_for(state).start_session(example.SKILL, "Shop")
    assert rec.load_repositories(state)[0]["filesRead"] == []


# --- the tools made from session.yaml ----------------------------------------------------


def test_each_kind_has_an_add_and_an_update_tool_with_its_fields(turn):
    made = turn.entry_tools(example.SCHEMA)
    assert set(made) == {f"{verb}_{kind}" for verb in ("add", "update") for kind in example.SCHEMA.kinds}

    add = made["add_finding"].tool_spec
    assert add["name"] == "add_finding"
    assert add["description"] == "Record a finding a participant named. Never one of your own."
    schema = add["inputSchema"]["json"]
    assert schema["required"] == ["part", "text"]
    assert schema["properties"]["level"]["enum"] == ["high", "low"]
    assert schema["properties"]["level"]["description"] == "How serious the participants say it is."
    assert "identifier of a part, such as P1" in schema["properties"]["part"]["description"]

    update = made["update_fix"].tool_spec["inputSchema"]["json"]
    assert update["required"] == ["id"] and "such as FX1" in update["properties"]["id"]["description"]
    assert update["properties"]["findings"] == {
        "type": "array", "items": {"type": "string"},
        "description": "Addresses. The identifiers of each finding, such as F1.",
    }
    assert update["properties"]["agreed_by"]["type"] == "array"


def test_an_add_tool_records_and_asks_for_it_to_be_read_back(turn, state):
    made = turn.entry_tools(example.SCHEMA)
    said = call(made["add_scope_item"], kind="included", text="the API")
    assert said == ("Recorded as S1, a scope item: kind: Included; text: the API. "
                    "Say this back to the participants in one line, with the identifier.")
    assert load(state).item("S1")["values"]["text"] == "the API"
    assert turn.tool_calls == 2  # start_session, then this


def test_an_update_tool_changes_only_its_own_kind(reviewed, state):
    made = reviewed.entry_tools(example.SCHEMA)
    assert "F1, a finding: part: P1 (API); finding: No rate limit; level: High." in call(
        made["update_finding"], id="F1", level="high")
    assert call(made["update_part"], id="F1", name="x") == "Not done. F1 is a finding, not a part."
    assert load(state).item("F1")["values"]["level"] == "high"


def test_a_refused_call_answers_with_the_reason_and_changes_nothing(reviewed, state):
    made = reviewed.entry_tools(example.SCHEMA)
    assert call(made["add_finding"], part="P7", text="x") == "Not done. There is no entry P7."
    assert call(made["add_finding"], text="x") == "Not done. The part is missing."
    assert len(load(state)["items"]) == 2


def test_a_tool_without_a_session_says_so(state):
    assert turn_for(state).complete_stage() == "Not done. There is no session. Start one first."


def test_a_fault_is_answered_and_logged_by_its_type_alone(turn, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("the flamingo detail")
    monkeypatch.setattr(rec.Record, "add_open_question", broken)
    with caplog.at_level(logging.ERROR, logger="agent"):
        assert turn.add_open_question("Who owns it?") == tools.SOMETHING_WENT_WRONG
    assert "RuntimeError" in caplog.text and "flamingo" not in caplog.text


# --- moving through the session ------------------------------------------------------------


def test_completing_a_stage_names_the_next(turn):
    assert turn.complete_stage() == (
        "The scope stage is complete. Now in the parts stage. Name it and ask its first question."
    )


def test_completing_a_stage_says_once_what_was_left_unfilled(reviewed):
    reviewed.complete_stage()
    said = reviewed.complete_stage()
    assert "Left unfilled: F1: level." in said and "supply nothing yourself" in said


def test_completing_the_stage_that_holds_findings_hands_them_over(turn, state):
    turn.complete_stage()
    session = load(state)
    session.add_finding("differs", "shop", "README.md", "There is a queue.", ["README.md"])
    rec.save(state, session)
    said = turn.complete_stage()
    assert "Report these repository findings now" in said
    assert "[differs] shop/README.md: There is a queue." in said


def test_completing_the_last_stage_asks_about_finishing(turn):
    for _ in range(5):
        turn.complete_stage()
    assert turn.complete_stage().endswith(
        "That was the last stage. Ask whether the participants want to finish.")


def test_going_to_a_stage_and_a_stage_that_does_not_exist(turn, state):
    assert turn.go_to_stage("findings") == "Now in the findings stage. Say so."
    assert turn.go_to_stage("nowhere").startswith("Not done. The stage must be one of: scope, parts")
    assert load(state)["stage"] == "findings"


def test_one_person_skips_at_once(turn, state):
    assert turn.request_change("skip_stage") == (
        "Skipped. Now in the parts stage. Name it and ask its first question.")
    assert load(state)["stages"]["scope"] == "skipped"


def test_a_group_s_skip_waits_for_the_next_message(turn, state):
    assert next_message(state, BEN).request_change("skip_stage").startswith("Pending.")
    assert load(state)["stage"] == "scope"
    assert next_message(state).resolve_change(True).startswith("Skipped. Now in the parts stage.")


def test_a_finish_is_refused_on_the_message_that_asked_and_done_on_the_next(turn, state):
    assert "about to be posted" in turn.request_change("finish")
    assert turn.resolve_change(True).startswith("Not done. It was only just announced.")
    assert turn.documents == []

    later = next_message(state)
    assert later.resolve_change(True).startswith("The session is finished.")
    assert [d["filename"] for d in later.documents] == [
        "review-login-service.md", "facilitator-notes-login-service.md"]
    assert later.documents[1]["markdown"].startswith("# Facilitator's notes: Login service")
    assert "Dee's own observations" in later.documents[1]["markdown"]


def test_an_objection_drops_the_finish(turn, state):
    turn.request_change("finish")
    later = next_message(state)
    assert later.resolve_change(False).startswith("Dropped.")
    assert later.documents == [] and load(state).in_progress


# --- the document ------------------------------------------------------------------------------


def test_the_document_part_way_comes_without_the_notes(reviewed):
    assert "as it stands" in reviewed.write_document()
    assert [d["filename"] for d in reviewed.documents] == ["review-login-service.md"]
    assert reviewed.documents[0]["title"] == "Review: Login service"
    assert "> Status: **In progress**." in reviewed.documents[0]["markdown"]
    assert "led by Dee, an AI agent" in reviewed.documents[0]["markdown"]


def test_asking_twice_attaches_each_document_once(reviewed):
    reviewed.write_document()
    reviewed.write_document()
    assert len(reviewed.documents) == 1


def test_after_the_end_the_document_comes_with_the_notes(turn, state):
    turn.request_change("abandon")
    next_message(state).resolve_change(True)
    later = next_message(state)
    assert "facilitator's notes are attached" in later.write_document()
    assert len(later.documents) == 2


# --- hints, notes, questions, removing --------------------------------------------------------------


def test_a_hint_is_recorded_before_it_is_given_and_a_second_is_refused(reviewed, state):
    assert reviewed.give_hint("who may call it", "P1").startswith("Noted as H1. Now give the hint")
    refused = reviewed.give_hint("something else", "P1")
    assert refused.startswith("Not done. A hint has already been given") and "add_note" in refused
    assert reviewed.hint_taken_up("H1") == "Noted."
    assert load(state)["hints"][0]["takenUp"] is True


def test_a_note_is_kept_and_not_to_be_mentioned(reviewed, state):
    assert reviewed.add_note("questioned_kept", "low seemed low", "F1") == "Noted. Do not mention it."
    assert load(state)["notes"][0]["about"] == "F1"


def test_an_open_question_is_read_back(turn):
    assert turn.add_open_question("Who owns it?").startswith(
        "Recorded as Q1, an open question: Who owns it?.")


def test_removing_says_so_and_refuses_what_is_named(reviewed, state):
    assert reviewed.remove_item("P1") == "Not done. It is named by F1. Change or remove those first."
    assert reviewed.remove_item("F1") == "Removed F1. Say so."
    assert [item["id"] for item in load(state)["items"]] == ["P1"]
