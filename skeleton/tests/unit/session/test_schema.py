"""Unit tests for reading a skill's session.yaml."""

import copy

import pytest
import yaml

import example
from session import schema as sch

GOOD = yaml.safe_load((example.SKILLS_DIR / example.SKILL / "session.yaml").read_text())


def changed(change):
    data = copy.deepcopy(GOOD)
    change(data)
    return data


def test_the_schema_holds_what_the_file_says():
    schema = sch.parse(GOOD)
    assert schema.subject == "system"
    assert schema.document_title == "Review" and schema.document_filename == "review"
    assert schema.method == "Checked by hand."
    assert schema.opening == ("you will not name findings",)
    assert schema.stage_names == ("scope", "parts", "findings", "rating", "plan", "report")
    assert schema.last_stage == "report" and schema.findings_after == "parts"
    assert list(schema.kinds) == ["scope_item", "part", "finding", "fix"]
    assert schema.stage("rating").fills == {"finding": ("level",)}
    assert schema.stage("plan").records == ("fix", "finding")


def test_what_is_left_out_is_given_a_default():
    part = sch.parse(GOOD).kinds["part"]
    assert part.singular == "part" and part.layout == sch.TABLE
    assert part.description == "Record one part a participant gave. Never one of your own."
    name, description = part.fields
    assert name.type == sch.TEXT and name.title == "Name" and name.required
    assert description.description == "Description." and not description.required
    assert sch.parse(GOOD).kinds["scope_item"].field("kind").type == sch.CHOICE


def test_an_identifier_leads_to_its_kind():
    schema = sch.parse(GOOD)
    assert schema.kind_of("F3").name == "finding"
    assert schema.kind_of("FX12").name == "fix"
    for identifier in ("Q1", "H2", "Z1", "F", "f1", "", None):
        assert schema.kind_of(identifier) is None


def test_a_kind_s_first_stage_is_found():
    schema = sch.parse(GOOD)
    assert schema.stage_of("finding").name == "findings"
    assert schema.stage_of("fix").name == "plan"


@pytest.mark.parametrize("change, problem", [
    (lambda d: d.pop("subject"), "subject"),
    (lambda d: d.pop("document"), "document"),
    (lambda d: d["document"].update(filename="My File"), "document.filename"),
    (lambda d: d.update(stages=d["stages"][:1]), "stages"),
    (lambda d: d["stages"].append({"name": "scope"}), "given twice"),
    (lambda d: d["stages"][0].update(name="Scope"), "stage's name"),
    (lambda d: d["stages"][0].update(records=["nothing"]), "stages.scope.records"),
    (lambda d: d["stages"][3].update(fills={"finding": ["nothing"]}), "nothing is not one of its fields"),
    (lambda d: d["stages"][3].update(fills={"nothing": ["level"]}), "not a kind of record"),
    (lambda d: d["stages"][0].update(colour="red"), "unknown setting colour"),
    (lambda d: d.update(findings_after="nowhere"), "findings_after"),
    (lambda d: d.update(opening="one sentence"), "opening"),
    (lambda d: d.update(extra=1), "unknown setting extra"),
    (lambda d: d["records"]["part"].pop("prefix"), "records.part.prefix"),
    (lambda d: d["records"]["part"].update(prefix="Q"), "are taken"),
    (lambda d: d["records"]["part"].update(prefix="F"), "used twice"),
    (lambda d: d["records"]["part"].update(layout="grid"), "records.part.layout"),
    (lambda d: d["records"]["part"].update(label="nothing"), "records.part.label"),
    (lambda d: d["records"]["part"].update(group_by="name"), "records.part.group_by"),
    (lambda d: d["records"]["part"]["fields"]["name"].update(required=False), "at least one field must be required"),
    (lambda d: d["records"]["part"]["fields"].update(id={}), "not 'id'"),
    (lambda d: d["records"]["part"]["fields"]["name"].update(type="number"), "fields.name.type"),
    (lambda d: d["records"]["part"]["fields"]["name"].update(to="part"), "only a ref"),
    (lambda d: d["records"]["finding"]["fields"]["part"].update(to="nothing"), "fields.part.to"),
    (lambda d: d["records"]["finding"]["fields"]["level"].update(choices=["one"]), "at least two"),
    (lambda d: d["records"]["finding"]["fields"]["level"].update(choices=["High", "low"]), "lower case"),
    (lambda d: d["records"].update(orphan={"prefix": "ZZ", "fields": {"text": {"required": True}}}),
     "records.orphan is recorded in no stage"),
])
def test_a_bad_file_is_refused_with_the_place(change, problem):
    with pytest.raises(sch.SchemaError, match=problem):
        sch.parse(changed(change))


def test_a_field_may_refer_to_a_kind_given_later():
    def swap(data):
        data["records"] = dict(reversed(list(data["records"].items())))
    assert list(sch.parse(changed(swap)).kinds) == ["fix", "finding", "part", "scope_item"]


def test_a_folder_without_the_file_or_with_bad_yaml_is_refused(tmp_path):
    with pytest.raises(sch.SchemaError, match="no session.yaml"):
        sch.load(tmp_path)
    (tmp_path / "session.yaml").write_text("stages: [", encoding="utf-8")
    with pytest.raises(sch.SchemaError, match="not valid YAML"):
        sch.load(tmp_path)
    (tmp_path / "session.yaml").write_text("- a list", encoding="utf-8")
    with pytest.raises(sch.SchemaError, match="mapping"):
        sch.load(tmp_path)
