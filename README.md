# Backstage AWS AgentCore Template

This repository is a Backstage scaffolder template for creating a new AI agent hosted on
[Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html).
It generates a repository, publishes it to GitHub and registers it in the catalog.

## What this template creates

- A Python agent built with the [Strands Agents SDK](https://strandsagents.com/), with a
  system prompt, input checks, structured request logging and unit tests
- An AWS SAM `template.yaml` with an AgentCore Runtime and a least-privilege IAM execution role
- Optionally, an AgentCore Memory so the agent remembers a conversation
- A Dockerfile for the agent's Linux arm64 container image
- GitHub Actions workflows that test the agent, build and push the image to ECR, and deploy
  with AWS SAM
- A project handbook under `docs/`, published through Backstage TechDocs
- Backstage catalog metadata in `catalog-info.yaml`
- Optionally, a Slack front end:
  - a Slack app: an app manifest in the repository, and a workflow that validates it on
    branches, applies it on `main`, reapplies it daily and creates the app when started by hand
  - a receiving service that passes Slack messages to the agent and posts its replies: an API
    Gateway address, three Lambda functions, two SQS queues and two Secrets Manager secrets
- Optionally, Spec Kit initialized for Claude, Copilot or Codex

## Repository layout

- `template.yaml`: the Backstage scaffolder template definition
- `skeleton/`: files copied into the generated project
- `pipeline/`: GitHub Actions workflows and the ECR repository policy used by the generated
  project
- `slack-app/`: the Slack app and the receiving service's code, tests and handbook pages, copied
  over the project only when the Slack front end is selected. The receiving service's resources
  are in `skeleton/template.yaml`, inside `{% if values.enable_slack_app %}`. Its `Pipfile.lock`
  replaces the skeleton's, adding the development packages the Slack code needs. Regenerate
  both lock files together when a dependency changes.

Files under `skeleton/`, `pipeline/` and `slack-app/` are rendered by the scaffolder, so `${{ values.* }}`
and `{% ... %}` are template syntax. GitHub Actions expressions in the workflows are wrapped in
`{% raw %}`.

## Typical use in Backstage

The template asks for:

- component name, description, owning group, domain, system, environment and AWS account
- the agent's instructions, its Bedrock model, the Python version, and whether it remembers
  conversations
- whether to add a Slack front end, and the app's name, description, workspace and hostname.
  Selecting it switches conversation memory on
- whether to initialize Spec Kit, and for which coding agent
- whether to launch a Copilot cloud agent task

It then fetches the catalog entities, copies the skeleton, the pipeline and the Slack files, initializes Spec
Kit, publishes the repository, registers the component and launches the Copilot task.

## Requirements

- Backstage with the Scaffolder plugin, the GitHub publisher, and the `github:speckit:*` and
  `github:copilot:agent:launch` actions
- Catalog entities for domain, system, owner, environment and cloud account
- The organization secrets `AWS_CICD_ACCOUNT_ID` and `AWS_ECR_REPO` available to generated
  repositories
- In the deployment account: access to the chosen Bedrock model, and CloudWatch Transaction
  Search enabled for traces
- For the Slack front end:
  - a Slack workspace where the project's owner can create and install apps. The owner creates
    two credentials by hand after the project is generated; the generated handbook lists the
    steps
  - a Route 53 hosted zone for the hostname in the deployment account, with its ID in the
    Parameter Store parameter `/org/dns/ZoneId`

## Origin

The generated project generalizes [Bill-GN](https://github.com/ServerlessOpsIO/Bill-GN), using
its specifications and its plan for the core agent. The image build follows the container
workflows in `backstage-aws-sam-ecs-template`. The Slack front end comes from
`engineering-agents`, features 006 (Slack app deployment) and 007 (Slack agent messaging).

## Not included

An API front end, reference knowledge, tools, multi-agent orchestration, and Datadog
dashboards or alarms are not generated.
