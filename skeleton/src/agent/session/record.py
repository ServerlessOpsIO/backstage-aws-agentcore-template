"""The session record: what a session has established so far.

Everything the written document is made from is here, as plain JSON types,
because it is kept in the agent's state and restored with the conversation.
The model changes it only through the tools in tools.py. What may be recorded
comes from the skill's session.yaml (schema.py); the rules that can be counted
are kept here, in code, whatever the model was told.

Nothing in this module logs. The record holds what people said and their names.
"""

import copy

from session import schema as sch

STAGE_STATUSES = ("not_started", "in_progress", "complete", "skipped")

IN_PROGRESS = "in_progress"
FINISHED = "finished"
ABANDONED = "abandoned"

NOTE_KINDS = ("not_raised", "questioned_kept")
FINDING_KINDS = ("differs", "not_mentioned")
CHANGES = ("skip_stage", "finish", "abandon")

# The keys of the agent's state.
KEY_SESSION = "session"
KEY_REPOSITORIES = "repositories"
KEY_LAST_MESSAGE_ID = "lastMessageId"
KEY_LAST_MESSAGE_DONE = "lastMessageDone"
KEY_SESSION_BEFORE = "sessionBefore"

_LISTS = (
    "participants", "joinedAfter", "items", "openQuestions", "hints", "notes", "findings",
    "removedAfterNotes",
)


class Refused(Exception):
    """A change the rules do not allow. The message is fit to show the model."""


def _text(value, what, required=True):
    value = value.strip() if isinstance(value, str) else ""
    if required and not value:
        raise Refused(f"{what} is missing.")
    return value


def _one_of(value, allowed, what):
    if value not in allowed:
        raise Refused(f"{what} must be one of: {', '.join(allowed)}.")
    return value


def _empty(value):
    return value is None or value == "" or value == []


class Record:
    """One session's record. A thin layer of rules over a JSON-safe dict."""

    def __init__(self, data, schema):
        self.data = data
        self.schema = schema
        # Repository findings let go by the last change of stage, for the tool
        # that made the change to hand to the model. Not part of the record.
        self.released = []

    # --- making and reading ---------------------------------------------------

    @classmethod
    def start(cls, skill, schema, subject, speaker, today):
        """Return the record of a session that has just started, in its first stage."""
        stages = schema.stage_names
        data = {
            "skill": skill,
            "status": IN_PROGRESS,
            "subject": _text(subject, f"The {schema.subject}'s name"),
            "startedOn": today,
            "turn": 1,
            "stage": stages[0],
            "stages": {stage: "not_started" for stage in stages},
            "findingsReleased": not schema.findings_after,
            "pending": None,
            "notesPostedOnTurn": None,
            "endWarned": False,
            "replaceWarnedOnTurn": None,
            "counters": {},
        }
        for name in _LISTS:
            data[name] = []
        data["stages"][stages[0]] = "in_progress"
        record = cls(data, schema)
        record.add_person(speaker)
        return record

    @classmethod
    def from_dict(cls, data, schema):
        """Return the record held in data. Raises ValueError when it does not fit the schema.

        A stage the skill has gained since the record was made is added as not
        started. A stage or a kind the skill has lost makes the record unfit.
        """
        if not isinstance(data, dict):
            raise ValueError("not a record")
        for name in _LISTS:
            if not isinstance(data.get(name), list):
                raise ValueError(f"{name} is not a list")
        if data.get("status") not in (IN_PROGRESS, FINISHED, ABANDONED):
            raise ValueError("status")
        if data.get("stage") not in schema.stage_names:
            raise ValueError("stage")
        stages = data.get("stages")
        if not isinstance(stages, dict) or not set(stages) <= set(schema.stage_names):
            raise ValueError("stages")
        if any(status not in STAGE_STATUSES for status in stages.values()):
            raise ValueError("stage status")
        if not isinstance(data.get("turn"), int) or not isinstance(data.get("counters"), dict):
            raise ValueError("turn or counters")
        if not isinstance(data.get("subject"), str) or not isinstance(data.get("skill"), str):
            raise ValueError("subject or skill")
        for item in data["items"]:
            if not isinstance(item, dict) or item.get("kind") not in schema.kinds:
                raise ValueError("an item of a kind the skill no longer has")
            if not isinstance(item.get("values"), dict) or not isinstance(item.get("id"), str):
                raise ValueError("item")
        data = copy.deepcopy(data)
        for stage in schema.stage_names:
            data["stages"].setdefault(stage, "not_started")
        return cls(data, schema)

    def to_dict(self):
        return copy.deepcopy(self.data)

    def __getitem__(self, key):
        return self.data[key]

    @property
    def in_progress(self):
        return self.data["status"] == IN_PROGRESS

    @property
    def ended(self):
        return not self.in_progress

    @property
    def notes_posted(self):
        return self.data["notesPostedOnTurn"] is not None

    def _next_id(self, prefix):
        counters = self.data["counters"]
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}{counters[prefix]}"

    def _find(self, collection, identifier, what):
        for entry in self.data[collection]:
            if entry["id"] == identifier:
                return entry
        raise Refused(f"There is no {what} {identifier}.")

    def item(self, identifier):
        return self._find("items", identifier, "entry")

    def items_of(self, kind_name):
        return [item for item in self.data["items"] if item["kind"] == kind_name]

    # --- people and turns -----------------------------------------------------

    def people(self):
        """Everyone who may be named as having said or decided something."""
        return self.data["participants"] + self.data["joinedAfter"]

    def add_person(self, name):
        """Add a speaker once: a participant while in progress, joined after once ended."""
        if not name or name in self.people():
            return
        self.data["participants" if self.in_progress else "joinedAfter"].append(name)

    def next_turn(self):
        self.data["turn"] += 1

    # --- what the participants give -------------------------------------------

    def _identifiers(self, value, field, what):
        identifiers = list(value) if isinstance(value, (list, tuple)) else [value]
        for identifier in identifiers:
            target = self.item(identifier) if isinstance(identifier, str) else None
            if target is None or target["kind"] != field.to:
                singular = self.schema.kinds[field.to].singular
                raise Refused(f"{what} must be the identifier of one {singular}.")
        return identifiers

    def _value(self, field, value):
        """Return one field's value as it is kept, or raise Refused."""
        what = f"The {field.title.lower()}"
        if field.type == sch.TEXT:
            return _text(value, what)
        if field.type == sch.CHOICE:
            return _one_of(value, field.choices, what)
        if field.type == sch.REF:
            return self._identifiers(_text(value, what), field, what)[0]
        if field.type == sch.REFS:
            return self._identifiers(value, field, what)
        names = [name for name in (value if isinstance(value, (list, tuple)) else [value])
                 if isinstance(name, str)]
        unknown = [name for name in names if name not in self.people()]
        if unknown:
            raise Refused(
                "Not in this session: " + ", ".join(unknown)
                + ". Those who can be named: " + ", ".join(self.people()) + "."
            )
        return names

    def _values(self, kind, given, complete):
        """Check what a tool was given for one entry. Empty values are treated as not given."""
        given = given if isinstance(given, dict) else {}
        unknown = [name for name in given if kind.field(name) is None]
        if unknown:
            raise Refused(f"There is no {unknown[0]} to give for this kind of entry.")
        values = {}
        for field in kind.fields:
            value = given.get(field.name)
            if isinstance(value, str):
                value = value.strip()
            if _empty(value):
                if complete and field.required:
                    raise Refused(f"The {field.title.lower()} is missing.")
                continue
            values[field.name] = self._value(field, value)
        return values

    def _touch(self, item):
        if self.notes_posted:
            item["changedAfterNotes"] = True

    def add_item(self, kind_name, given):
        """Record one entry of a kind the skill names, and return it."""
        kind = self.schema.kinds.get(kind_name)
        if kind is None:
            raise Refused(f"There is no kind of entry called {kind_name}.")
        values = self._values(kind, given, complete=True)
        item = {
            "id": self._next_id(kind.prefix),
            "kind": kind.name,
            "stage": self.data["stage"],
            "values": values,
            "changedAfterNotes": False,
        }
        self._touch(item)
        self.data["items"].append(item)
        return item

    def update_item(self, identifier, given):
        """Change or fill in fields of an entry, and return it."""
        item = self.item(_text(identifier, "The identifier"))
        kind = self.schema.kinds[item["kind"]]
        values = self._values(kind, given, complete=False)
        if not values:
            raise Refused("Nothing to change was given.")
        item["values"].update(values)
        self._touch(item)
        return item

    def referring_to(self, identifier):
        """Return the identifiers of the entries that name this one."""
        found = []
        for item in self.data["items"]:
            kind = self.schema.kinds[item["kind"]]
            for field in kind.fields:
                value = item["values"].get(field.name)
                if (field.type == sch.REF and value == identifier) or (
                        field.type == sch.REFS and identifier in (value or [])):
                    found.append(item["id"])
                    break
        return found

    def remove(self, identifier):
        """Remove one entry or open question the participants withdraw."""
        identifier = _text(identifier, "The identifier")
        if identifier[:1] in ("H", "N", "R") and self.schema.kind_of(identifier) is None:
            raise Refused("Hints, notes and findings cannot be removed.")
        if identifier.startswith("Q") and self.schema.kind_of(identifier) is None:
            self._find("openQuestions", identifier, "open question")
            self.data["openQuestions"] = [q for q in self.data["openQuestions"] if q["id"] != identifier]
            return
        self.item(identifier)
        named = self.referring_to(identifier)
        if named:
            raise Refused("It is named by " + ", ".join(named) + ". Change or remove those first.")
        self.data["items"] = [item for item in self.data["items"] if item["id"] != identifier]
        if self.notes_posted:
            self.data["removedAfterNotes"].append(identifier)

    def lacking(self, stage=None):
        """Return (identifier, [field names]) for what the stage is meant to fill and has not."""
        stage = self.schema.stage(stage or self.data["stage"])
        found = []
        for kind_name, field_names in (stage.fills if stage else {}).items():
            for item in self.items_of(kind_name):
                missing = [name for name in field_names if _empty(item["values"].get(name))]
                if missing:
                    found.append((item["id"], missing))
        return found

    # --- open questions, hints, notes, findings -------------------------------

    def add_open_question(self, text):
        question = {"id": self._next_id("Q"), "text": _text(text, "The question")}
        self.data["openQuestions"].append(question)
        return question

    def give_hint(self, about, point):
        """Record that a hint is being given. At most one for each entry in each stage,
        and one in each stage that is about no entry."""
        stage = self.data["stage"]
        about = about or None
        if about:
            self.item(about)
        if any(h["stage"] == stage and h["about"] == about for h in self.data["hints"]):
            raise Refused(
                "A hint has already been given here in this stage. Give no second hint: "
                "record the point with add_note, kind not_raised, and say nothing about it."
            )
        hint = {
            "id": self._next_id("H"), "stage": stage, "about": about,
            "point": _text(point, "The point"), "takenUp": False,
        }
        self.data["hints"].append(hint)
        return hint

    def hint_taken_up(self, identifier):
        self._find("hints", identifier, "hint")["takenUp"] = True

    def add_note(self, kind, text, about=None):
        about = about or None
        if about:
            self.item(about)
        note = {
            "id": self._next_id("N"),
            "kind": _one_of(kind, NOTE_KINDS, "The kind"),
            "stage": self.data["stage"],
            "about": about,
            "text": _text(text, "The text"),
        }
        self.data["notes"].append(note)
        return note

    def add_finding(self, kind, repository, file, fact, files_read):
        """Record what the agent found in a repository file it has read in this session."""
        if file not in files_read:
            raise Refused(f"{file} has not been read from {repository} in this session.")
        finding = {
            "id": self._next_id("R"),
            "kind": _one_of(kind, FINDING_KINDS, "The kind"),
            "repository": repository, "file": file,
            "fact": _text(fact, "The fact"),
            "reported": bool(self.data["findingsReleased"]),
        }
        self.data["findings"].append(finding)
        return finding

    def release_findings(self):
        """Stop holding findings back, and return those that were being held."""
        self.data["findingsReleased"] = True
        held = [finding for finding in self.data["findings"] if not finding["reported"]]
        for finding in held:
            finding["reported"] = True
        return held

    # --- stages and endings ---------------------------------------------------

    def _enter(self, stage):
        self.data["stage"] = stage
        self.data["stages"][stage] = "in_progress"

    def _leave(self, status):
        """Give the current stage a status and enter the next. Return the next stage, or None."""
        stages = self.schema.stage_names
        stage = self.data["stage"]
        self.data["stages"][stage] = status
        self.released = self.release_findings() if stage == self.schema.findings_after else []
        position = stages.index(stage)
        if position + 1 < len(stages):
            self._enter(stages[position + 1])
            return stages[position + 1]
        return None

    def complete_stage(self):
        """Complete the current stage. Never refused.

        Returns what the model needs to say next: the stage entered (None after
        the last), what the stage was meant to fill and did not, and any
        repository findings released by completing it.
        """
        left = self.data["stage"]
        lacking = self.lacking(left)
        entered = self._leave("complete")
        return {"left": left, "entered": entered, "lacking": lacking, "released": self.released}

    def go_to_stage(self, stage):
        _one_of(stage, self.schema.stage_names, "The stage")
        self._enter(stage)

    def request_change(self, action):
        """Ask to skip the stage, finish or abandon. Return 'applied' or 'pending'."""
        _one_of(action, CHANGES, "The action")
        if not self.in_progress:
            raise Refused("The session has already ended.")
        if action == "skip_stage" and len(self.data["participants"]) <= 1:
            self._leave("skipped")
            self.data["pending"] = None
            return "applied"
        self.data["pending"] = {
            "action": action, "stage": self.data["stage"], "announcedOnTurn": self.data["turn"],
        }
        return "pending"

    def resolve_change(self, confirmed):
        """Confirm or drop the pending change. Return the action applied, or None when dropped."""
        pending = self.data["pending"]
        if not pending:
            raise Refused("Nothing is pending. If the participants want it, they ask again.")
        if not confirmed:
            self.data["pending"] = None
            return None
        if pending["announcedOnTurn"] >= self.data["turn"]:
            raise Refused(
                "It was only just announced. Wait for the next message, and confirm then "
                "unless that message objects."
            )
        self.data["pending"] = None
        action = pending["action"]
        if action == "skip_stage":
            if self.data["stage"] == pending["stage"]:
                self._leave("skipped")
            else:
                self.data["stages"][pending["stage"]] = "skipped"
                if pending["stage"] == self.schema.findings_after:
                    self.released = self.release_findings()
            return action
        if action == "finish":
            self.data["stages"][self.schema.last_stage] = "complete"
            self.data["status"] = FINISHED
        else:
            self.data["status"] = ABANDONED
        self.data["notesPostedOnTurn"] = self.data["turn"]
        return action

    def unfinished_stages(self):
        """Return (stage, status) for every stage that is not complete."""
        return [(stage, self.data["stages"][stage]) for stage in self.schema.stage_names
                if self.data["stages"][stage] != "complete"]


# --- the agent's state --------------------------------------------------------


def load(state, skills):
    """Return the session record in the state, or None.

    skills maps a skill's name to something with a schema. A record of a skill
    the agent no longer has, or one that no longer fits its schema, counts as
    no session.
    """
    data = state.get(KEY_SESSION)
    if not isinstance(data, dict):
        return None
    skill = skills.get(data.get("skill"))
    if skill is None:
        return None
    try:
        return Record.from_dict(data, skill.schema)
    except ValueError:
        return None


def save(state, record):
    state.set(KEY_SESSION, record.to_dict() if record else None)


def load_repositories(state):
    repositories = state.get(KEY_REPOSITORIES)
    return copy.deepcopy(repositories) if isinstance(repositories, list) else []


def save_repositories(state, repositories):
    state.set(KEY_REPOSITORIES, copy.deepcopy(repositories))


def _restore(state):
    before = state.get(KEY_SESSION_BEFORE)
    if isinstance(before, dict):
        state.set(KEY_SESSION, copy.deepcopy(before.get(KEY_SESSION)))
        state.set(KEY_REPOSITORIES, copy.deepcopy(before.get(KEY_REPOSITORIES) or []))


def begin_message(state, message_id):
    """Prepare the state for one message. Return True when the message is a repeat.

    What a message leads the agent to record is recorded once or not at all: a
    message whose handling never finished is undone first, and a second request
    for the same message starts again from before the first.
    """
    if state.get(KEY_LAST_MESSAGE_DONE) is False:
        _restore(state)
    repeat = bool(message_id) and message_id == state.get(KEY_LAST_MESSAGE_ID)
    if repeat:
        _restore(state)
    else:
        state.set(KEY_SESSION_BEFORE, {
            KEY_SESSION: copy.deepcopy(state.get(KEY_SESSION)),
            KEY_REPOSITORIES: copy.deepcopy(state.get(KEY_REPOSITORIES) or []),
        })
        state.set(KEY_LAST_MESSAGE_ID, message_id or None)
    state.set(KEY_LAST_MESSAGE_DONE, False)
    return repeat


def end_message(state):
    """Mark the current message as handled to its end."""
    state.set(KEY_LAST_MESSAGE_DONE, True)
