"""Unit tests for the command that plays a fixed session. Nothing here calls AWS."""

import pytest

import example
import loader
import play_session as play
from session import render
from session.record import Record

SCHEMA = example.SCHEMA


def record():
    s = Record.start(example.SKILL, SCHEMA, "URL shortener", "Ana Souza", "2026-11-21")
    s.add_person("Ben Okafor")
    s.add_item("scope_item", {"kind": "included", "text": "The API"})
    s.complete_stage()
    s.add_item("part", {"name": "API"})
    s.add_item("part", {"name": "Links table"})
    s.give_hint("P2", "who else can write to the giraffe enclosure table")
    s.complete_stage()
    s.add_item("finding", {"part": "P1", "text": "Links created as another customer"})
    s.complete_stage()
    s.update_item("F1", {"level": "high"})
    s.add_note("questioned_kept", "high although the endpoint is private", "F1")
    s.complete_stage()
    s.add_item("fix", {"text": "Move the key to a header", "findings": ["F1"], "owner": "Ben Okafor"})
    s.complete_stage()
    return s


def documents(s, notes):
    out = [{"filename": render.filename(s, render.DOCUMENT),
            "markdown": render.written_document(s, [], "2026-11-22", "Dee")}]
    if notes:
        out.append({"filename": render.filename(s, render.NOTES),
                    "markdown": render.facilitator_notes(s, "Dee")})
    return out


@pytest.fixture
def played():
    """The replies a good agent would give to a short session with every kind of turn."""
    s = record()
    part_way = documents(s, notes=False)
    s.request_change("finish")
    s.next_turn()
    s.resolve_change(True)
    finished = documents(s, notes=True)
    s.add_item("finding", {"part": "P2", "text": "Rows overwritten"})
    changed = documents(s, notes=True)
    spec = {
        "skill": example.SKILL,
        "turns": [
            {"speaker": "Ana Souza", "text": "start", "addressed": True, "expect": "answer", "opening": True},
            {"speaker": "Ben Okafor", "text": "Ana, lunch?", "expect": "no_reply"},
            {"speaker": "Ben Okafor", "text": "the review?", "documents": 1, "part_way_document": True},
            {"speaker": "Ana Souza", "text": "finish", "documents": 0},
            {"speaker": "Ben Okafor", "text": "agreed", "documents": 2, "finishes": True},
            {"speaker": "Ana Souza", "text": "one more", "documents": 2, "changed_after_notes": True},
        ],
        "must_appear_in_notes": ["F1"],
        "must_not_appear_in_document": ["giraffe"],
    }
    replies = [
        {"kind": "answer", "text": "Scope, parts, findings, rating, plan, then the report."},
        {"kind": "no_reply", "text": ""},
        {"kind": "answer", "text": "Attached.", "documents": part_way},
        {"kind": "answer", "text": "About to post."},
        {"kind": "answer", "text": "Posted.", "documents": finished},
        {"kind": "answer", "text": "Posted again.", "documents": changed},
    ]
    return spec, replies


def run(spec, replies):
    queue = list(replies)
    return play.play(spec, lambda payload: queue.pop(0))


def check(spec, results):
    return play.checks(spec, SCHEMA, results)


def failed(found, kind=None):
    return [name for k, name, passed, _ in found if not passed and (kind is None or k == kind)]


# --- the session files --------------------------------------------------------


SESSION_FILES = sorted(play.SESSIONS.glob("*.yaml"))


@pytest.mark.parametrize("path", SESSION_FILES, ids=lambda path: path.name)
def test_a_session_file_plays_a_skill_the_agent_has_with_every_kind_of_turn(path):
    spec, schema = play.load_session(path)
    assert spec["skill"] in loader.SKILLS
    assert schema.stage_names == loader.SKILLS[spec["skill"]].stages
    turns = spec["turns"]
    assert len({turn["speaker"] for turn in turns}) >= 2
    assert any(t.get("expect") == "no_reply" for t in turns)
    assert any("ASKS FOR THE WORK" in str(t.get("note")) for t in turns)
    assert any("OBJECTION" in str(t.get("note")) for t in turns)
    assert any(t.get("part_way_document") for t in turns)
    assert any(t.get("finishes") for t in turns)
    assert any(t.get("changed_after_notes") for t in turns)
    assert turns[0].get("opening") and turns[0].get("addressed")


def test_a_session_file_must_have_turns_and_name_its_skill(tmp_path):
    path = tmp_path / "session.yaml"
    path.write_text("skill: test-review\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no turns"):
        play.load_session(path, example.SKILLS_DIR)
    path.write_text("turns:\n  - {speaker: Ana, text: hi}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not name the skill"):
        play.load_session(path, example.SKILLS_DIR)
    path.write_text("skill: test-review\nturns:\n  - {speaker: Ana, text: hi}\n", encoding="utf-8")
    spec, schema = play.load_session(path, example.SKILLS_DIR)
    assert len(spec["turns"]) == 1 and schema.document_title == "Review"


def test_the_only_session_file_is_played_when_none_is_named(tmp_path):
    with pytest.raises(ValueError, match="holds 0 session files"):
        play.default_session(tmp_path)
    (tmp_path / "one.yaml").write_text("", encoding="utf-8")
    assert play.default_session(tmp_path).name == "one.yaml"
    (tmp_path / "two.yaml").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="holds 2 session files"):
        play.default_session(tmp_path)


def test_a_turn_becomes_a_request_with_its_own_message_id():
    payload = play.payload_for(3, {"speaker": "Ana Souza", "text": "two\n  lines"}, "2026-11-28T10:00:00Z")
    assert payload == {
        "prompt": "two lines", "speakerName": "Ana Souza", "conversationType": "channel_thread",
        "addressed": False, "messageId": "play:3", "threadEndsAt": "2026-11-28T10:00:00Z",
    }
    direct = play.payload_for(1, {"speaker": "Ana", "text": "x", "type": "direct_message"}, "t")
    assert "threadEndsAt" not in direct


# --- the written document's structure -----------------------------------------


def good():
    return render.written_document(record(), [], "2026-11-22", "Dee")


def test_the_player_and_the_agent_agree_on_the_headings():
    assert play.headings(SCHEMA) == render.headings(SCHEMA)


def test_a_document_made_by_the_renderer_has_nothing_wrong():
    assert play.check_document(good(), SCHEMA) == []
    empty = Record.start(example.SKILL, SCHEMA, "Shop", "Ana Souza", "2026-11-21")
    assert play.check_document(render.written_document(empty, [], "2026-11-22", "Dee"), SCHEMA) == []


@pytest.mark.parametrize("heading", play.headings(SCHEMA))
def test_a_missing_section_is_reported_by_name(heading):
    text = good().replace(heading + "\n", "")
    assert f"the section {heading[3:]}" in play.check_document(text, SCHEMA)


def test_other_faults_are_reported():
    def problems(text):
        return play.check_document(text, SCHEMA)
    assert "the title" in problems(good().replace("# Review:", "# Report:"))
    assert "the status line" in problems(good().replace("> Status:", "> State:"))
    assert "Participants in the summary" in problems(good().replace("- **Participants**", "- **People**"))
    assert "System in the summary" in problems(good().replace("- **System**", "- **Thing**"))
    assert "the columns of the table under Findings" in problems(good().replace("| Finding |", "| Problem |"))
    assert "an empty field in the row F1" in problems(good().replace("| High |", "|  |"))
    assert "a field of the row P1" in problems(good().replace("| P1 | API | — |", "| P1 | API |"))
    assert "the method" in problems(good().replace("an AI agent", "a person"))
    swapped = good().replace("## Parts", "## X").replace("## Findings", "## Parts").replace("## X", "## Findings")
    assert "the order of the sections" in problems(swapped)


# --- the checks ---------------------------------------------------------------


def test_a_good_play_passes_every_check(played):
    spec, replies = played
    found = check(spec, run(spec, replies))
    assert failed(found) == []
    names = [name for _, name, _, _ in found]
    assert "a change after the notes is marked †" in names
    assert "nothing from the notes is in the document" in names
    assert "the final written document has every part and field" in names
    assert "turn 1: the opening names the stages" in names


def test_an_opening_that_leaves_out_a_stage_is_a_behavioural_miss(played):
    spec, replies = played
    replies[0]["text"] = "Scope, parts, findings, then the report."
    found = check(spec, run(spec, replies))
    assert failed(found, play.BEHAVIOURAL) == ["turn 1: the opening names the stages"]


def test_notes_with_a_part_way_document_fail(played):
    spec, replies = played
    replies[2]["documents"] = replies[4]["documents"]
    found = check(spec, run(spec, replies))
    assert "turn 3: 1 document(s)" in failed(found, play.STRUCTURAL)
    assert "turn 3: a part-way document comes without the notes" in failed(found, play.STRUCTURAL)


def test_a_finish_without_the_notes_fails(played):
    spec, replies = played
    replies[4]["documents"] = replies[4]["documents"][:1]
    assert "turn 5: the finish carries the document and the notes" in failed(
        check(spec, run(spec, replies)), play.STRUCTURAL)


def test_a_point_from_the_notes_in_the_document_fails(played):
    spec, replies = played
    document = replies[5]["documents"][0]
    document["markdown"] += "\nwho else can write to the giraffe enclosure table\n"
    found = check(spec, run(spec, replies))
    assert "nothing from the notes is in the document" in failed(found, play.STRUCTURAL)
    assert "the document does not contain 'giraffe'" in failed(found, play.BEHAVIOURAL)


def test_a_change_after_the_notes_without_its_mark_fails(played):
    spec, replies = played
    replies[5]["documents"] = replies[4]["documents"]
    assert "a change after the notes is marked †" in failed(
        check(spec, run(spec, replies)), play.STRUCTURAL)


def test_a_wrong_kind_of_reply_is_a_behavioural_miss(played):
    spec, replies = played
    replies[1] = {"kind": "answer", "text": "Enjoy lunch."}
    found = check(spec, run(spec, replies))
    assert failed(found, play.STRUCTURAL) == []
    assert failed(found, play.BEHAVIOURAL) == ["turn 2: expected no_reply"]


def test_a_turn_that_fails_or_is_slow_is_structural(played):
    spec, replies = played
    queue = list(replies)

    def send(payload):
        reply = queue.pop(0)
        if payload["messageId"] == "play:4":
            raise RuntimeError("the agent fell over")
        return reply

    results = play.play(spec, send)
    results[0]["seconds"] = 140
    found = failed(check(spec, results), play.STRUCTURAL)
    assert "turn 4: a reply came back" in found
    assert "turn 1: answered within 100 seconds" in found


def test_no_written_document_at_all_fails():
    spec = {"turns": [{"speaker": "Ana", "text": "hi"}]}
    found = check(spec, run(spec, [{"kind": "answer", "text": "Hello."}]))
    assert failed(found, play.STRUCTURAL) == ["a written document was produced"]


# --- the transcript and the report --------------------------------------------


def test_the_transcript_and_the_documents_are_written_to_the_folder(played, tmp_path):
    spec, replies = played
    results = run(spec, replies)
    report = play.report_of(check(spec, results))
    play.write_transcript(tmp_path / "run", results, report)
    names = sorted(p.name for p in (tmp_path / "run").iterdir())
    assert "transcript.md" in names and "checks.txt" in names
    assert "turn-03-review-url-shortener.md" in names
    assert "turn-05-facilitator-notes-url-shortener.md" in names
    transcript = (tmp_path / "run" / "transcript.md").read_text()
    assert "**Ben Okafor**:" in transcript and "_(no reply)_" in transcript
    assert "**Ana Souza** (to the agent):" in transcript
    assert "Structural: all pass." in report


def test_the_report_says_how_many_failed(played):
    spec, replies = played
    replies[4]["documents"] = []
    report = play.report_of(check(spec, run(spec, replies)))
    assert "FAIL  turn 5: 2 document(s) (got 0)" in report
    assert "FAILED" in report.splitlines()[-1]


def test_the_command_needs_a_runtime(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME_ARN", raising=False)
    with pytest.raises(SystemExit):
        play.main([])
