# Common tasks

## Validate and deploy changes

```bash
pipenv install --dev
pipenv run test-unit
sam validate --lint
```

Push the branch. The `Branches` workflow tests, builds and deploys a stack for it. Merge to
`main` to deploy the `main` stack.

## Run the agent locally

Needs AWS credentials that can invoke the model.

```bash
cd src/agent
MODEL_ID=${{ values.model_id }} pipenv run python main.py
```

In another terminal:

```bash
curl -s localhost:8080/ping
curl -s -X POST localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "What can you do?"}'
```

## Ask the deployed agent

```bash
export AGENT_RUNTIME_ARN=$(aws cloudformation describe-stacks \
  --stack-name <repository>-<branch slug> \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text)

uv run --with boto3 scripts/invoke.py "What can you do?"
```

To hold a conversation, send every message with the same `--session-id` and a `--speaker`.
Documents in a reply are saved to the current folder.

```bash
SESSION=$(uuidgen)-$(uuidgen)
uv run --with boto3 scripts/invoke.py --session-id $SESSION --speaker "Ana Souza" "Help us decide where to hold the offsite"
```

## Change who the agent is, or what it leads people through

Who the agent is and the rules that always hold are in `src/agent/persona.md`; add a test to
`tests/unit/test_prompt.py` for each rule it must keep. What a session is about is in a
skill under `src/agent/skills/`. How any session is led is in `src/agent/session/guide.md`.
[Guided sessions](10-guided-sessions.md) says how to change each and how to check the change.

## Play a fixed session

```bash
export AGENT_RUNTIME_ARN=<as above>
pipenv run play-session
```

See [Guided sessions](10-guided-sessions.md#playing-a-fixed-session).

## Change the model

Set `ModelId` in `cfn-parameters.json` and deploy. It must be a United States inference
profile ID, which starts with `us.`; global profiles are refused because the organization's
region restriction denies them. The execution role's permission follows the parameter.
Confirm the deployment account has access to the model first.

The rest of the ID is not checked. A mistyped value that still starts with `us.` deploys and
then fails at the first request.

## Change how much the model reasons

Set `ReasoningEffort` in `cfn-parameters.json` and deploy. The values are `default`, `none`,
`low`, `medium`, `high`, `xhigh` and `max`. `default` leaves the choice to the model.
Reasoning is billed as output, so lower levels cost less and answer sooner.

## Give the agent a tool

A tool that records what participants give in a session needs no code: name the kind of
entry in the skill's `session.yaml` and the tool is made from it. See
[Guided sessions](10-guided-sessions.md#the-session-file).

For any other tool, write a function with type hints and a docstring that describes it and
its arguments, and add it to `OWN_TOOLS` in `src/agent/main.py` under the name the model
should call it by. It is offered on every call to the model, in and out of a session. Say
when to use it in the skill or in `src/agent/session/guide.md`. If the tool calls an AWS
service, add a statement to `AgentExecutionRole` in `template.yaml` scoped to the resources
it uses. What a tool is given and what it answers must not be logged.

## Grant a caller access

Give the caller's role `bedrock-agentcore:InvokeAgentRuntime` on the stack's `AgentRuntimeArn`
output.

## Add a dependency

Add it, pinned, to `[packages]` in the `Pipfile`. Use `[dev-packages]` for tools that are not
needed in the image. Then run `pipenv lock` and commit `Pipfile.lock` with the `Pipfile`.

## Continue or separate conversations

Requests that share a `runtimeSessionId` and `actorId` continue one conversation, and with it
one session. Send a new session ID to start a new one. Messages and the session record expire
after `MemoryEventExpiryDays`.
