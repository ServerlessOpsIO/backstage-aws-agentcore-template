#!/usr/bin/env python3
"""Play a fixed session against a deployed agent and check the result.

    pipenv run play-session

The turns are in a file under data/sessions/. Each is sent to the agent in one
new conversation, without Slack. The transcript and the documents are written to
transcripts/, which git ignores: they hold a whole conversation and stay on this
computer. Nothing but the checks is printed.

Two kinds of check are reported:

- structural: the written document's parts and fields, which documents come with
  which reply, and how long each reply took. The command exits 0 only when all pass.
- behavioural: what depends on the model's judgement and can still be checked by a
  program. These are reported and do not change the exit code.

What no program can judge is in the checklist in
docs/handbook/10-guided-sessions.md, which a person reads the transcript against.

The runtime ARN comes from --arn or AGENT_RUNTIME_ARN. The caller's AWS credentials
need bedrock-agentcore:InvokeAgentRuntime on it.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# The skills' session.yaml files say what a written document must contain.
sys.path.insert(0, str(ROOT / "src" / "agent"))
from session import schema as sch  # noqa: E402

SESSIONS = ROOT / "data" / "sessions"
SKILLS = ROOT / "src" / "agent" / "skills"
DEFAULT_OUT = ROOT / "transcripts"

MAX_SECONDS = 100
THREAD_DAYS = 7

NOTES_FILE = "facilitator-notes"
SUMMARY_FIELDS = ["**Date**", "**Session started**", "**Participants**", "**Recorded**"]
STRUCTURAL, BEHAVIOURAL = "structural", "behavioural"


# --- the session file ---------------------------------------------------------


def default_session(folder=SESSIONS):
    """Return the session file to play when none is named: the only one there is."""
    found = sorted(Path(folder).glob("*.yaml"))
    if len(found) != 1:
        raise ValueError(f"{folder} holds {len(found)} session files: name one with --session")
    return found[0]


def load_session(path, skills=SKILLS):
    """Return (the session's turns and settings, the schema of the skill it plays)."""
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or not spec.get("turns"):
        raise ValueError(f"{path} has no turns")
    if not isinstance(spec.get("skill"), str):
        raise ValueError(f"{path} does not name the skill it plays")
    return spec, sch.load(Path(skills) / spec["skill"])


def payload_for(number, turn, thread_ends_at):
    kind = turn.get("type", "channel_thread")
    payload = {
        "prompt": " ".join(str(turn["text"]).split()),
        "speakerName": turn["speaker"],
        "conversationType": kind,
        "addressed": bool(turn.get("addressed", False)),
        "messageId": f"play:{number}",
    }
    if kind == "channel_thread":
        payload["threadEndsAt"] = thread_ends_at
    return payload


# --- playing ------------------------------------------------------------------


def play(spec, send, now=None):
    """Send every turn in order. Return one result per turn."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    ends = (now + datetime.timedelta(days=THREAD_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    for number, turn in enumerate(spec["turns"], 1):
        started = time.monotonic()
        try:
            reply = send(payload_for(number, turn, ends))
        except Exception as error:  # A failed turn is a result, not the end of the play.
            reply = {"kind": "error", "text": type(error).__name__}
        results.append({
            "number": number, "turn": turn, "reply": reply if isinstance(reply, dict) else {},
            "seconds": time.monotonic() - started,
        })
    return results


def aws_sender(arn, session_id):
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-agentcore", region_name=arn.split(":")[3],
        config=Config(read_timeout=MAX_SECONDS + 20, retries={"total_max_attempts": 1}),
    )

    def send(payload):
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn, runtimeSessionId=session_id,
            contentType="application/json", accept="application/json",
            payload=json.dumps(payload).encode(),
        )
        return json.loads(response["response"].read())

    return send


# --- checking a written document ----------------------------------------------


def headings(schema):
    """Return the headings every written document of a skill has, in order."""
    return (["## Summary"] + [f"## {kind.title}" for kind in schema.kinds.values()]
            + ["## Open questions", "## Method"])


def _section(text, heading):
    after = text.split(heading + "\n", 1)
    return re.split(r"\n## ", after[1], maxsplit=1)[0] if len(after) == 2 else ""


def _rows(section):
    """Return a table's header and its rows as lists of cells, without the rule."""
    lines = [line for line in section.splitlines() if line.startswith("|")]
    rows = [[c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))] for line in lines]
    return (rows[0] if rows else []), rows[2:]


def check_document(text, schema):
    """Return what is wrong with a written document's structure: [] when nothing is."""
    problems = []
    if not text.startswith(f"# {schema.document_title}: "):
        problems.append("the title")
    if not re.search(r"^> Status: \*\*(Complete|Finished|In progress|Abandoned)\*\*\.", text, re.M):
        problems.append("the status line")
    expected = headings(schema)
    found = re.findall(r"^## .*$", text, re.M)
    for heading in expected:
        if heading not in found:
            problems.append(f"the section {heading[3:]}")
    if [h for h in found if h in expected] != [h for h in expected if h in found]:
        problems.append("the order of the sections")
    summary = _section(text, "## Summary")
    for field in [f"**{schema.subject.capitalize()}**"] + SUMMARY_FIELDS:
        if field not in summary:
            problems.append(f"{field.strip('*')} in the summary")

    for kind in schema.kinds.values():
        if kind.layout != sch.TABLE:
            continue
        header, rows = _rows(_section(text, f"## {kind.title}"))
        if not rows:
            continue
        columns = ["ID"] + [field.title for field in kind.fields]
        if header != columns:
            problems.append(f"the columns of the table under {kind.title}")
        for row in rows:
            if len(row) != len(columns):
                problems.append(f"a field of the row {row[0]}")
            elif any(not cell for cell in row):
                problems.append(f"an empty field in the row {row[0]}")

    if "AI agent" not in _section(text, "## Method"):
        problems.append("the method")
    return problems


def _notes_points(notes):
    """Return the points made in the notes: the text after each item's label."""
    points = []
    for line in notes.splitlines():
        if line.startswith("- "):
            point = line.split(": ", 1)[-1].replace(" (not raised in the session)", "").strip()
            if len(point) > 15:
                points.append(point)
    return points


# --- the checks ---------------------------------------------------------------


def _documents(result):
    return result["reply"].get("documents") or []


def _find(documents, prefix):
    for document in documents:
        if str(document.get("filename", "")).startswith(prefix):
            return document.get("markdown", "")
    return None


def checks(spec, schema, results):
    """Return every check as (kind, name, passed, detail)."""
    stem = schema.document_filename
    out = []

    def add(kind, name, passed, detail=""):
        out.append((kind, name, bool(passed), detail))

    for result in results:
        turn, reply, number = result["turn"], result["reply"], result["number"]
        kind = reply.get("kind")
        add(STRUCTURAL, f"turn {number}: a reply came back", kind in ("answer", "no_reply"), str(kind))
        expected = turn.get("expect", "any")
        if expected != "any":
            add(BEHAVIOURAL, f"turn {number}: expected {expected}", kind == expected, f"got {kind}")
        if "documents" in turn:
            add(STRUCTURAL, f"turn {number}: {turn['documents']} document(s)",
                len(_documents(result)) == turn["documents"], f"got {len(_documents(result))}")
        add(STRUCTURAL, f"turn {number}: answered within {MAX_SECONDS} seconds",
            result["seconds"] <= MAX_SECONDS, f"{result['seconds']:.0f} s")
        if turn.get("opening"):
            text = str(reply.get("text", "")).lower()
            missing = [stage.title.lower() for stage in schema.stages[:-1]
                       if stage.title.lower() not in text]
            add(BEHAVIOURAL, f"turn {number}: the opening names the stages", not missing,
                "missing " + ", ".join(missing) if missing else "")

    part_way = [r for r in results if r["turn"].get("part_way_document")]
    for result in part_way:
        documents = _documents(result)
        document = _find(documents, stem)
        add(STRUCTURAL, f"turn {result['number']}: a part-way document comes without the notes",
            document is not None and _find(documents, NOTES_FILE) is None)
        if document:
            add(STRUCTURAL, f"turn {result['number']}: the part-way document is marked in progress",
                "> Status: **In progress**." in document)

    finishing = [r for r in results if r["turn"].get("finishes")]
    notes = None
    for result in finishing:
        documents = _documents(result)
        document, notes = _find(documents, stem), _find(documents, NOTES_FILE)
        add(STRUCTURAL, f"turn {result['number']}: the finish carries the document and the notes",
            document is not None and notes is not None)

    with_documents = [r for r in results if _find(_documents(r), stem)]
    final = _find(_documents(with_documents[-1]), stem) if with_documents else None
    add(STRUCTURAL, "a written document was produced", final is not None)
    if final:
        problems = check_document(final, schema)
        add(STRUCTURAL, "the final written document has every part and field", not problems,
            "missing or wrong: " + "; ".join(problems) if problems else "")
        if any(r["turn"].get("changed_after_notes") for r in results):
            add(STRUCTURAL, "a change after the notes is marked †",
                "†" in final and "after the facilitator's notes were posted" in final)
        for word in spec.get("must_not_appear_in_document") or []:
            add(BEHAVIOURAL, f"the document does not contain '{word}'", word.lower() not in final.lower())

    if notes is not None:
        add(STRUCTURAL, "the notes say whose they are",
            notes.startswith("# Facilitator's notes: ") and "own observations" in notes)
        if final:
            leaked = [point for point in _notes_points(notes) if point.lower() in final.lower()]
            add(STRUCTURAL, "nothing from the notes is in the document", not leaked,
                f"{len(leaked)} point(s) of the notes appear in the document" if leaked else "")
        for word in spec.get("must_appear_in_notes") or []:
            add(BEHAVIOURAL, f"the notes contain '{word}'", word.lower() in notes.lower())
    return out


# --- the transcript -----------------------------------------------------------


def write_transcript(folder, results, report):
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["# Transcript of the played session", ""]
    for result in results:
        turn, reply = result["turn"], result["reply"]
        lines += [f"## Turn {result['number']}", "",
                  f"**{turn['speaker']}**" + (" (to the agent)" if turn.get("addressed") else "") + ":",
                  "", " ".join(str(turn["text"]).split()), ""]
        if turn.get("note"):
            lines += [f"> Look for: {' '.join(str(turn['note']).split())}", ""]
        said = reply.get("text") or ""
        lines += [f"**The agent** ({reply.get('kind')}, {result['seconds']:.0f} s):", "",
                  said if said else "_(no reply)_", ""]
        for document in reply.get("documents") or []:
            name = f"turn-{result['number']:02d}-{document.get('filename', 'document.md')}"
            (folder / name).write_text(document.get("markdown", ""), encoding="utf-8")
            lines += [f"_Attached: {name}_", ""]
    (folder / "transcript.md").write_text("\n".join(lines), encoding="utf-8")
    (folder / "checks.txt").write_text(report, encoding="utf-8")


def report_of(found):
    lines = []
    for kind in (STRUCTURAL, BEHAVIOURAL):
        lines.append(f"{kind.capitalize()} checks")
        for _, name, passed, detail in [c for c in found if c[0] == kind]:
            lines.append(f"  {'pass' if passed else 'FAIL'}  {name}" + (f" ({detail})" if detail and not passed else ""))
    failed = [c for c in found if c[0] == STRUCTURAL and not c[2]]
    missed = [c for c in found if c[0] == BEHAVIOURAL and not c[2]]
    lines.append("")
    lines.append(f"Structural: {'all pass' if not failed else str(len(failed)) + ' FAILED'}. "
                 f"Behavioural: {len(missed)} missed.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arn", default=os.environ.get("AGENT_RUNTIME_ARN"))
    parser.add_argument("--session", help="The session file to play. Default: the only one in data/sessions.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Where transcripts are written.")
    args = parser.parse_args(argv)
    if not args.arn:
        parser.error("set AGENT_RUNTIME_ARN or pass --arn")

    spec, schema = load_session(args.session or default_session())
    results = play(spec, aws_sender(args.arn, f"play-{uuid.uuid4()}"))
    found = checks(spec, schema, results)
    report = report_of(found)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(args.out) / stamp
    write_transcript(folder, results, report)
    print(report, end="")
    print(f"Transcript: {folder}")
    return 1 if any(c[0] == STRUCTURAL and not c[2] for c in found) else 0


if __name__ == "__main__":
    sys.exit(main())
