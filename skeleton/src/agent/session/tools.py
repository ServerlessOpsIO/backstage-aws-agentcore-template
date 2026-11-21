"""The tools the model calls to change the session record.

One Turn is made for each request. Some tools are the same for every skill:
starting a session, moving between stages, hints, notes and the document. The
rest are made from the skill's session.yaml: for each kind of entry it names
there is an add_<kind> and an update_<kind> tool, whose arguments are the
kind's fields. Each tool reads the record from the agent's state, applies one
change through record.py, saves it, and answers with a short sentence the
model acts on.

The model is offered only the tools of the current stage. The rules are kept
here and in record.py, whatever the model was told. A refused call answers
with the reason and is not an error.

Nothing in this module logs what a tool was given or what it answered: both
hold what people said. A failure is logged by its type alone.
"""

import functools
import inspect
import logging

from strands import tool
from strands.tools.tools import PythonAgentTool

from session import record as rec
from session import render
from session import schema as sch
from session.record import Record, Refused
from session.summary import fields_line

logger = logging.getLogger("agent")

CHANNEL_THREAD = "channel_thread"
DIRECT_MESSAGE = "direct_message"

START = "start_session"
SESSION_TOOLS = (
    "complete_stage", "go_to_stage", "request_change", "resolve_change", "add_open_question",
    "give_hint", "hint_taken_up", "add_note", "write_document", "remove_item",
)
READING_TOOLS = ("list_repository_files", "read_repository_file")
REPOSITORY_TOOLS = READING_TOOLS + ("hold_finding",)
# What stays on offer once a session has ended, besides the tools for its entries.
AFTER_THE_END = ("add_open_question", "write_document", "remove_item")
STATIC_TOOLS = (START,) + SESSION_TOOLS

SOMETHING_WENT_WRONG = (
    "That could not be done because of a fault, not because of what was asked. "
    "Tell the participants it was not recorded and carry on."
)


def add_tool(kind_name):
    return f"add_{kind_name}"


def update_tool(kind_name):
    return f"update_{kind_name}"


def _entry_tools(kind_names):
    return tuple(name for kind in kind_names for name in (add_tool(kind), update_tool(kind)))


def tools_for(record):
    """Return the names of the tools the model is offered for the record as it stands."""
    if record is None:
        return (START,) + READING_TOOLS
    schema = record.schema
    if record.in_progress:
        stage = schema.stage(record["stage"])
        filled = tuple(update_tool(kind) for kind in stage.fills if kind not in stage.records)
        return SESSION_TOOLS + REPOSITORY_TOOLS + _entry_tools(stage.records) + filled
    return (START,) + REPOSITORY_TOOLS + _entry_tools(schema.kinds) + AFTER_THE_END


def _answers(method):
    """Make a tool method answer with a sentence whatever happens inside it."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        self.tool_calls += 1
        try:
            return method(self, *args, **kwargs)
        except Refused as refusal:
            return f"Not done. {refusal}"
        except Exception as error:  # A fault must not cost the reply, or reach a log with its text.
            logger.error("Tool %s failed: %s", method.__name__, type(error).__name__)
            return SOMETHING_WENT_WRONG
    return wrapper


def _changes(method):
    """Run a tool method against the session record and save what it did."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        session = rec.load(self.state, self.skills)
        if session is None:
            raise Refused("There is no session. Start one first.")
        answer = method(self, session, *args, **kwargs)
        rec.save(self.state, session)
        return answer
    signature = inspect.signature(method)
    wrapper.__signature__ = signature.replace(
        parameters=[p for name, p in signature.parameters.items() if name != "session"]
    )
    return wrapper


def _recorded(what):
    return f"Recorded as {what} Say this back to the participants in one line, with the identifier."


class Turn:
    """What one request needs to run the tools: the state, who is speaking, and what to attach.

    skills maps each skill's name to the loaded skill, which has the schema its
    sessions follow. agent_name is what the agent is called in the documents.
    """

    def __init__(self, state, speaker, skills, conversation_type=DIRECT_MESSAGE,
                 thread_ends_at=None, today=None, agent_name="The agent"):
        self.state = state
        self.speaker = speaker
        self.skills = skills
        self.conversation_type = conversation_type
        self.thread_ends_at = thread_ends_at
        self.today = today
        self.agent_name = agent_name
        self.documents = []
        self.tool_calls = 0

    # --- documents ------------------------------------------------------------

    def _attach(self, session, kind, markdown):
        name = render.filename(session, kind)
        self.documents = [d for d in self.documents if d["filename"] != name]
        self.documents.append({
            "filename": name, "title": render.title(session, kind), "markdown": markdown,
        })

    def _attach_documents(self, session, notes):
        repositories = rec.load_repositories(self.state)
        self._attach(session, render.DOCUMENT, render.written_document(
            session, repositories, self.today, self.agent_name))
        if notes:
            self._attach(session, render.NOTES, render.facilitator_notes(session, self.agent_name))

    # --- starting -------------------------------------------------------------

    def _skill(self, name):
        name = (name or "").strip()
        if name in self.skills:
            return name
        if len(self.skills) == 1:
            return next(iter(self.skills))
        raise Refused("Say which skill the session uses. One of: " + ", ".join(self.skills) + ".")

    @_answers
    def start_session(self, skill: str, subject: str) -> str:
        """Start a session with one of your skills. Use only when someone asks for one.

        Args:
            skill: The name of the skill the session uses, as given under AVAILABLE SKILLS.
            subject: The name of what the session is about, as the person gave it.
        """
        skill = self._skill(skill)
        schema = self.skills[skill].schema
        last = rec.load(self.state, self.skills)
        if last and last.in_progress:
            raise Refused(
                f"A session on \"{last['subject']}\" is in progress. Ask whether to continue it "
                "or abandon it."
            )
        if last and last["replaceWarnedOnTurn"] in (None, last["turn"]):
            last.data["replaceWarnedOnTurn"] = last["turn"]
            rec.save(self.state, last)
            raise Refused(
                f"The session on \"{last['subject']}\" has ended. Tell them that starting a new one "
                "replaces it: it can then no longer be changed or asked for, though any files "
                "already posted stay where they are. If they still want to, call start_session "
                "again on their next message."
            )

        session = Record.start(skill, schema, subject, self.speaker, self.today)
        rec.save(self.state, session)
        repositories = rec.load_repositories(self.state)
        for repository in repositories:
            repository["filesRead"] = []
        rec.save_repositories(self.state, repositories)

        titles = [stage.title.lower() for stage in schema.stages]
        points = [
            f"the {len(titles)} stages: {', '.join(titles)}",
            "the participants do the work and you facilitate: you ask, explain and record",
            "you keep notes on what was missed, posted with the document when the session ends",
        ]
        points += list(schema.opening)
        if self.conversation_type == CHANNEL_THREAD:
            points += [
                "you may stay quiet when they talk among themselves, and a mention always gets a reply",
                "you see only what full members of the workspace write",
            ]
            if self.thread_ends_at:
                points.append(f"this thread stops being answered at {self.thread_ends_at} (UTC), "
                              "so the session must finish before then")
        return (
            f"Session started on \"{session['subject']}\". Give the opening now, briefly, "
            "covering: " + "; ".join(points) + f". Then name the {titles[0]} stage and ask "
            "its first question."
        )

    # --- moving through the session -------------------------------------------

    def _findings_text(self, findings):
        if not findings:
            return ""
        listed = " ".join(
            f"[{f['kind'].replace('_', ' ')}] {f['repository']}/{f['file']}: {f['fact']}"
            for f in findings
        )
        return (
            "Report these repository findings now, together, as facts, naming each file, and "
            "ask the participants which is right or whether it belongs in the record. Add "
            f"nothing to the record until they say so. {listed}"
        )

    def _entered(self, session, entered):
        if entered:
            return (f"Now in the {session.schema.stage_title(entered).lower()} stage. Name it "
                    "and ask its first question.")
        return "That was the last stage. Ask whether the participants want to finish."

    @_answers
    @_changes
    def complete_stage(self, session) -> str:
        """Mark the current stage complete and enter the next. Use when the participants have nothing more to add to it."""
        done = session.complete_stage()
        parts = [f"The {session.schema.stage_title(done['left']).lower()} stage is complete."]
        if done["lacking"]:
            listed = "; ".join(
                f"{identifier}: {', '.join(render.words(name) for name in missing)}"
                for identifier, missing in done["lacking"]
            )
            parts.append(
                f"Left unfilled: {listed}. Say once that these will show as empty in the "
                "document and that they can go back. This is not a hint; supply nothing yourself."
            )
        parts.append(self._findings_text(done["released"]))
        parts.append(self._entered(session, done["entered"]))
        return " ".join(part for part in parts if part)

    @_answers
    @_changes
    def go_to_stage(self, session, stage: str) -> str:
        """Go to another stage, earlier or later, without completing or skipping the current one.

        Args:
            stage: The name of the stage, as it appears in the session record.
        """
        session.go_to_stage(stage)
        return f"Now in the {session.schema.stage_title(stage).lower()} stage. Say so."

    def _skipped(self, session):
        if session.in_progress and session["stages"][session["stage"]] == "in_progress":
            entered = session["stage"]
        else:
            entered = None
        return " ".join(part for part in (
            "Skipped.", self._findings_text(session.released), self._entered(session, entered),
        ) if part)

    @_answers
    @_changes
    def request_change(self, session, action: str) -> str:
        """Record that a participant asked to skip the current stage, finish the session or abandon it.

        Args:
            action: One of skip_stage, finish, abandon.
        """
        if session.request_change(action) == "applied":
            return self._skipped(session)
        if action == "skip_stage":
            return (
                "Pending. Tell the participants the stage is about to be skipped. On the next "
                "message call resolve_change, confirmed true unless that message objects."
            )
        return (
            "Pending. Tell the participants that the document and your notes are about to "
            "be posted and that changes made afterwards will be marked. On the next message "
            "call resolve_change, confirmed true unless that message objects."
        )

    @_answers
    @_changes
    def resolve_change(self, session, confirmed: bool) -> str:
        """Confirm or drop the change that was announced. Use on the message after the announcement.

        Args:
            confirmed: True when the message does not object. False when it objects, asks to wait or questions it.
        """
        action = session.resolve_change(confirmed)
        if action is None:
            return "Dropped. Carry on with the session. If they ask again later, announce it afresh."
        if action == "skip_stage":
            return self._skipped(session)
        self._attach_documents(session, notes=True)
        word = "finished" if action == "finish" else "abandoned"
        return (
            f"The session is {word}. The document and the facilitator's notes are attached "
            "to this reply as files. Say so in a sentence or two. Do not write them out."
        )

    @_answers
    @_changes
    def write_document(self, session) -> str:
        """Attach the written document to this reply as a file. Use when asked for the document."""
        self._attach_documents(session, notes=session.ended)
        if session.ended:
            return ("The document and the facilitator's notes are attached as files. "
                    "Say so. Do not write them out.")
        return ("The document as it stands is attached as a file, with unfinished stages "
                "marked. Say so. Do not write it out.")

    @_answers
    @_changes
    def add_open_question(self, session, text: str) -> str:
        """Record something the participants could not answer or agree on.

        Args:
            text: The question, in their words.
        """
        question = session.add_open_question(text)
        return _recorded(f"{question['id']}, an open question: {question['text']}.")

    @_answers
    @_changes
    def remove_item(self, session, id: str) -> str:
        """Remove something the participants withdraw.

        Args:
            id: The identifier of an entry or an open question.
        """
        session.remove(id)
        return f"Removed {id}. Say so."

    # --- hints and notes ------------------------------------------------------

    @_answers
    @_changes
    def give_hint(self, session, point: str, about: str = "") -> str:
        """Record that you are about to give a hint. Call this before giving it.

        Args:
            point: What the participants have missed. For your notes, not for saying.
            about: The identifier of the entry it is about. Leave empty when it is about the stage as a whole.
        """
        hint = session.give_hint(about, point)
        return (
            f"Noted as {hint['id']}. Now give the hint: point at the area and DO NOT give the "
            "answer. If they take it up, call hint_taken_up."
        )

    @_answers
    @_changes
    def hint_taken_up(self, session, hint: str) -> str:
        """Record that the participants raised the point after a hint.

        Args:
            hint: The hint's identifier, such as H1.
        """
        session.hint_taken_up(hint)
        return "Noted."

    @_answers
    @_changes
    def add_note(self, session, kind: str, text: str, about: str = "") -> str:
        """Add to your facilitator's notes. Say nothing about it to the participants.

        Args:
            kind: not_raised for a missed point you could not hint at; questioned_kept for something you questioned and they kept.
            text: The point, or what you questioned.
            about: The identifier of the entry it is about, if any.
        """
        session.add_note(kind, text, about or None)
        return "Noted. Do not mention it."

    # --- what the participants give -------------------------------------------

    @_answers
    @_changes
    def add_item(self, session, kind: str, values: dict) -> str:
        """Record one entry of a kind. The model reaches this through an add_<kind> tool."""
        item = session.add_item(kind, values)
        return _recorded(self._read_back(session, item))

    @_answers
    @_changes
    def update_item(self, session, id: str, values: dict) -> str:
        """Change an entry. The model reaches this through an update_<kind> tool."""
        return _recorded(self._read_back(session, session.update_item(id, values)))

    def _read_back(self, session, item):
        singular = session.schema.kinds[item["kind"]].singular
        return f"{item['id']}, {render.a(singular)}: {fields_line(session, item)}."

    # --- the tools made from session.yaml -------------------------------------

    def _run(self, call, tool_use):
        answer = call(dict(tool_use.get("input") or {}))
        return {"toolUseId": tool_use["toolUseId"], "status": "success", "content": [{"text": answer}]}

    def _entry_tool(self, name, description, properties, required, call):
        spec = {
            "name": name,
            "description": description,
            "inputSchema": {"json": {"type": "object", "properties": properties, "required": required}},
        }
        return PythonAgentTool(name, spec, lambda tool_use, **_: self._run(call, tool_use))

    def entry_tools(self, schema):
        """Return the add and update tools for every kind of entry in a schema, by name."""
        tools = {}
        for kind in schema.kinds.values():
            properties = {field.name: _property(field, schema) for field in kind.fields}
            required = [field.name for field in kind.fields if field.required]
            tools[add_tool(kind.name)] = self._entry_tool(
                add_tool(kind.name), kind.description, properties, required,
                lambda values, kind=kind: self.add_item(kind.name, values),
            )
            identifier = {"type": "string",
                          "description": f"The identifier of the {kind.singular}, such as {kind.prefix}1."}
            tools[update_tool(kind.name)] = self._entry_tool(
                update_tool(kind.name),
                f"Change or fill in {render.a(kind.singular)} already recorded, when a participant corrects "
                "it or adds to it. Give only what changes.",
                {"id": identifier, **properties}, ["id"],
                lambda values, kind=kind: self._update_of(kind, values),
            )
        return tools

    def _update_of(self, kind, values):
        identifier = values.pop("id", "")
        session = rec.load(self.state, self.skills)
        target = session.schema.kind_of(identifier) if session else None
        if target is not None and target.name != kind.name:
            self.tool_calls += 1
            return f"Not done. {identifier} is {render.a(target.singular)}, not {render.a(kind.singular)}."
        return self.update_item(identifier, values)


def _property(field, schema):
    """Return one field as the JSON Schema of a tool argument."""
    if field.type == sch.CHOICE:
        return {"type": "string", "enum": list(field.choices), "description": field.description}
    if field.type == sch.REF:
        target = schema.kinds[field.to]
        return {"type": "string",
                "description": f"{field.description} The identifier of {render.a(target.singular)}, such as {target.prefix}1."}
    if field.type == sch.REFS:
        target = schema.kinds[field.to]
        return {"type": "array", "items": {"type": "string"},
                "description": f"{field.description} The identifiers of each {target.singular}, such as {target.prefix}1."}
    if field.type == sch.PEOPLE:
        return {"type": "array", "items": {"type": "string"},
                "description": f"{field.description} Names of participants, as given in the session record."}
    return {"type": "string", "description": field.description}


def make_tools(turn, extra=None):
    """Return the tools every skill shares, as {name: tool}, bound to one request's Turn.

    The tools for a skill's entries are added by current_tools, once there is a
    session to say which skill is in use. extra adds tools kept elsewhere, such
    as the repository tools, by name.
    """
    tools = {name: tool(getattr(turn, name)) for name in STATIC_TOOLS}
    for name, function in (extra or {}).items():
        tools[name] = tool(function)
    return tools


def current_tools(turn, tools, record, always=()):
    """Return {name: tool} for exactly what the model is offered for the record as it stands.

    always names tools that are offered whatever the session's state.
    """
    available = dict(tools)
    if record is not None:
        available.update(turn.entry_tools(record.schema))
    return {name: available[name] for name in tools_for(record) + tuple(always) if name in available}
