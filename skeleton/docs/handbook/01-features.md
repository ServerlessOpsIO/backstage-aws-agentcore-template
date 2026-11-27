# Features

## The agent

- A Python ${{ values.python_version }} program in `src/agent/` using the Strands Agents SDK.
- A persona in `src/agent/persona.md`: who ${{ values.agent_name }} is, how it speaks, and five rules that
  hold in every conversation. Its name and role were set from the Backstage form.
- Skills in `src/agent/skills/`, in the published Agent Skills format. A skill says what one
  kind of session is about. The project came with one example, `decision-record`.
- A model on Amazon Bedrock, chosen by the `ModelId` deployment parameter. It is set to
  `${{ values.model_id }}` in `cfn-parameters.json`.
- A reasoning effort setting, `ReasoningEffort`, for how much the model reasons before it
  answers. It is set to `${{ values.reasoning_effort }}`; `default` leaves the choice to the model.
- Input checks before the model is called: empty prompts and prompts over `MaxPromptChars`
  (4,000 characters by default) are rejected without spending tokens.
- A generic error reply. Failure details go to the log and never to the caller.
- Conversation memory in AgentCore Memory. Requests that share a session ID continue one
  conversation; its messages and its session record are kept for `MemoryEventExpiryDays`
  (${{ values.memory_expiry_days }} days by default).

## Guided sessions

${{ values.agent_name }} leads people through a session of one of its skills, stage by stage, and gives them
a written document at the end. The participants do the work; the agent asks, explains and
records. See [Guided sessions](10-guided-sessions.md).

- A skill declares its stages, what is recorded in each, and its document in one YAML
  file. The tools the model is offered, the session record and the document are made from
  it. A new kind of session needs no new code.
- The session is kept as a record in the agent's state, not left to the model's memory of
  the conversation. The model changes it only through tools, and code keeps the rules that
  can be counted.
- What the model is told, and which tools it is offered, are rebuilt before every call to it.
- Hints, at most one for each entry in each stage, and facilitator's notes that are posted
  only when the session ends.
- The written document and the notes are laid out by code from the record, as Markdown
  files. The model writes neither.
- In a conversation with several people the agent may stay quiet when they talk among
  themselves.
- The agent can read files from public repositories of one GitHub organisation, once a
  person has named one.
- A command plays a fixed session against the deployed agent and checks the result.

## Hosting

- An Amazon Bedrock AgentCore Runtime, which runs the agent as a Linux arm64 container image
  and costs nothing while idle.
- Callers authenticate with IAM. There is no public, unauthenticated endpoint.
- An IAM execution role scoped to the agent's log groups, model and image repository.

## Delivery

- Unit tests that replace the model with a fake, so they never call AWS.
- GitHub Actions workflows that test the agent, build and push its image, and deploy the stack.
  Every deploying branch gets its own stack and its own runtime.
{%- if values.enable_slack_app %}

## The Slack app

- A Slack app for the agent, named ${{ values.slack_app_name }}. Its definition is `slack/manifest.yaml`.
- A workflow that checks the definition on branches, applies it to Slack when it changes on
  `main`, reapplies it once a day, and creates the app only when started by hand.
- The app's ID, signing secret, client ID, client secret and bot token stored as GitHub
  values.
- **The agent answers in Slack.** A mention in a channel gets the agent's reply in a thread,
  and a direct message gets it in the direct message. See
  [Slack messaging](09-slack-messaging.md).

## The Slack receiving service

- A public address on API Gateway that accepts a request only when Slack's signature proves
  Slack sent it.
- Three Lambda functions in `src/handlers/`: one receives and queues, one asks the agent and
  posts the reply, one cleans up after a message that was not finished.
- Two SQS queues. No database: which threads ${{ values.slack_app_name }} takes part in is read from Slack.
- One Slack thread is one agent session, shared by everyone in the thread. A direct message
  is one continuous session, answered without threads. A thread's earlier messages are given
  to the agent the first time ${{ values.slack_app_name }} answers in it.
- Only full members of the workspace are answered.
- What people write is never logged, and waits in a queue for at most an hour.
- Present only in the stack deployed from `main`, once the Slack app's secrets exist.
{%- endif %}

## Observability

- One structured JSON log record per request, with a correlation ID, outcome, duration and
  token usage. Prompt and reply text are not logged, nor are people's names or documents.
- OpenTelemetry traces through the AWS distribution, delivered to AWS X-Ray. Two settings
  keep what people write out of them.

## Not included

These are left for the project to add when it needs them: {% if values.enable_slack_app %}a chat front end other than Slack{% else %}a chat or API front end{% endif %}, reference
knowledge, gateways, multi-agent orchestration, and dashboards or alerts.
