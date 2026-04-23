# OpenFaaS Python SDK — GitHub Actions Federation Example

This repository shows how to use the [OpenFaaS Python SDK](https://github.com/openfaas/python-sdk) from a GitHub Actions workflow without storing any static credentials. Authentication is handled through [OpenFaaS IAM Web Identity Federation](https://docs.openfaas.com/openfaas-pro/iam/github-actions-federation/): the workflow obtains a short-lived GitHub Actions OIDC id_token, exchanges it for an OpenFaaS access token, and then uses the SDK to interact with the gateway.

> OpenFaaS IAM is an OpenFaaS Pro feature. You will need a Pro or Enterprise license to use it.

## How it works

```
GitHub Actions runner
        │
        │  1. Request OIDC id_token (audience = gateway URL)
        ▼
GitHub OIDC provider  ──────────────►  id_token (JWT signed by GitHub)
        │
        │  2. Exchange id_token for an OpenFaaS access token
        ▼
OpenFaaS gateway /oauth/token
        │  - Validates the JWT signature against GitHub's JWKS
        │  - Checks the JwtIssuer, Policy and Role resources
        │  - Returns a short-lived OpenFaaS access token
        │
        │  3. Use the OpenFaaS access token with the Python SDK
        ▼
OpenFaaS gateway API  ──────────────►  list namespaces, deploy functions, …
```

### Key components

| File | Purpose |
|---|---|
| `github_actions_token_source.py` | `TokenSource` implementation that fetches a GitHub OIDC id_token from the Actions runtime |
| `deploy.py` | Main script — wires up `GitHubActionsTokenSource` → `TokenAuth` → `Client` and interacts with the gateway |
| `.github/workflows/deploy.yml` | Workflow that runs `deploy.py` on every push to `main` |
| `iam/issuer.yaml` | `JwtIssuer` — tells the gateway to trust tokens from GitHub Actions |
| `iam/policy.yaml` | `Policy` — defines the allowed actions (list/deploy functions) |
| `iam/role.yaml` | `Role` — binds the policy to tokens from a specific GitHub org/user |

### Token exchange in detail

The `GitHubActionsTokenSource` class fetches a GitHub OIDC id_token at runtime using two environment variables that GitHub injects into the runner when the job has `id-token: write` permission:

- `ACTIONS_ID_TOKEN_REQUEST_URL` — the URL to call
- `ACTIONS_ID_TOKEN_REQUEST_TOKEN` — a short-lived bearer token to authorise the request

The audience is set to the gateway URL, which must match the `aud` field in the `JwtIssuer` resource.

`TokenAuth` from the SDK wraps the token source and performs the OAuth 2.0 Token Exchange (RFC 8693) against the gateway's `/oauth/token` endpoint. The resulting OpenFaaS access token is cached in memory and automatically refreshed when it expires.

```python
token_source = GitHubActionsTokenSource(audience=GATEWAY)

auth = TokenAuth(
    token_url=f"{GATEWAY}/oauth/token",
    token_source=token_source,
)

with Client(gateway_url=GATEWAY, auth=auth) as client:
    print(client.get_namespaces())
```

No credentials are stored anywhere — the entire auth chain is driven by the ephemeral OIDC token that GitHub issues for each workflow run.

## Pre-requisites

- An OpenFaaS Pro gateway with IAM enabled
- `kubectl` access to the cluster to apply the IAM resources

## Setup

### 1. Apply the IAM resources

Edit the files in `iam/` to match your environment — replace `https://gateway.example.com` with your gateway URL and `your-org` with your GitHub organisation or username — then apply them:

```bash
kubectl apply -f iam/
```

The three resources are:

**`iam/issuer.yaml`** — registers GitHub Actions as a trusted OIDC issuer:

```yaml
apiVersion: iam.openfaas.com/v1
kind: JwtIssuer
metadata:
  name: token.actions.githubusercontent.com
  namespace: openfaas
spec:
  iss: https://token.actions.githubusercontent.com
  aud:
    - https://gateway.example.com
  tokenExpiry: 30m
```

**`iam/policy.yaml`** — grants least-privilege access to the `openfaas-fn` namespace:

```yaml
apiVersion: iam.openfaas.com/v1
kind: Policy
metadata:
  name: github-actions-rw
  namespace: openfaas
spec:
  statement:
    - sid: 1-rw-openfaas-fn
      action:
        - Function:List
        - Function:Get
        - Function:Create
        - Function:Update
        - Function:Delete
        - Namespace:List
        - Secret:List
      effect: Allow
      resource: ["openfaas-fn:*"]
```

**`iam/role.yaml`** — binds the policy to tokens issued for your GitHub org on any branch:

```yaml
apiVersion: iam.openfaas.com/v1
kind: Role
metadata:
  name: github-actions-deployer
  namespace: openfaas
spec:
  policy:
    - github-actions-rw
  condition:
    StringEqual:
      jwt:iss: ["https://token.actions.githubusercontent.com"]
      jwt:repository_owner: ["your-org"]
    StringLike:
      jwt:ref: ["refs/heads/*"]
```

The `condition` block restricts which workflows can assume this role. You can tighten this further using any claim in the GitHub Actions id_token — for example, restricting to a specific repository (`jwt:repository`) or requiring the `main` branch only (`jwt:ref: ["refs/heads/main"]`).

### 2. Set the gateway URL

Add `OPENFAAS_URL` as a repository variable in **Settings > Secrets and variables > Actions > Variables**:

```
OPENFAAS_URL = https://gateway.example.com
```

### 3. Push to trigger the workflow

```bash
git push origin main
```

The workflow will:

1. Check out the code
2. Install the OpenFaaS Python SDK and `requests`
3. Run `deploy.py`, which fetches a GitHub OIDC token, exchanges it for an OpenFaaS access token, and uses the SDK to list namespaces, list functions, and deploy a demo function

## Restricting access further

The Role's `condition` block supports any claim present in the GitHub Actions id_token. Some useful examples:

```yaml
# Only allow the main branch
StringEqual:
  jwt:ref: ["refs/heads/main"]

# Only allow a specific repository
StringEqual:
  jwt:repository: ["your-org/your-repo"]

# Only allow a specific workflow file
StringEqual:
  jwt:job_workflow_ref: ["your-org/your-repo/.github/workflows/deploy.yml@refs/heads/main"]
```

## Repository structure

```
.
├── .github/
│   └── workflows/
│       └── deploy.yml               # GitHub Actions workflow
├── iam/
│   ├── issuer.yaml                  # JwtIssuer — trust GitHub Actions OIDC
│   ├── policy.yaml                  # Policy — allowed gateway actions
│   └── role.yaml                    # Role — bind policy to GitHub org/branch
├── deploy.py                        # Main script using the OpenFaaS Python SDK
├── github_actions_token_source.py   # TokenSource implementation for GitHub Actions
└── requirements.txt
```

## See also

- [OpenFaaS Python SDK](https://github.com/openfaas/python-sdk)
- [OpenFaaS IAM — GitHub Actions Federation](https://docs.openfaas.com/openfaas-pro/iam/github-actions-federation/)
- [OpenFaaS IAM overview](https://docs.openfaas.com/openfaas-pro/iam/overview/)
