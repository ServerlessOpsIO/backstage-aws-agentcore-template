# Features

## The agent

- A Python ${{ values.python_version }} program in `src/agent/` using the Strands Agents SDK.
- A system prompt in `src/agent/system_prompt.md`, set from the Backstage form.
- A model on Amazon Bedrock, chosen by the `ModelId` deployment parameter. It is set to
  `${{ values.model_id }}` in `cfn-parameters.json`.
- A reasoning effort setting, `ReasoningEffort`, for how much the model reasons before it
  answers. It is set to `${{ values.reasoning_effort }}`; `default` leaves the choice to the model.
- Input checks before the model is called: empty prompts and prompts over `MaxPromptChars`
  (4,000 characters by default) are rejected without spending tokens.
- A generic error reply. Failure details go to the log and never to the caller.
{%- if values.enable_memory %}
- Conversation memory in AgentCore Memory. Requests that share a session ID continue one
  conversation; its messages are kept for `MemoryEventExpiryDays` (${{ values.memory_expiry_days }} days by default).
{%- else %}
- No state between requests. Each request is answered on its own by a new agent instance.
{%- endif %}

## Hosting

- An Amazon Bedrock AgentCore Runtime, which runs the agent as a Linux arm64 container image
  and costs nothing while idle.
- Callers authenticate with IAM. There is no public, unauthenticated endpoint.
- An IAM execution role scoped to the agent's log groups, model and image repository.

## Delivery

- Unit tests that replace the model with a fake, so they never call AWS.
- GitHub Actions workflows that test the agent, build and push its image, and deploy the stack.
  Every deploying branch gets its own stack and its own runtime.

## Observability

- One structured JSON log record per request, with a correlation ID, outcome, duration and
  token usage. Prompt and reply text are not logged.
- OpenTelemetry traces through the AWS distribution, delivered to AWS X-Ray.

## Not included

These are left for the project to add when it needs them: a chat or API front end, reference
knowledge, tools and gateways, multi-agent orchestration, and dashboards or alerts.
