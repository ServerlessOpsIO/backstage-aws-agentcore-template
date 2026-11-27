# Architecture

## AWS resources

| Resource | Type | Purpose |
| --- | --- | --- |
| `AgentRuntime` | `AWS::BedrockAgentCore::Runtime` | Runs the agent's container image. HTTP protocol, public network mode, IAM authorization. |
| `AgentExecutionRole` | `AWS::IAM::Role` | What the agent may do: write its logs, traces and metrics, pull its image and invoke its model. |
| `AgentMemory` | `AWS::BedrockAgentCore::Memory` | Keeps each conversation's messages and its session record, so the agent can continue a session. |
{%- if values.enable_slack_app %}

The stack deployed from `main` also has the Slack receiving service, once the Slack app's
secrets exist. A branch stack does not.

| Resource | Type | Purpose |
| --- | --- | --- |
| `RestApi` | `AWS::Serverless::Api` | The public address Slack sends events to, defined in `openapi.yaml`. Throttled; access log only. |
| `SiteCertificate` | `AWS::CertificateManager::Certificate` | Certificate for the hostname, validated through the hosted zone. |
| `SlackSigningSecretStore`, `SlackBotTokenStore` | `AWS::SecretsManager::Secret` | The two Slack secrets, filled at deployment from GitHub secrets. Each is readable only by the functions that use it. |
| `ReceiveSlackEventFunction` | `AWS::Serverless::Function` | Checks Slack's signature, answers Slack, queues the message. |
| `SlackMessageQueue` | `AWS::SQS::Queue` (FIFO) | Messages waiting to be answered, one group per Slack thread. |
| `AnswerSlackMessageFunction` | `AWS::Serverless::Function` | Asks the agent and posts the reply in the thread. |
| `SlackHeldBackQueue` | `AWS::SQS::Queue` (FIFO) | Messages the worker did not finish. |
| `CleanUpSlackMessageFunction` | `AWS::Serverless::Function` | Posts the apology if one is owed and removes the eyes reaction. |
| Three log groups | `AWS::Logs::LogGroup` | One per function, kept 30 days. The API's access log is kept 7. |

How a message travels through these is in [Slack messaging](09-slack-messaging.md).
{%- endif %}

The image repository is not in the template. The workflows create it in the CI/CD account as
`<owner>/<repository>` and apply `.github/workflows/ecr-policy.json`, which lets principals in
the AWS organization pull from it.

Sessions end after 5 idle minutes and live for at most 30 (`LifecycleConfiguration`). Raise
both for agents that run long tasks.

## Repository layout

```text
src/agent/            # The code that ships in the image
├── persona.md        # Who the agent is and the rules that always hold. Yours to write.
├── skills/           # One folder for each kind of session. Yours to write.
├── main.py           # Entry point: input checks, one request, logging, errors
├── prompt.py         # Builds what the model is told, before every call to it
├── loader.py         # Reads the skills when the agent starts
├── session/          # The session engine. A new kind of session needs no change here.
│   ├── guide.md      # How any session is led: stages, hints, notes, quiet, finishing
│   ├── schema.py     # Reads a skill's session.yaml
│   ├── record.py     # The session record and the rules code keeps
│   ├── tools.py      # The tools the model calls, some made from session.yaml
│   ├── summary.py    # The record as text for the model
│   └── render.py     # The written document and the facilitator's notes
├── github.py         # Reads files from public repositories of one organisation
└── Dockerfile        # arm64 image, non-root user, port 8080
data/sessions/        # Fixed sessions to play against the deployed agent
{%- if values.enable_slack_app %}
src/handlers/         # The Lambda functions of the Slack receiving service
├── ReceiveSlackEvent/    # function.py and the requirements.txt packaged with it
├── AnswerSlackMessage/
└── CleanUpSlackMessage/
src/common/           # Code the three functions share, packaged with each
data/handlers/        # Sample events and schemas for the functions
openapi.yaml          # The one route of the public address
slack/                # The Slack app's definition
scripts/slack_app/    # The program that applies the definition to Slack
Pipfile               # Dependencies: the agent's in [packages]; test tools and what the
                      # functions import in [dev-packages]
{%- else %}
Pipfile               # Dependencies: runtime in [packages], test tools in [dev-packages]
{%- endif %}
Pipfile.lock          # Exact versions that CI and the image install
.dockerignore         # Limits the Docker build context to the Pipfile and src/agent/
tests/unit/           # Unit tests; never packaged
scripts/invoke.py     # Send a deployed agent one message
scripts/play_session.py  # Play a fixed session against a deployed agent and check it
template.yaml         # Runtime, execution role, memory{% if values.enable_slack_app %}; the Slack receiving service{% endif %}
cfn-parameters.json   # Deployment parameters
cfn-tags.json         # Resource tags
.github/workflows/    # Branch and main workflows, image repository policy
```

## Request flow

1. A caller invokes the runtime with IAM credentials. Callers without
   `bedrock-agentcore:InvokeAgentRuntime` on the runtime are rejected by the service before the
   agent runs.
2. `main.py` reads the request ID and session ID, trims the prompt and applies the empty and
   length checks. A failed check returns an `input_rejection` without calling the model.
3. It builds an agent whose session manager loads the conversation's earlier messages and
   the agent's state, which holds the session record, from AgentCore Memory.
4. Before every call to the model it rebuilds what the model is told (the record, the shared
   guide, the skill, the current stage's guidance, the persona) and which tools it is
   offered, from the record as it stands. A tool call that changes the stage changes both
   for the very next call.
5. When the model has replied, the exchange and the state are saved. Tool calls and their
   results are left out of what is restored later, so a file read from a repository is not
   sent to the model again on every turn.
6. It writes one log record and returns the reply, with any documents the tools attached.
7. Any failure returns HTTP 500 with a generic message. Details go to the log. What the
   message had led the agent to record is undone before the next message is handled.

## Invoke interface

Operation: `InvokeAgentRuntime`, signed with IAM (SigV4), on the stack's `AgentRuntimeArn`
output. `runtimeSessionId` must be 33 to 256 characters.

Request body:

```json
{ "prompt": "What can you do?", "speakerName": "Ana Souza" }
```

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `prompt` | string | yes | Trimmed. Must not be empty. At most `MaxPromptChars` characters. |
| `actorId` | string | no | Separates conversations in memory; `default` when absent. Everyone in one conversation must send the same value, or each gets a conversation of their own. |
| `speakerName` | string | no | Who wrote the message. It is cleaned and given to the model, and the person becomes a participant of the session. `Someone` when absent. |
| `conversationType` | string | no | `direct_message` (the default) or `channel_thread`. Only in a channel thread may the agent stay quiet. |
| `addressed` | boolean | no | Whether the message was put to the agent. `false` allows it to stay quiet during a session in a channel thread. |
| `messageId` | string | no | The same on a second attempt at one message, so that what the message leads to is recorded once. |
| `threadEndsAt` | string | no | For a channel thread: when it stops being answered, as an ISO 8601 time. The agent says it in the opening and warns when a day is left. |

Response body:

```json
{ "kind": "answer", "text": "...", "requestId": "0f6c1a52-...",
  "documents": [{ "filename": "decision-record-queue.md", "title": "Decision record: Queue", "markdown": "..." }] }
```

`documents` is present only when the reply carries some.

| Situation | HTTP | `kind` |
| --- | --- | --- |
| The agent replied | 200 | `answer` |
| The agent judged that the message needed nothing from it | 200 | `no_reply` |
| Empty, missing or over-length prompt | 200 | `input_rejection` |
| The agent could not reply | 500 | `error` |
| Body is not valid JSON | 400 | n/a, returned by the runtime SDK |
| Caller lacks permission | 403 | n/a, `AccessDeniedException` from the service |

The reply is one JSON document, not a stream.
