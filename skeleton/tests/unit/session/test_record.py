"""Unit tests for the session record: the rules that code keeps."""

import pytest

import example
from session import record as rec
from session.record import Record, Refused

ANA, BEN = "Ana Souza", "Ben Okafor"


def new(speaker=ANA):
    return Record.start(example.SKILL, example.SCHEMA, "Login service", speaker, "2026-11-22")


@pytest.fixture
def session():
    return new()


@pytest.fixture
def reviewed(session):
    """A session with two parts and a finding, in the plan stage."""
    session.complete_stage()
    session.add_item("part", {"name": "API"})
    session.add_item("part", {"name": "Table", "description": "Holds users"})
    session.complete_stage()
    session.add_item("finding", {"part": "P1", "text": "No rate limit"})
    session.complete_stage()
    session.complete_stage()
    return session


# --- starting, and reading back ----------------------------------------------


def test_a_session_starts_in_the_first_stage_with_its_first_speaker(session):
    assert session["skill"] == example.SKILL and session["subject"] == "Login service"
    assert session["stage"] == "scope" and session["stages"]["scope"] == "in_progress"
    assert session["stages"]["parts"] == "not_started"
    assert session["participants"] == [ANA] and session.in_progress
    assert session["findingsReleased"] is False


def test_a_session_needs_a_subject():
    with pytest.raises(Refused, match="system's name"):
        Record.start(example.SKILL, example.SCHEMA, "  ", ANA, "2026-11-22")


def test_a_record_survives_being_stored(reviewed, state):
    rec.save(state, reviewed)
    assert rec.load(state, example.SKILLS).to_dict() == reviewed.to_dict()


@pytest.mark.parametrize("damage", [
    lambda d: d.update(stage="nowhere"),
    lambda d: d.update(status="paused"),
    lambda d: d.pop("items"),
    lambda d: d["stages"].update(removed="complete"),
    lambda d: d["stages"].update(scope="half"),
    lambda d: d.update(turn="2"),
    lambda d: d["items"].append({"id": "Z1", "kind": "gone", "values": {}}),
    lambda d: d.update(skill="a-skill-that-was-removed"),
])
def test_a_record_that_no_longer_fits_counts_as_no_session(damage, session, state):
    data = session.to_dict()
    damage(data)
    state.set(rec.KEY_SESSION, data)
    assert rec.load(state, example.SKILLS) is None


def test_a_stage_the_skill_has_gained_is_added_as_not_started(session, state):
    data = session.to_dict()
    del data["stages"]["rating"]
    state.set(rec.KEY_SESSION, data)
    assert rec.load(state, example.SKILLS)["stages"]["rating"] == "not_started"


def test_no_record_is_no_session(state):
    assert rec.load(state, example.SKILLS) is None


# --- people -------------------------------------------------------------------


def test_a_speaker_is_added_once_and_after_the_end_is_kept_apart(session):
    session.add_person(BEN)
    session.add_person(BEN)
    session.add_person("")
    assert session["participants"] == [ANA, BEN]
    session.data["status"] = rec.FINISHED
    session.add_person("Cai Lin")
    assert session["joinedAfter"] == ["Cai Lin"] and session.people() == [ANA, BEN, "Cai Lin"]


# --- entries -------------------------------------------------------------------


def test_an_entry_gets_the_next_identifier_of_its_kind(session):
    first = session.add_item("scope_item", {"kind": "included", "text": " the API "})
    second = session.add_item("scope_item", {"kind": "excluded", "text": "the site"})
    assert (first["id"], second["id"]) == ("S1", "S2")
    assert first["values"] == {"kind": "included", "text": "the API"}
    assert first["stage"] == "scope" and first["changedAfterNotes"] is False


def test_an_identifier_is_never_used_again(session):
    session.add_item("scope_item", {"kind": "included", "text": "one"})
    session.remove("S1")
    assert session.add_item("scope_item", {"kind": "included", "text": "two"})["id"] == "S2"


@pytest.mark.parametrize("kind, values, problem", [
    ("scope_item", {"kind": "included"}, "The text is missing"),
    ("scope_item", {"kind": "included", "text": "   "}, "The text is missing"),
    ("scope_item", {"kind": "maybe", "text": "x"}, "must be one of: included, excluded"),
    ("scope_item", {"kind": "included", "text": "x", "colour": "red"}, "no colour"),
    ("finding", {"part": "P9", "text": "x"}, "There is no entry P9"),
    ("finding", {"part": "S1", "text": "x"}, "identifier of one part"),
    ("fix", {"text": "x", "findings": []}, "The addresses is missing"),
    ("fix", {"text": "x", "findings": ["F1", "P1"]}, "identifier of one finding"),
    ("fix", {"text": "x", "findings": ["F1"], "agreed_by": ["Nobody Here"]}, "Not in this session: Nobody Here"),
    ("nothing", {"text": "x"}, "no kind of entry called nothing"),
])
def test_an_entry_that_does_not_fit_is_refused(kind, values, problem, reviewed):
    reviewed.add_item("scope_item", {"kind": "included", "text": "the API"})
    with pytest.raises(Refused, match=problem):
        reviewed.add_item(kind, values)


def test_references_and_people_are_kept_as_given(reviewed):
    reviewed.add_person(BEN)
    fix = reviewed.add_item("fix", {"text": "Add a limit", "findings": ["F1"], "agreed_by": [ANA, BEN]})
    assert fix["id"] == "FX1"
    assert fix["values"] == {"text": "Add a limit", "findings": ["F1"], "agreed_by": [ANA, BEN]}


def test_an_entry_is_changed_field_by_field(reviewed):
    reviewed.update_item("F1", {"level": "high"})
    reviewed.update_item("F1", {"text": "No rate limit on sign-in", "level": ""})
    assert reviewed.item("F1")["values"] == {"part": "P1", "text": "No rate limit on sign-in", "level": "high"}


@pytest.mark.parametrize("identifier, values, problem", [
    ("F1", {}, "Nothing to change"),
    ("F1", {"level": "medium"}, "must be one of"),
    ("F9", {"level": "high"}, "There is no entry F9"),
    ("", {"level": "high"}, "identifier is missing"),
])
def test_a_change_that_does_not_fit_is_refused(identifier, values, problem, reviewed):
    with pytest.raises(Refused, match=problem):
        reviewed.update_item(identifier, values)


def test_an_entry_another_names_cannot_be_removed(reviewed):
    reviewed.add_item("fix", {"text": "Add a limit", "findings": ["F1"]})
    with pytest.raises(Refused, match="named by F1"):
        reviewed.remove("P1")
    with pytest.raises(Refused, match="named by FX1"):
        reviewed.remove("F1")
    reviewed.remove("FX1")
    reviewed.remove("F1")
    reviewed.remove("P1")
    assert [item["id"] for item in reviewed["items"]] == ["P2"]


def test_hints_notes_and_findings_cannot_be_removed_and_questions_can(session):
    question = session.add_open_question("Who owns the table?")
    session.remove(question["id"])
    assert session["openQuestions"] == []
    for identifier in ("H1", "N1", "R1"):
        with pytest.raises(Refused, match="cannot be removed"):
            session.remove(identifier)
    with pytest.raises(Refused, match="no open question Q7"):
        session.remove("Q7")


# --- what a stage is meant to fill -----------------------------------------------


def test_what_a_stage_has_not_filled_is_listed(reviewed):
    reviewed.go_to_stage("rating")
    assert reviewed.lacking() == [("F1", ["level"])]
    reviewed.update_item("F1", {"level": "low"})
    assert reviewed.lacking() == []
    assert reviewed.lacking("scope") == []


def test_completing_a_stage_says_what_it_left_unfilled(reviewed):
    reviewed.add_item("fix", {"text": "Add a limit", "findings": ["F1"]})
    done = reviewed.complete_stage()
    assert done["left"] == "plan" and done["entered"] == "report"
    assert done["lacking"] == [("FX1", ["owner"])]


# --- hints and notes ---------------------------------------------------------------


def test_one_hint_for_each_entry_in_each_stage_and_one_about_none(reviewed):
    reviewed.give_hint("P1", "nobody asked who can call it")
    reviewed.give_hint("P2", "nobody asked who can read it")
    reviewed.give_hint("", "a whole area is missing")
    for about in ("P1", ""):
        with pytest.raises(Refused, match="already been given"):
            reviewed.give_hint(about, "another point")
    reviewed.go_to_stage("findings")
    assert reviewed.give_hint("P1", "a point for this stage")["id"] == "H4"
    with pytest.raises(Refused, match="no entry P9"):
        reviewed.give_hint("P9", "x")


def test_a_hint_can_be_marked_as_taken_up(session):
    hint = session.give_hint("", "the admin pages")
    session.hint_taken_up(hint["id"])
    assert session["hints"][0]["takenUp"] is True
    with pytest.raises(Refused):
        session.hint_taken_up("H9")


def test_a_note_is_kept_with_its_stage(reviewed):
    note = reviewed.add_note("questioned_kept", "low seemed too low", "F1")
    assert note == {"id": "N1", "kind": "questioned_kept", "stage": "plan", "about": "F1",
                    "text": "low seemed too low"}
    with pytest.raises(Refused, match="must be one of"):
        reviewed.add_note("gossip", "x")


# --- repository findings -------------------------------------------------------------


def test_a_finding_is_held_until_the_stage_named_for_it_is_complete(session):
    session.complete_stage()
    held = session.add_finding("differs", "shop", "README.md", "There is a queue.", ["README.md"])
    assert held["reported"] is False
    done = session.complete_stage()
    assert [f["id"] for f in done["released"]] == ["R1"] and session["findings"][0]["reported"] is True
    later = session.add_finding("not_mentioned", "shop", "README.md", "There is a cache.", ["README.md"])
    assert later["reported"] is True


def test_a_finding_must_come_from_a_file_that_was_read(session):
    with pytest.raises(Refused, match="has not been read"):
        session.add_finding("differs", "shop", "secrets.txt", "x", ["README.md"])


def test_skipping_the_stage_also_lets_findings_go(session):
    session.complete_stage()
    session.add_finding("differs", "shop", "README.md", "There is a queue.", ["README.md"])
    assert session.request_change("skip_stage") == "applied"
    assert [f["id"] for f in session.released] == ["R1"]


# --- moving, skipping, finishing ---------------------------------------------------------


def test_stages_are_completed_in_order_and_the_last_leads_nowhere(session):
    entered = [session.complete_stage()["entered"] for _ in example.SCHEMA.stage_names]
    assert entered == ["parts", "findings", "rating", "plan", "report", None]
    assert session["stage"] == "report" and session.unfinished_stages() == []


def test_going_to_a_stage_neither_completes_nor_skips_the_one_left(session):
    session.go_to_stage("findings")
    assert session["stage"] == "findings" and session["stages"]["scope"] == "in_progress"
    with pytest.raises(Refused, match="must be one of"):
        session.go_to_stage("nowhere")


def test_one_participant_skips_at_once_and_several_must_wait(session):
    assert session.request_change("skip_stage") == "applied"
    assert session["stages"]["scope"] == "skipped" and session["stage"] == "parts"
    session.add_person(BEN)
    assert session.request_change("skip_stage") == "pending"
    assert session["stage"] == "parts"


def test_a_change_is_confirmed_only_on_a_later_message(session):
    assert session.request_change("finish") == "pending"
    with pytest.raises(Refused, match="only just announced"):
        session.resolve_change(True)
    session.next_turn()
    assert session.resolve_change(True) == "finish"
    assert session["status"] == rec.FINISHED and session.notes_posted
    assert session["stages"]["report"] == "complete"


def test_an_objection_drops_the_change(session):
    session.request_change("abandon")
    session.next_turn()
    assert session.resolve_change(False) is None
    assert session.in_progress and session["pending"] is None
    with pytest.raises(Refused, match="Nothing is pending"):
        session.resolve_change(True)


def test_abandoning_ends_the_session_and_nothing_more_can_be_asked_of_it(session):
    session.request_change("abandon")
    session.next_turn()
    assert session.resolve_change(True) == "abandon"
    assert session["status"] == rec.ABANDONED
    with pytest.raises(Refused, match="already ended"):
        session.request_change("finish")


def test_a_confirmed_skip_marks_the_stage_that_was_announced(session):
    session.add_person(BEN)
    session.request_change("skip_stage")
    session.next_turn()
    session.go_to_stage("findings")
    assert session.resolve_change(True) == "skip_stage"
    assert session["stages"]["scope"] == "skipped" and session["stage"] == "findings"


# --- after the notes -----------------------------------------------------------------------


def test_changes_after_the_notes_are_marked(reviewed):
    reviewed.request_change("finish")
    reviewed.next_turn()
    reviewed.resolve_change(True)
    reviewed.update_item("F1", {"level": "high"})
    added = reviewed.add_item("finding", {"part": "P2", "text": "Readable by all"})
    assert reviewed.item("F1")["changedAfterNotes"] and added["changedAfterNotes"]
    reviewed.remove("F2")
    assert reviewed["removedAfterNotes"] == ["F2"]


# --- a message handled twice, or never finished --------------------------------------------------


def test_a_repeated_message_starts_again_from_before_the_first(state, session):
    rec.save(state, session)
    assert rec.begin_message(state, "m1") is False
    session.add_item("scope_item", {"kind": "included", "text": "the API"})
    rec.save(state, session)
    rec.end_message(state)

    assert rec.begin_message(state, "m1") is True
    assert rec.load(state, example.SKILLS)["items"] == []


def test_a_message_that_never_finished_is_undone_by_the_next(state, session):
    rec.save(state, session)
    rec.begin_message(state, "m1")
    session.add_item("scope_item", {"kind": "included", "text": "the API"})
    rec.save(state, session)

    assert rec.begin_message(state, "m2") is False
    assert rec.load(state, example.SKILLS)["items"] == []


def test_messages_without_an_identifier_are_each_new(state, session):
    rec.save(state, session)
    for _ in range(2):
        assert rec.begin_message(state, None) is False
        current = rec.load(state, example.SKILLS)
        current.add_item("scope_item", {"kind": "included", "text": "the API"})
        rec.save(state, current)
        rec.end_message(state)
    assert len(rec.load(state, example.SKILLS)["items"]) == 2
