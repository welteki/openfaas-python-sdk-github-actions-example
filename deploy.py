"""
OpenFaaS gateway interaction script — intended to be called from a GitHub
Actions workflow using federated (OIDC) authentication.

Usage (inside a GitHub Actions step):

    python deploy.py

Required environment variables:
    OPENFAAS_URL   — base URL of the OpenFaaS gateway

The GitHub Actions OIDC environment variables (ACTIONS_ID_TOKEN_REQUEST_URL
and ACTIONS_ID_TOKEN_REQUEST_TOKEN) are injected automatically by the runner
when the job has ``id-token: write`` permission.
"""

from __future__ import annotations

import os
import sys

from openfaas import Client, TokenAuth
from openfaas.models import FunctionDeployment

from github_actions_token_source import GitHubActionsTokenSource

GATEWAY = os.environ.get("OPENFAAS_URL", "").rstrip("/")
NAMESPACE = "openfaas-fn"


def main() -> None:
    if not GATEWAY:
        print("ERROR: OPENFAAS_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    token_source = GitHubActionsTokenSource(audience=GATEWAY)

    auth = TokenAuth(
        token_url=f"{GATEWAY}/oauth/token",
        token_source=token_source,
    )

    with Client(gateway_url=GATEWAY, auth=auth) as client:

        # ------------------------------------------------------------------
        # List namespaces — confirms auth is working
        # ------------------------------------------------------------------
        print("Namespaces:")
        for ns in client.get_namespaces():
            print(f"  {ns}")

        # ------------------------------------------------------------------
        # List functions in the target namespace
        # ------------------------------------------------------------------
        print(f"\nFunctions in '{NAMESPACE}':")
        functions = client.get_functions(NAMESPACE)
        if functions:
            for fn in functions:
                print(f"  {fn.name:30s}  replicas={fn.replicas}  image={fn.image}")
        else:
            print("  (none)")

        # ------------------------------------------------------------------
        # Deploy / update a sample function to demonstrate write access
        # ------------------------------------------------------------------
        fn_name = "gha-python-sdk-demo"
        print(f"\nDeploying '{fn_name}' to '{NAMESPACE}'...")

        spec = FunctionDeployment(
            service=fn_name,
            image="ghcr.io/openfaas/nodeinfo:latest",
            namespace=NAMESPACE,
            labels={"managed-by": "openfaas-python-sdk", "deployed-by": "github-actions"},
            annotations={"source": "https://github.com/welteki/openfaas-python-sdk-github-actions-example"},
        )
        status = client.deploy(spec)
        print(f"  Deploy status: {status}")

        # Confirm it appears in the function list
        fn = client.get_function(fn_name, NAMESPACE)
        print(f"  Function '{fn.name}' is ready — image: {fn.image}")

        # ------------------------------------------------------------------
        # Invoke the env function using a per-function scoped token.
        #
        # The env function has jwt_auth enabled, so a plain gateway token is
        # not sufficient. invoke_function with use_function_auth=True performs
        # a second token exchange — trading the gateway token for a token
        # scoped specifically to openfaas-fn:env — before making the call.
        # ------------------------------------------------------------------
        print("\nInvoking 'env' (function auth)...")
        response = client.invoke_function(
            "env",
            namespace=NAMESPACE,
            use_function_auth=True,
        )
        print(f"  HTTP status : {response.status_code}")
        if response.ok:
            # env prints its environment variables — show first few lines
            for line in response.text.splitlines()[:8]:
                print(f"  {line}")


if __name__ == "__main__":
    main()
