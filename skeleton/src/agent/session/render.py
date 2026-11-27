"""The written document and the facilitator's notes, made from the session record.

Both are GitHub-flavoured Markdown. The same record always gives the same
document: nothing here asks a model for words. What the document contains
comes from the skill's session.yaml: a section for each kind of entry, in the
order the kinds are given, laid out as a table or a list.

Nothing in this module logs. The documents hold what people said and their names.
"""

import re

from session import schema as sch
from session.record import ABANDONED, FINISHED

EMPTY = "—"
CHANGED = "†"

DOCUMENT = "document"
NOTES = "notes"
NOTES_FILE_STEM = "facilitator-notes"
NOTES_TITLE = "Facilitator's notes"
_FILENAME_CHARS = 60
_LABEL_CHARS = 60


def _text(value):
    """Return what a person gave, made safe for a table cell or a list item."""
    value = re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "\\|")
    if value[:1] in ("#", ">"):
        value = "\\" + value
    return value


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def a(noun):
    """Return a noun with its article: "an option", "a decision"."""
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


def words(name):
    """Return a name from session.yaml as words: "not_started" gives "not started"."""
    return str(name).replace("_", " ")


def filename(record, kind):
    """Return the file name for a document about the session's subject."""
    stem = NOTES_FILE_STEM if kind == NOTES else record.schema.document_filename
    slug = re.sub(r"[^a-z0-9]+", "-", str(record["subject"] or "").lower()).strip("-")
    name = f"{stem}-{slug}" if slug else stem
    return name[:_FILENAME_CHARS].rstrip("-") + ".md"


def title(record, kind):
    heading = NOTES_TITLE if kind == NOTES else record.schema.document_title
    return f"{heading}: {_text(record['subject'])}"


def name_of(record, identifier):
    """Return an entry's identifier, with its label when its kind has one: "O2 (Queue)"."""
    for item in record["items"]:
        if item["id"] == identifier:
            label = record.schema.kinds[item["kind"]].label
            text = _text(item["values"].get(label)) if label else ""
            if len(text) > _LABEL_CHARS:
                text = text[:_LABEL_CHARS].rstrip() + "…"
            return f"{identifier} ({text})" if text else identifier
    return str(identifier)


def value_text(record, field, value):
    """Return one field's value as words, or '' when it has none."""
    if value is None or value == "" or value == []:
        return ""
    if field.type == sch.CHOICE:
        return words(value).capitalize()
    if field.type == sch.REF:
        return name_of(record, value)
    if field.type == sch.REFS:
        return ", ".join(name_of(record, identifier) for identifier in value)
    if field.type == sch.PEOPLE:
        return ", ".join(_text(name) for name in value)
    return _text(value)


def _marked(item):
    return item["id"] + (CHANGED if item.get("changedAfterNotes") else "")


# --- the written document -----------------------------------------------------


def _unfinished(record):
    """Stages that are not complete, leaving out the last, in which this document is given."""
    last = record.schema.last_stage
    return [(stage, status) for stage, status in record.unfinished_stages() if stage != last]


def _status(record):
    unfinished = _unfinished(record)
    if record["status"] == FINISHED:
        word = "Finished" if unfinished else "Complete"
    elif record["status"] == ABANDONED:
        word = "Abandoned"
    else:
        word = "In progress"
    lines = [f"> Status: **{word}**."]
    for stage, status in unfinished:
        label = "Skipped" if status == "skipped" else "Not finished"
        lines.append(f"> {label}: {record.schema.stage_title(stage)}.")
    if any(item.get("changedAfterNotes") for item in record["items"]):
        lines.append(
            f"> Entries marked {CHANGED} were added or changed after the facilitator's notes were posted."
        )
    if record["removedAfterNotes"]:
        lines.append(
            "> Removed after the facilitator's notes were posted: "
            + ", ".join(record["removedAfterNotes"]) + "."
        )
    return "\n".join(lines)


def _stage_note(record, kind):
    """The words a section begins with when its stage was skipped or never started."""
    stage = record.schema.stage_of(kind.name)
    status = record["stages"][stage.name]
    if status == "skipped":
        return f"Skipped: {stage.title}.\n\n"
    if status == "not_started":
        return f"Not finished: {stage.title}.\n\n"
    return ""


def _summary(record, today):
    lines = [
        f"- **{record.schema.subject.capitalize()}**: {_text(record['subject'])}",
        f"- **Date**: {today}",
        f"- **Session started**: {record['startedOn']}",
        "- **Participants**: " + (", ".join(_text(n) for n in record["participants"]) or EMPTY),
    ]
    if record["joinedAfter"]:
        lines.append(
            "- **Joined after the session**: " + ", ".join(_text(n) for n in record["joinedAfter"])
        )
    counts = ", ".join(
        f"{kind.title} {len(record.items_of(kind.name))}" for kind in record.schema.kinds.values()
    )
    lines.append(f"- **Recorded**: {counts}")
    return "\n".join(lines)


def _as_table(record, kind, items):
    rows = [
        [_marked(item)] + [
            value_text(record, field, item["values"].get(field.name)) or EMPTY for field in kind.fields
        ]
        for item in items
    ]
    return _table(["ID"] + [field.title for field in kind.fields], rows)


def _list_item(record, kind, item, leave_out):
    """One entry as a list item: its first text, then its other fields in brackets."""
    fields = [field for field in kind.fields if field.name != leave_out]
    first = next((field for field in fields if field.type == sch.TEXT), fields[0] if fields else None)
    main = value_text(record, first, item["values"].get(first.name)) if first else ""
    rest = []
    for field in fields:
        text = "" if field is first else value_text(record, field, item["values"].get(field.name))
        if text:
            rest.append(f"{field.title}: {text}")
    line = f"- {_marked(item)}: {main or EMPTY}"
    return line + (f" ({'; '.join(rest)})" if rest else "")


def _as_list(record, kind, items):
    if not kind.group_by:
        return "\n".join(_list_item(record, kind, item, "") for item in items)
    parts = []
    for choice in kind.field(kind.group_by).choices:
        chosen = [item for item in items if item["values"].get(kind.group_by) == choice]
        body = "\n".join(_list_item(record, kind, item, kind.group_by) for item in chosen)
        parts.append(f"**{words(choice).capitalize()}**\n\n{body or 'None recorded.'}")
    return "\n\n".join(parts)


def _section(record, kind):
    items = record.items_of(kind.name)
    if not items:
        body = "None recorded."
    elif kind.layout == sch.LIST:
        body = _as_list(record, kind, items)
    else:
        body = _as_table(record, kind, items)
    return _stage_note(record, kind) + body


def _open_questions(record):
    if not record["openQuestions"]:
        return "None."
    return "\n".join(f"{n}. {_text(q['text'])}" for n, q in enumerate(record["openQuestions"], 1))


def _repository_files(repositories):
    files, unread = [], []
    for repository in repositories or []:
        commit = (repository.get("commit") or "")[:7]
        for path in repository.get("filesRead") or []:
            files.append(f"- `{repository['name']}@{commit}`: `{path}`")
        if repository.get("unread"):
            unread.append(f"`{repository['name']}` could not be read in full.")
    if not files and not unread:
        return ""
    return "\n\n".join(part for part in ("\n".join(files), " ".join(unread)) if part)


def _method(record, agent_name):
    text = (
        f"This document was made in a session led by {agent_name}, an AI agent. What it "
        f"records was said or decided by the participants. {agent_name} asked the questions "
        "and recorded the answers."
    )
    if record.schema.method:
        text += " " + record.schema.method
    return "> " + text


def written_document(record, repositories, today, agent_name):
    """Return the written document for the record as it stands."""
    sections = [
        (f"# {title(record, DOCUMENT)}", _status(record)),
        ("## Summary", _summary(record, today)),
    ]
    sections += [(f"## {kind.title}", _section(record, kind)) for kind in record.schema.kinds.values()]
    sections.append(("## Open questions", _open_questions(record)))
    files = _repository_files(repositories)
    if files:
        sections.append(("## Repository files read", files))
    sections.append(("## Method", _method(record, agent_name)))
    return "\n\n".join(f"{heading}\n\n{body}" for heading, body in sections) + "\n"


def headings(schema):
    """Return the headings every written document of a skill has, in order."""
    return (["## Summary"] + [f"## {kind.title}" for kind in schema.kinds.values()]
            + ["## Open questions", "## Method"])


# --- the facilitator's notes --------------------------------------------------


def _about(record, entry):
    if entry.get("about"):
        return name_of(record, entry["about"])
    return record.schema.stage_title(entry["stage"])


def facilitator_notes(record, agent_name):
    """Return the facilitator's notes: hints not taken up, then every note."""
    schema = record.schema
    hinted = [
        f"- {schema.stage_title(h['stage'])}, {_about(record, h)}: {_text(h['point'])}"
        for h in record["hints"] if not h["takenUp"]
    ]
    not_raised = [
        f"- {schema.stage_title(n['stage'])}, {_about(record, n)}: {_text(n['text'])} (not raised in the session)"
        for n in record["notes"] if n["kind"] == "not_raised"
    ]
    questioned = [
        f"- {_about(record, n)}: {_text(n['text'])}"
        for n in record["notes"] if n["kind"] == "questioned_kept"
    ]
    sections = [
        ("## Hinted at, and not taken up", hinted),
        ("## Not raised in the session", not_raised),
        ("## Questioned, and kept", questioned),
    ]
    opening = (
        f"> These are {agent_name}'s own observations from the session. The participants have not\n"
        "> checked them, and they are not part of what the participants recorded."
    )
    parts = [f"# {title(record, NOTES)}", opening]
    for heading, entries in sections:
        parts.append(heading)
        parts.append("\n".join(entries) if entries else "Nothing.")
    return "\n\n".join(parts) + "\n"
