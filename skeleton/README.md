# ${{ values.system_name }} / ${{ values.component_name }}

${{ values.description }}

A conversational AI agent, ${{ values.agent_name }}, that leads people through a structured session and
gives them a written document at the end. It is built with the
[Strands Agents SDK](https://strandsagents.com/), uses a model on Amazon Bedrock, and is
hosted on
[Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html).
Infrastructure is defined with [AWS SAM](https://aws.amazon.com/serverless/sam/) and deployed by
GitHub Actions.

The project came with everything a session needs except its subject: the session record,
stages, hints, the facilitator's notes, the written document, conversation memory and
delivery. It also came with one example skill, `decision-record`, so that it works from
the first deployment.

The [project handbook](docs/handbook/00-index.md) covers features, configuration, architecture,
CI/CD, observability and common tasks. It is also in the component's **Docs** tab in Backstage.

## New Project Getting Started

This repository was generated from a template. Before the first deployment succeeds, complete
the [deployment prerequisites](docs/handbook/03-configuration.md#deployment-prerequisites):

1. The deployment account has access to the configured model in Amazon Bedrock.
2. CloudWatch Transaction Search is enabled in the deployment account and region (for traces).
3. The `AWS_ECR_REPO` secret is available to this repository.

Then make the agent your own. Your work is the subject and the conversation:

- **Who the agent is**: edit [`src/agent/persona.md`](src/agent/persona.md).
- **What it leads people through**: replace the example skill under
  [`src/agent/skills/`](src/agent/skills/) with your own. A skill is Markdown and one YAML
  file: what a session is about, its stages, what the participants give in each, and the
  questions to ask. [Guided sessions](docs/handbook/10-guided-sessions.md) says how.
- **Checking it**: write a fixed session for your skill in
  [`data/sessions/`](data/sessions/) and play it against the deployed agent.

You should not need to change the code in `src/agent/` to do any of that.

## Run the tests

```bash
pipenv install --dev
pipenv run test-unit
sam validate --lint
```

## Ask the deployed agent

```bash
export AGENT_RUNTIME_ARN=$(aws cloudformation describe-stacks \
  --stack-name ${{ values.component_name | lower }}-main \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text)

uv run --with boto3 scripts/invoke.py "What can you do?"
```

Your AWS credentials need `bedrock-agentcore:InvokeAgentRuntime` on the runtime.
