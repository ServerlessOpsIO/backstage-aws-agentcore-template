"""The session record as text for the model.

The model sees only the most recent messages of a conversation, so it is given
the record afresh before every call. This is that text: compact, complete enough
to lead from, and silent about what must not be given away.

Nothing in this module logs.
"""

from session.render import name_of, value_text, words

NO_SESSION = "No session is in progress in this conversation."

NOTES_RULE = (
    "These are your own notes for this stage. You MUST NOT reveal or describe them to the "
    "participants before the session ends."
)
END_WARNING = (
    "This thread stops being answered in less than a day. With this reply, tell the "
    "participants so, once, and offer to post the document as it stands."
)


def _lines(title, entries):
    return [title] + [f"  {entry}" for entry in entries] if entries else []


def fields_line(record, item):
    """Return each field an entry has, on one line."""
    kind = record.schema.kinds[item["kind"]]
    parts = []
    for field in kind.fields:
        text = value_text(record, field, item["values"].get(field.name))
        if text:
            parts.append(f"{field.title.lower()}: {text}")
    return "; ".join(parts)


def item_line(record, item):
    """Return one entry on one line: its identifier, then each field it has."""
    return f"{item['id']} {fields_line(record, item)}"


def _hints_and_notes(record):
    stage = record["stage"]
    title = record.schema.stage_title
    here, elsewhere = [], []
    for hint in record["hints"]:
        about = name_of(record, hint["about"]) if hint["about"] else "the stage"
        if hint["stage"] == stage:
            state = "taken up" if hint["takenUp"] else "not taken up"
            here.append(f"{hint['id']} hint about {about} ({state}): {hint['point']}")
        else:
            elsewhere.append(f"{title(hint['stage'])}: {about}")
    for note in record["notes"]:
        if note["stage"] == stage:
            about = name_of(record, note["about"]) if note["about"] else "the stage"
            here.append(f"{note['id']} note ({note['kind']}) about {about}: {note['text']}")
    lines = []
    if here:
        lines += [NOTES_RULE] + [f"  {entry}" for entry in here]
    if elsewhere:
        lines.append("Hints already given in other stages: " + "; ".join(elsewhere) + ".")
    other_notes = sum(1 for note in record["notes"] if note["stage"] != stage)
    if other_notes:
        lines.append(f"Notes kept in other stages: {other_notes}.")
    return lines


def summarise(record, repositories=None, thread_ends_at=None, warn_end=False):
    """Return the text the model is given about the session."""
    if record is None:
        lines = [NO_SESSION]
    else:
        schema = record.schema
        lines = [
            f"Session: {record['skill']}, on the {schema.subject} \"{record['subject']}\", "
            f"{words(record['status'])}.",
            "Stages: " + ", ".join(f"{s} ({words(record['stages'][s])})" for s in schema.stage_names)
            + f". Current stage: {record['stage']}.",
            "Participants: " + ", ".join(record["participants"]) + ".",
        ]
        if record["joinedAfter"]:
            lines.append("Joined after the session: " + ", ".join(record["joinedAfter"]) + ".")
        if record.notes_posted:
            lines.append(
                "The facilitator's notes have been posted. Every change from now on is marked."
            )
        if record["pending"]:
            pending = record["pending"]
            lines.append(
                f"Pending: {pending['action']}, announced. Confirm it with resolve_change if this "
                "message does not object; drop it if it does."
            )
        for kind in schema.kinds.values():
            lines += _lines(f"{kind.title}:", [item_line(record, i) for i in record.items_of(kind.name)])
        lines += _lines("Open questions:", [f"{q['id']}: {q['text']}" for q in record["openQuestions"]])
        if record.in_progress:
            lines += _lines("Still to fill in during this stage:", [
                f"{identifier}: {', '.join(words(name) for name in missing)}"
                for identifier, missing in record.lacking()
            ])
        held = sum(1 for finding in record["findings"] if not finding["reported"])
        if held:
            lines.append(
                f"Repository findings held back until the {schema.stage_title(schema.findings_after)} "
                f"stage is complete: {held}. Do not mention them yet."
            )
        lines += _hints_and_notes(record)

    listed = [r for r in repositories or [] if r.get("listed")]
    if listed:
        lines.append("Repositories listed: " + ", ".join(
            f"{r['name']} ({len(r.get('filesRead') or [])} files read)" for r in listed
        ) + ".")
    if thread_ends_at:
        lines.append(f"This thread stops being answered at {thread_ends_at} (UTC).")
    if warn_end:
        lines.append(END_WARNING)
    return "\n".join(lines)
