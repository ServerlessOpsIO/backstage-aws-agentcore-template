# Guided sessions

${{ values.agent_name }} leads people through a session of one of its skills, stage by stage, and gives them a
written document at the end. The people do the work. The agent asks, explains and records.

This page says how a session works, how to write a skill of your own, what the code
enforces, and how to check that a change has not broken anything. The project came with
one example skill, `decision-record`, which leads people through a decision. Replace it
with yours.

## What is yours to write, and what came with the project

| | Where | Holds |
| --- | --- | --- |
| The persona | `src/agent/persona.md` | Who the agent is, how it speaks, and five rules that hold in every conversation. No word about how to run a session. **Yours.** |
| A skill | `src/agent/skills/<name>/` | What one kind of session is about: its stages, what the participants give in each, the questions to ask, and what the agent must leave to them. No word about who the agent is. **Yours.** |
| A fixed session | `data/sessions/<name>.yaml` | A made-up conversation that exercises the skill, to play against the deployed agent. **Yours.** |
| The shared guide | `src/agent/session/guide.md` | How any session is led: starting, moving between stages, hints, notes, staying quiet, finishing, reading a repository. Change it when every skill should be led differently. |
| The session engine | `src/agent/session/*.py`, `main.py`, `prompt.py`, `loader.py` | The session record, the tools, the document, and the request loop. A new kind of session needs no change here. |

## What people talking to the agent need to know

- **Starting**: ask for what a skill does, in your own words. There is no command.
- **It will not do the work for you.** Asked for what the participants are there to give,
  it asks a question back. It will explain an idea or how something works.
- **Stages**: a session goes through the skill's stages in order. You can ask where things
  stand, go back, skip a stage, or ask for the document early.
- **The document arrives as a Markdown file**, ready to put in a repository. So do the
  agent's facilitator's notes: what it hinted at that nobody took up, what it saw missed,
  and what it questioned and you kept. The notes come only when the session ends.
- **To finish**, say so. The agent says what it is about to post and posts on the next
  message, unless that message objects. An objection cancels it; ask again when ready.
- **Changes after the end** are allowed, and each is marked in the document with †.
- **A session lasts as long as the conversation's memory**: `MemoryEventExpiryDays` days.
{%- if values.enable_slack_app %}
- **In a channel thread it may stay quiet** when people are talking to each other. A
  mention always gets a reply. In a direct message it always replies.
- **It sees only what full members of the workspace write.**
- **A session in a channel thread must finish within ${{ values.memory_expiry_days }} days of the thread's first
  message.** After that the thread is no longer answered. The agent says the time when the
  session starts, and warns when a day is left.
{%- endif %}
- **It can read a repository** to check what you tell it: a public repository in the
  `GitHubOrg` organisation, and only once someone has named it.

## Writing a skill

A skill is a folder in the published [Agent Skills](https://agentskills.io) format, with
one file added for sessions:

```text
src/agent/skills/decision-record/
├── SKILL.md         # Front matter, and what is particular to this kind of session
├── session.yaml     # The stages, what is recorded in each, and the document
├── SOURCE.md        # Where the skill came from and its licence
└── references/      # One file for each stage. Only the current stage's is given to the model.
    ├── context.md
    ├── options.md
    ├── decision.md
    └── record.md
```

`src/agent/loader.py` reads every skill when the agent starts. The agent does not start
when a skill is malformed, when its `session.yaml` is wrong, when a stage has no reference
file, or when it has no `SOURCE.md` naming a licence. The folder's name must be the skill's
name.

To write your own, copy `decision-record` to a new folder and change each file. Then
delete `decision-record`, its file in `data/sessions/` and its test at the end of
`tests/unit/test_skills.py`. An agent may have several skills; the model chooses between
them from each one's `description`.

### `SKILL.md`

The front matter needs `name` and `description`. The description is what the model reads
to decide whether a request is for this skill, so say what the session does and when to
use it.

The body is given to the model for the whole of a session. Keep it to what is particular
to this kind of session:

- What a session is, and its stages in a sentence.
- **What the participants do, and the agent does not.** Name it exactly: "DO NOT propose an
  option." The persona and the shared guide forbid doing the participants' work in general;
  only the skill can say what that work is.
- What the agent may still explain.
- What kind of example to give, and what kind never to give.

Do not repeat what `src/agent/session/guide.md` already says. Where a skill and the guide
differ, the model is told the skill is right.

### The session file

`session.yaml` is what makes a skill work without code. From it the agent makes the
session record, the tools the model is offered in each stage, what the model is told
about the session, and the written document.

```yaml
subject: decision              # What a session is about, in a word or two
document:
  title: Decision record       # The document is "# Decision record: <what the session is on>"
  filename: decision-record    # The file is decision-record-<what the session is on>.md
  method: >-                   # Optional. Added to the Method section.
    Options were compared by the advantages and drawbacks the participants gave for each.
opening:                       # Optional. Said in the opening of every session.
  - you will not propose options or say which is best
findings_after: context        # Optional. See "Reading a repository".
stages:                        # In order. The last is the one in which the document is given.
  - name: context              # Needs references/context.md
    title: Context             # Used in "the context stage" and in the document
    records: [context]         # The kinds of entry that can be added or changed here
  - name: decision
    title: Decision
    records: [outcome, action]
    fills:                     # Optional. What the stage is meant to fill in.
      action: [owner]
  - name: record
    title: Decision record
records:                       # Each kind is a section of the document, in this order
  option:
    prefix: O                  # Identifiers are O1, O2, ...
    title: Options             # The section's heading
    singular: option           # Optional. Default: the kind's name
    description: Record an option a participant put forward. Never one of your own.
    layout: table              # table (the default) or list
    label: name                # Optional. A text field shown beside the identifier: "O1 (Queue)"
    fields:
      name:
        description: A short name for the option.
        required: true
      description:
        description: What choosing it would mean, as the participant described it.
```

**Stages.** Between 2 and 12. Each has a `references/<name>.md`, which is given to the
model only while that stage is current. A reference file says what the stage aims at, the
questions to ask in order, which tools record what, and what to do before closing the
stage. A stage with no `records` and no `fills`, such as the last, records nothing.

**Kinds of entry.** Each kind becomes two tools, `add_<kind>` and `update_<kind>`, whose
arguments are its fields. The model is offered them only in the stages that list the kind.
`description` is the tool's description: say what a participant must have done for it to
be used. A kind must be listed in at least one stage, and at least one of its fields must
be required. The prefixes `H`, `N`, `Q` and `R` are taken by hints, notes, open questions
and repository findings.

**Fields.** Each has a `description`, which is what the model is told about the argument,
and may have a `title` for the document's column. `required: true` makes `add_<kind>`
refuse without it.

| `type` | Holds | Written as |
| --- | --- | --- |
| `text` (the default) | What a participant said | `name: {required: true}` |
| `choice` | One of a fixed list. The tool refuses anything else. | `choices: [advantage, drawback]` |
| `ref` | The identifier of one entry of another kind. The tool refuses an identifier that does not exist or is of another kind. | `type: ref` and `to: option` |
| `refs` | The identifiers of several entries of another kind | `type: refs` and `to: option` |
| `people` | Names of people in the session. The tool refuses a name of someone who has not written in it. | `type: people` |

**`fills`.** Names fields a stage is meant to fill in on entries that already exist: an
owner for each action, a rating for each finding. The model is shown what is still empty
while the stage is current, and told once when the stage is completed with some left. The
stage is offered `update_<kind>` for those kinds even when it does not list them under
`records`.

**The document.** One section for each kind, in the order given, between a summary and the
open questions. A `table` has a column for each field. A `list` gives each entry's first
text and its other fields in brackets; `group_by` names a `choice` field to group a list
by. The section of a stage that was skipped or never reached says so. The document's
wording and order are fixed by `src/agent/session/render.py`; the model writes none of it.

### `SOURCE.md`

Say where the skill's method comes from, what was read to write it, and its licence. It
must have a line `Licence: ...`. When a skill restates someone else's method, credit it
here.

### Checking a skill before deploying

```bash
pipenv run test-unit
```

`tests/unit/test_skills.py` runs against every skill in `src/agent/skills/`. It fails when
a skill does not load, when a stage has no reference, when `SKILL.md` or a reference names
an `add_` or `update_` tool that the session file does not make, and when a stage's
reference names a tool that is not offered in that stage.

Add tests of your own at the end of that file: one for each rule your skill must keep,
looking for a phrase. If you reword a rule on purpose, change the phrase in the test in
the same commit. If a test fails and you did not mean to change that rule, you have
removed it.

## Changing who the agent is

Edit `src/agent/persona.md`. Its first heading is the agent's name, which is used in the
documents. Its five rules each sit under a fixed heading that `tests/unit/test_prompt.py`
looks for. The persona must not name a stage, a tool or anything about a session; a test
fails if it does.

If your agent should do some of the work itself, the rule "You do not do the
participants' work" is the one to rewrite, with its test, and the same rule under "How to
lead" in `src/agent/session/guide.md`.

## What the model is told, and when

Before every call to the model, `src/agent/prompt.py` builds what it is told, in this
order: the session record, the shared guide, the skill's instructions, the current stage's
reference, the list of skills, and the persona last. The model follows best what comes
last, so the persona's rules are read last and a skill overrides the guide.

With no session in progress the model is given the record ("no session"), the guide, the
list of skills and the persona, and is offered `start_session`.

## How a session is kept: the session record

The framework shows the model only the most recent messages of a conversation, and old
tool calls are left out. A session can be several hundred messages. So a session is not
left to the model's memory. The agent keeps a **session record**: structured data holding
every entry, the stages, the participants and the agent's notes. It is kept in the
agent's state, in AgentCore Memory, with the conversation.

The model changes the record only by calling tools (`src/agent/session/tools.py`). Code in
`src/agent/session/record.py` keeps the rules that can be counted, whatever the model was
told:

| Rule | Kept by |
| --- | --- |
| An entry has the fields its kind requires, and each value fits its type | `add_<kind>` and `update_<kind>` refuse otherwise |
| An entry that another names cannot be removed | `remove_item` refuses |
| One hint for each entry in each stage, and one about no entry | `give_hint` refuses a second |
| Notes only when the session ends | Only a confirmed finish or abandon attaches them |
| A finish, an abandon or a group's skip happens only on a later message | `resolve_change` refuses on the message that asked |
| Who the participants are | Added by code from who wrote each message |
| Repository findings are held until the stage named in `findings_after` is complete | `hold_finding` and `complete_stage` |
| Changes after the notes are marked | Set by code on every later change |
| When silence is allowed | Decided from the request, not by the model |
| What a message leads to is recorded once or not at all | The record is put back before a repeated or unfinished message |

The model is offered only the tools of the current stage.

**What code cannot check** is whether what the model recorded is what a person said, and
whether its own words do the participants' work. That is what the transcript checklist is
for.

**What the session file cannot express** is a rule that works something out, such as a
rating read from a table, a count that must be reached, or a diagram drawn from the
entries. Those need code: a rule in `record.py`, and a section in `render.py`.

### A change to a skill and sessions already in progress

A session's record is read against the skill as it is now. Adding a kind, a field or a
stage is safe. When a stage is renamed or removed, or a kind is removed while a
session holds entries of it, that session's record no longer fits and the agent treats the
conversation as having no session. Its conversation is still there, and the participants
can start again.

## Reading a repository

`src/agent/github.py`. Every limit is in code.

- Only public repositories of the organisation in the `GitHubOrg` setting. No tool takes
  an owner or a web address. With the setting empty, the tools are not offered.
- Only after a person has named the repository: by its name, as `organisation/name`, or by
  a GitHub address in the organisation. A name inside a longer name does not count, nor
  one that appears only in the agent's words or in a file.
- A renamed or moved repository is refused: redirects are not followed.
- A file must be in the list GitHub gave, and is read at the commit the list was taken at.
- At most 30,000 characters of a file, 8 files for one reply and 30 in a session.
- A file's content is handed to the model between markers that say it is content and not
  instruction. It is not kept after the reply that read it.

What the agent finds is kept as a finding and given to the participants as a fact, naming
the file. With `findings_after` set in the session file, findings are held back until that
stage is complete, so that people say what they know before they are told what the
repository shows. Without it they are reported at once.

No credential is used. GitHub allows 60 requests an hour from one network address without
one, and the agent's address belongs to AWS and may be shared. A session costs three
counted requests for each repository. When the limit is reached the agent says it cannot
read and carries on from the conversation.

## Privacy

No message text, reply, person's name, tool argument, file path, file content or document
is written to any log. The agent's log record for a request has `skill`, `stage`,
`toolCalls`, `documents`, and, when a repository was read, its name and a count of files.
See [Observability](06-observability.md) for the two settings that keep the same things
out of traces.

A person's name is cleaned before the model sees it, because a display name is text its
owner chose.

## If a session seems to have been forgotten

A session lives in AgentCore Memory. If memory cannot be read, the agent sees no session
and says none is in progress. Nothing tells this apart from a session that has truly aged
out, or one whose record no longer fits its skill. Look for errors from the memory service
in the agent's log around the time of the message.

## Playing a fixed session

`data/sessions/decision-record.yaml` is a made-up session between two people. It contains
every kind of moment: asking for the work, messages between the participants, a part-way
document, a finish that is objected to, and a change after the notes. Write one for each
skill of your own; the comment at the top of the file describes the format.

```bash
export AGENT_RUNTIME_ARN=<the stack's AgentRuntimeArn output>
pipenv run play-session
```

With more than one file in `data/sessions/`, name one with `--session`. It plays every turn
against the deployed agent{% if values.enable_slack_app %}, without Slack{% endif %}, and prints two lists.

- **Structural checks**: the document's sections and fields, which documents came with
  which reply, and that no reply took over 100 seconds. The command exits 0 only when all
  pass.
- **Behavioural checks**: what a program can still check about the model's judgement, such
  as whether a message between participants got no reply. Reported; they do not change the
  exit code.

The transcript, the checks and the documents are written to `transcripts/<time>/`, which
git ignores. They hold a whole conversation: keep them on your own computer.

Play it three times. A model does not answer the same way twice.

## The transcript checklist

Read `transcripts/<time>/transcript.md` against these items. Each turn's "Look for" line
says what that turn is testing. Add items for what your own skill forbids.

| # | Item | What to look for | A failure looks like |
| --- | --- | --- | --- |
| 1 | The opening was given. | In the first reply: the stages; that participants do the work; that it keeps notes posted at the end. Before any question. | The first reply goes straight to the first question. |
| 2 | Each stage was named when it began. | A sentence such as "Now the options stage" at each change. | Questions for the next stage begin with no word that the stage has changed. |
| 3 | One question at a time. | Each reply ends with at most one question. | Three questions in one reply. |
| 4 | The agent never did the participants' work. | At the turns marked ASKS FOR THE WORK, a question back. Explanations of ideas are fine. | The agent supplies an entry, a rating or a decision. |
| 5 | At most one hint for each entry in a stage, and no hint gave the answer. | A hint points at an area. | Two hints about the same entry in one stage, or a hint that states the point. |
| 6 | Everything in the document was said or decided by a participant. | Take each entry in the document and find the turn where a person said it. Each was read back with its identifier when recorded. | An entry that no turn contains. Words changed so that they say more than the person did. |
| 7 | The notes' contents were not given away before the session ended. | Asked to show its notes, the agent says they come when the session ends. | The agent lists what it thinks was missed while the session is still going. |
| 8 | The agent was silent, and spoke, at the right moments. | No reply to messages between the participants. A reply to a question put to the group and to a disagreement. | A reply to "did you bring the numbers?" Or silence after a question nobody answered. |

Item 4 is the one that matters most: a model that does the work once will do it again.

## Limits

| Limit | Value | Where |
| --- | --- | --- |
| How long a session can be picked up again | `MemoryEventExpiryDays` days | `template.yaml` |
| Messages the model is shown | The last 40 | Strands default |
| Stages in a skill | 2 to 12 | `src/agent/session/schema.py` |
| Kinds of entry in a skill, and fields in a kind | 20, and 12 | `src/agent/session/schema.py` |
| Hints | One for each entry in each stage | `src/agent/session/record.py` |
| Repository files | 30,000 characters each; 8 for a reply; 30 in a session | `src/agent/github.py` |
| Repository paths listed | 2,000 | `src/agent/github.py` |
| A person's name | 80 characters | `src/agent/main.py` |
