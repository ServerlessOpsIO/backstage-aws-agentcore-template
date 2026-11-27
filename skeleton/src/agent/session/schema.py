"""What a skill says a session is made of: its stages and what it records.

Each skill has a session.yaml beside its SKILL.md. It names the stages a
session goes through, the kinds of entry the participants give in each, and the
document made from them at the end. Everything else in this package works from
it: the record, the tools the model is offered, what the model is told about
the session, and the written document. A new kind of conversation is a new
session.yaml and the words that go with it, not new code.

The format is described in docs/handbook/10-guided-sessions.md.

This module reads YAML and nothing else. It imports nothing from the agent
framework, so scripts and tests can use it on its own.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

FILE_NAME = "session.yaml"

TEXT = "text"
CHOICE = "choice"
REF = "ref"
REFS = "refs"
PEOPLE = "people"
FIELD_TYPES = (TEXT, CHOICE, REF, REFS, PEOPLE)

TABLE = "table"
LIST = "list"
LAYOUTS = (TABLE, LIST)

# Identifiers the engine gives out itself: hints, notes, open questions and
# what was found in a repository.
RESERVED_PREFIXES = ("H", "N", "Q", "R")

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_STAGE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
_PREFIX = re.compile(r"^[A-Z]{1,3}$")
_FILE_STEM = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
_IDENTIFIER = re.compile(r"^([A-Z]{1,3})(\d+)$")
# Names the tools use for their own arguments.
_RESERVED_FIELDS = ("id",)

MAX_STAGES = 12
MAX_KINDS = 20
MAX_FIELDS = 12


class SchemaError(Exception):
    """A session.yaml cannot be used as it is."""


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    title: str
    description: str
    required: bool
    choices: tuple
    to: str


@dataclass(frozen=True)
class Kind:
    """One kind of entry, such as an option or a decision."""

    name: str
    prefix: str
    title: str
    singular: str
    description: str
    layout: str
    group_by: str
    label: str
    fields: tuple

    def field(self, name):
        for candidate in self.fields:
            if candidate.name == name:
                return candidate
        return None


@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    records: tuple
    fills: dict


@dataclass(frozen=True)
class Schema:
    subject: str
    document_title: str
    document_filename: str
    method: str
    opening: tuple
    findings_after: str
    stages: tuple
    kinds: dict

    @property
    def stage_names(self):
        return tuple(stage.name for stage in self.stages)

    @property
    def last_stage(self):
        return self.stages[-1].name

    def stage(self, name):
        for candidate in self.stages:
            if candidate.name == name:
                return candidate
        return None

    def stage_title(self, name):
        stage = self.stage(name)
        return stage.title if stage else str(name)

    def kind_of(self, identifier):
        """Return the kind an identifier such as "T3" belongs to, or None."""
        match = _IDENTIFIER.match(str(identifier or ""))
        if not match:
            return None
        for kind in self.kinds.values():
            if kind.prefix == match.group(1):
                return kind
        return None

    def stage_of(self, kind_name):
        """Return the first stage in which a kind is recorded, or None."""
        for stage in self.stages:
            if kind_name in stage.records:
                return stage
        return None


def _words(name):
    return name.replace("_", " ").replace("-", " ")


def _string(value, what, default=None):
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{what} must be text")
    return " ".join(value.split())


def _mapping(value, what):
    if not isinstance(value, dict) or not value:
        raise SchemaError(f"{what} must be a mapping with at least one entry")
    return value


def _field(kind_name, name, spec, kinds):
    where = f"records.{kind_name}.fields.{name}"
    if not isinstance(name, str) or not _NAME.match(name) or name in _RESERVED_FIELDS:
        raise SchemaError(f"{where}: a field's name is lower case letters, digits and _, and not 'id'")
    spec = spec or {}
    if not isinstance(spec, dict):
        raise SchemaError(f"{where} must be a mapping")
    unknown = set(spec) - {"type", "title", "description", "required", "choices", "to"}
    if unknown:
        raise SchemaError(f"{where}: unknown setting {sorted(unknown)[0]}")
    kind = spec.get("type", CHOICE if "choices" in spec else TEXT)
    if kind not in FIELD_TYPES:
        raise SchemaError(f"{where}.type must be one of: {', '.join(FIELD_TYPES)}")

    choices = ()
    if kind == CHOICE:
        given = spec.get("choices")
        if not isinstance(given, list) or len(given) < 2:
            raise SchemaError(f"{where}.choices must list at least two values")
        choices = tuple(str(choice) for choice in given)
        if any(not _NAME.match(choice) for choice in choices) or len(set(choices)) != len(choices):
            raise SchemaError(f"{where}.choices: each is lower case letters, digits and _, given once")
    elif "choices" in spec:
        raise SchemaError(f"{where}: only a choice has choices")

    to = ""
    if kind in (REF, REFS):
        to = spec.get("to")
        if to not in kinds:
            raise SchemaError(f"{where}.to must name a kind of record")
    elif "to" in spec:
        raise SchemaError(f"{where}: only a ref or refs has 'to'")

    title = _string(spec.get("title"), f"{where}.title", _words(name).capitalize())
    return Field(
        name=name,
        type=kind,
        title=title,
        description=_string(spec.get("description"), f"{where}.description", title + "."),
        required=spec.get("required") is True,
        choices=choices,
        to=to,
    )


def _kind(name, spec, kinds, prefixes):
    where = f"records.{name}"
    if not isinstance(name, str) or not _NAME.match(name):
        raise SchemaError(f"{where}: a kind's name is lower case letters, digits and _")
    spec = _mapping(spec, where)
    unknown = set(spec) - {"prefix", "title", "singular", "description", "layout", "group_by",
                           "label", "fields"}
    if unknown:
        raise SchemaError(f"{where}: unknown setting {sorted(unknown)[0]}")

    prefix = spec.get("prefix")
    if not isinstance(prefix, str) or not _PREFIX.match(prefix):
        raise SchemaError(f"{where}.prefix must be one to three capital letters")
    if prefix in RESERVED_PREFIXES:
        raise SchemaError(f"{where}.prefix: {', '.join(RESERVED_PREFIXES)} are taken")
    if prefix in prefixes:
        raise SchemaError(f"{where}.prefix: {prefix} is used twice")
    prefixes.add(prefix)

    given = _mapping(spec.get("fields"), f"{where}.fields")
    if len(given) > MAX_FIELDS:
        raise SchemaError(f"{where}: at most {MAX_FIELDS} fields")
    fields = tuple(_field(name, field_name, field_spec, kinds) for field_name, field_spec in given.items())
    if not any(field.required for field in fields):
        raise SchemaError(f"{where}: at least one field must be required")

    layout = spec.get("layout", TABLE)
    if layout not in LAYOUTS:
        raise SchemaError(f"{where}.layout must be one of: {', '.join(LAYOUTS)}")
    by_name = {field.name: field for field in fields}
    group_by = spec.get("group_by") or ""
    if group_by and (group_by not in by_name or by_name[group_by].type != CHOICE):
        raise SchemaError(f"{where}.group_by must name one of its choice fields")
    label = spec.get("label") or ""
    if label and (label not in by_name or by_name[label].type != TEXT):
        raise SchemaError(f"{where}.label must name one of its text fields")

    singular = _string(spec.get("singular"), f"{where}.singular", _words(name))
    return Kind(
        name=name,
        prefix=prefix,
        title=_string(spec.get("title"), f"{where}.title", singular.capitalize()),
        singular=singular,
        description=_string(
            spec.get("description"), f"{where}.description",
            f"Record one {singular} a participant gave. Never one of your own.",
        ),
        layout=layout,
        group_by=group_by,
        label=label,
        fields=fields,
    )


def _stage(spec, kinds, seen):
    if not isinstance(spec, dict):
        raise SchemaError("each stage must be a mapping")
    name = spec.get("name")
    if not isinstance(name, str) or not _STAGE.match(name):
        raise SchemaError("a stage's name is lower case letters, digits and -")
    if name in seen:
        raise SchemaError(f"the stage {name} is given twice")
    seen.add(name)
    where = f"stages.{name}"
    unknown = set(spec) - {"name", "title", "records", "fills"}
    if unknown:
        raise SchemaError(f"{where}: unknown setting {sorted(unknown)[0]}")

    records = spec.get("records") or []
    if not isinstance(records, list) or any(kind not in kinds for kind in records):
        raise SchemaError(f"{where}.records must list kinds of record")
    fills = spec.get("fills") or {}
    if not isinstance(fills, dict):
        raise SchemaError(f"{where}.fills must map a kind of record to its fields")
    cleaned = {}
    for kind_name, field_names in fills.items():
        if kind_name not in kinds:
            raise SchemaError(f"{where}.fills: {kind_name} is not a kind of record")
        if not isinstance(field_names, list) or not field_names:
            raise SchemaError(f"{where}.fills.{kind_name} must list fields")
        for field_name in field_names:
            if kinds[kind_name].field(field_name) is None:
                raise SchemaError(f"{where}.fills.{kind_name}: {field_name} is not one of its fields")
        cleaned[kind_name] = tuple(field_names)
    return Stage(
        name=name,
        title=_string(spec.get("title"), f"{where}.title", _words(name).capitalize()),
        records=tuple(records),
        fills=cleaned,
    )


def parse(data):
    """Return the Schema described by the content of a session.yaml."""
    data = _mapping(data, "session.yaml")
    unknown = set(data) - {"subject", "document", "opening", "findings_after", "stages", "records"}
    if unknown:
        raise SchemaError(f"unknown setting {sorted(unknown)[0]}")

    document = _mapping(data.get("document"), "document")
    filename = document.get("filename")
    if not isinstance(filename, str) or not _FILE_STEM.match(filename):
        raise SchemaError("document.filename is lower case letters, digits and -")

    given = _mapping(data.get("records"), "records")
    if len(given) > MAX_KINDS:
        raise SchemaError(f"at most {MAX_KINDS} kinds of record")
    # Two passes, so that a field may refer to a kind given after its own.
    kinds, prefixes = dict.fromkeys(given), set()
    for name, spec in given.items():
        kinds[name] = _kind(name, spec, kinds, prefixes)

    stages = data.get("stages")
    if not isinstance(stages, list) or not 2 <= len(stages) <= MAX_STAGES:
        raise SchemaError(f"stages must list between 2 and {MAX_STAGES} stages")
    seen = set()
    stages = tuple(_stage(spec, kinds, seen) for spec in stages)
    for name in kinds:
        if not any(name in stage.records for stage in stages):
            raise SchemaError(f"records.{name} is recorded in no stage")

    findings_after = data.get("findings_after") or ""
    if findings_after and findings_after not in seen:
        raise SchemaError("findings_after must name a stage")

    opening = data.get("opening") or []
    if not isinstance(opening, list) or any(not isinstance(point, str) for point in opening):
        raise SchemaError("opening must be a list of sentences")

    return Schema(
        subject=_string(data.get("subject"), "subject"),
        document_title=_string(document.get("title"), "document.title"),
        document_filename=filename,
        method=_string(document.get("method"), "document.method", ""),
        opening=tuple(" ".join(point.split()) for point in opening if point.strip()),
        findings_after=findings_after,
        stages=stages,
        kinds=kinds,
    )


def load(folder):
    """Return the Schema of the skill in a folder. Raises SchemaError when it has none or a bad one."""
    path = Path(folder) / FILE_NAME
    if not path.is_file():
        raise SchemaError(f"no {FILE_NAME}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SchemaError(f"{FILE_NAME} is not valid YAML") from error
    return parse(data)
