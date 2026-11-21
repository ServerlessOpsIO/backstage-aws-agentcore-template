# Configuration

## Deployment prerequisites

Do these once before the first deployment.

1. **Model access.** The deployment account must have access to the configured model in Amazon
   Bedrock. Some models are not open to every account, and the first use of a provider's models
   in an account may need a one-time step. Check in the Bedrock console's model catalog.
2. **Allowed regions.** The inference profile `${{ values.model_id }}` sends each request to one of
   several United States regions, usually `us-east-1`, `us-east-2` and `us-west-2`. The
   organization's region restrictions must allow Bedrock model invocation in all of them.
3. **Transaction Search.** Enable CloudWatch Transaction Search in the deployment account and
   region. Without it the agent's traces are not delivered. This is an account-level setting,
   so it is not in the template.
4. **Image registry secret.** The `AWS_ECR_REPO` secret must be available to this repository.
   It holds the CI/CD account's registry host, for example
   `123456789012.dkr.ecr.us-east-1.amazonaws.com`.
{%- if values.enable_slack_app %}
5. **The hosted zone.** The Parameter Store parameter `/org/dns/ZoneId` must hold the ID of
   the Route 53 hosted zone that `${{ values.slack_hostname }}` belongs to, in the deployment account.
6. **Slack secrets.** The GitHub secrets `SLACK_SIGNING_SECRET` and `SLACK_BOT_TOKEN` must
   exist before the Slack receiving service is deployed. The Slack app's setup stores both;
   see [The Slack app](08-slack-app.md#first-time-setup). Without them `Main` deploys the
   agent alone.
{%- endif %}

The `AWS_CICD_ACCOUNT_ID` secret is expected from the organization, and `DEPLOYMENT_ACCOUNT_ID`
was set on this repository when it was created.

## Deployment parameters

`cfn-parameters.json` supplies the template's parameters. The deploy action resolves the
`$env.` and `$secrets.` references when it runs.

| Parameter | Value | Purpose |
| --- | --- | --- |
| `Domain`, `System` | Fixed at creation | Organization identity |
| `Component` | Repository name slug | Start of the runtime name |
| `CodeBranch` | Branch slug | Rest of the runtime name |
| `ContainerRepo` | `AWS_ECR_REPO` secret | Registry host of the agent image |
| `ContainerOrg` | Repository owner slug | First part of the image repository name |
| `ContainerImage` | Repository name slug | Second part of the image repository name |
| `ContainerTag` | Commit SHA | Image tag to run |
| `ModelId` | `${{ values.model_id }}` | Bedrock inference profile the agent uses |
| `ReasoningEffort` | `${{ values.reasoning_effort }}` | How much the model reasons before answering |
{%- if values.enable_slack_app %}
| `MaxPromptChars` | `16000` | Longest prompt the agent accepts. Raised from the default so a Slack thread's earlier messages fit. It applies to every caller of the agent. |
| `Hostname` | `${{ values.slack_hostname }}` | Hostname Slack sends events to |
| `DnsZoneId` | `/org/dns/ZoneId` | Name of the Parameter Store parameter holding the hosted zone's ID |
| `SlackSigningSecret` | `SLACK_SIGNING_SECRET` secret | The Slack signing secret. Hidden; kept in Secrets Manager by the stack. |
| `SlackBotToken` | `SLACK_BOT_TOKEN` secret | The Slack bot token. Hidden; kept in Secrets Manager by the stack. |
{%- endif %}

These parameters have defaults in `template.yaml`. Add them to `cfn-parameters.json` to
override one:

| Parameter | Default | Purpose |
| --- | --- | --- |
| `MaxPromptChars` | `4000` | Longest prompt accepted |
| `LogLevel` | `INFO` | Agent log level |
| `MemoryEventExpiryDays` | `${{ values.memory_expiry_days }}` | Days a conversation's messages and its session record are kept, and so how long a session can be picked up again.{% if values.enable_slack_app %} Also how old a Slack thread may be before ${{ values.slack_app_name }} asks for a new one, and so how long a session in a thread has to finish.{% endif %} |
| `GitHubOrg` | `${{ values.github_org }}` | The GitHub organisation whose public repositories the agent may read. It reads no other. Set it to an empty string and the agent reads none. |

Before CloudWatch Transaction Search is turned on, check that the runtime still has the two
settings that keep what people write out of traces. See
[Observability](06-observability.md#what-people-write-is-kept-out-of-traces).

`ModelId` has no default in `template.yaml`, so it must be set in `cfn-parameters.json`. It
must be a United States inference profile ID, which starts with `us.`, such as
`us.openai.gpt-6-luna`. Anything else is refused at deployment: global profiles can route to
regions the organization does not allow. The rest of the ID is not checked, so a mistyped
value deploys and then fails at the first request.

The execution role's model permission follows `ModelId`. The role may call that inference
profile, and may reach a foundation model only through it.

`ReasoningEffort` is one of `default`, `none`, `low`, `medium`, `high`, `xhigh` and `max`.
`default` sends nothing and leaves the choice to the model, which is medium for OpenAI GPT-6 Luna.
Reasoning is billed as output, so a lower level costs less and answers sooner. A level the
configured model does not accept makes requests fail until it is corrected.

## Environment variables

The runtime passes these to the agent: `MODEL_ID`, `REASONING_EFFORT`, `MAX_PROMPT_CHARS`,
`LOG_LEVEL`, `MEMORY_ID`, `GITHUB_ORG` and the two settings that keep content out of traces.
Add more under `EnvironmentVariables` in `template.yaml`.

`MODEL_ID` is required. The agent has no fallback model and does not start without it.
`REASONING_EFFORT` is optional; without it the model uses its own default.

{%- if values.enable_slack_app %}

Do not put secrets in environment variables. Keep them as GitHub secrets, pass them to the
template as `NoEcho` parameters, store them in AWS Secrets Manager from there, and grant
only the role that needs one permission to read it. The Slack secrets below are the example
to follow.

## Slack secrets in AWS

The Slack receiving service reads two secrets when it runs. Both come from GitHub secrets
at deployment; nothing is created by hand in AWS.

| Secret in the stack | From the GitHub secret | Read by | Used for |
| --- | --- | --- | --- |
| `SlackSigningSecretStore` | `SLACK_SIGNING_SECRET` | `ReceiveSlackEvent` | Checking that a request came from Slack |
| `SlackBotTokenStore` | `SLACK_BOT_TOKEN` | `AnswerSlackMessage`, `CleanUpSlackMessage` | Every call to Slack |

To replace one, change the GitHub secret and run **Main** again. See
[Replacing a secret](09-slack-messaging.md#replacing-a-secret).
{%- else %}

Do not put secrets in environment variables or parameters. Store them in AWS Secrets Manager
and grant the execution role permission to read them.
{%- endif %}
{%- if values.enable_slack_app %}

## Slack app values

The `Slack app` workflow uses these repository-level GitHub values. None of them is in
`cfn-parameters.json` except the signing secret and the bot token, which the deployment
passes to the stack as described above. How each is created is in
[The Slack app](08-slack-app.md#first-time-setup).

| Name | Kind | Written by | Read by |
| --- | --- | --- | --- |
| `SLACK_SERVICE_TOKEN` | Secret | You | The `Slack app` workflow |
| `SLACK_GHA_STORE_TOKEN` | Secret | You | The `create` job of the `Slack app` workflow |
| `SLACK_APP_ID` | Variable | The creation run | The `Slack app` workflow |
| `SLACK_SIGNING_SECRET` | Secret | The creation run | The **Main** deployment, for the receiving service |
| `SLACK_CLIENT_ID` | Secret | The creation run | Nothing yet |
| `SLACK_CLIENT_SECRET` | Secret | The creation run | Nothing yet |
| `SLACK_BOT_TOKEN` | Secret | You, after installing the app | The `Slack app` workflow; the **Main** deployment, for the receiving service |

GitHub is the one place these are kept by hand. Only the `Slack app` workflow calls Slack's
app definition service.
{%- endif %}

## Tags

`cfn-tags.json` sets `org:domain`, `org:system` and `org:component` on the stack's resources.
The deploy action adds `org:repo`, `org:branch` and `org:stackName`.
