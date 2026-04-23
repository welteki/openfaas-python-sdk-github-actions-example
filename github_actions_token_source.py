"""
GitHub Actions token source for the OpenFaaS Python SDK.

Fetches a GitHub Actions OIDC id_token which can then be exchanged for an
OpenFaaS gateway access token via TokenAuth.

GitHub Actions exposes two environment variables at runtime when a workflow
has ``id-token: write`` permission:

  ACTIONS_ID_TOKEN_REQUEST_URL   — the URL to call to get an id_token
  ACTIONS_ID_TOKEN_REQUEST_TOKEN — a short-lived bearer token to authorise
                                   the request

This module makes that HTTP call and returns the raw JWT, matching exactly the
shell equivalent used in the faas-cli pro plugin:

  OIDC_TOKEN=$(curl -sLS "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=$OPENFAAS_URL" \\
    -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN")
  JWT=$(echo $OIDC_TOKEN | jq -j '.value')
"""

from __future__ import annotations

import os

import requests


class GitHubActionsTokenSource:
    """Fetches a GitHub Actions OIDC id_token to use with OpenFaaS IAM.

    The token is fetched fresh on every call to :meth:`token` — GitHub Actions
    OIDC tokens are short-lived (≈5 minutes) and non-cacheable, so re-fetching
    is the correct behaviour.

    The ``audience`` should be set to the URL of your OpenFaaS gateway, which
    must match the ``aud`` field configured on the ``JwtIssuer`` resource in
    the cluster.

    Args:
        audience: The audience to request in the OIDC token.  Must match the
                  ``aud`` configured on the OpenFaaS ``JwtIssuer`` resource,
                  e.g. ``"https://gateway.example.com"``.

    Raises:
        :exc:`RuntimeError`: If the required GitHub Actions environment
            variables are not present, i.e. the code is not running inside a
            GitHub Actions workflow with ``id-token: write`` permission.

    Example::

        from openfaas import Client, TokenAuth
        from github_actions_token_source import GitHubActionsTokenSource

        GATEWAY = "https://gateway.example.com"

        auth = TokenAuth(
            token_url=f"{GATEWAY}/oauth/token",
            token_source=GitHubActionsTokenSource(audience=GATEWAY),
        )
        with Client(GATEWAY, auth=auth) as client:
            print(client.get_namespaces())
    """

    def __init__(self, audience: str) -> None:
        self._audience = audience

    def token(self) -> str:
        """Fetch and return a fresh GitHub Actions OIDC id_token."""
        request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
        request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")

        if not request_url or not request_token:
            raise RuntimeError(
                "GitHub Actions OIDC environment variables are not set. "
                "Ensure the workflow job has 'id-token: write' permission and "
                "is running inside a GitHub Actions environment."
            )

        url = f"{request_url}&audience={self._audience}"
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {request_token}",
                "User-Agent": "openfaas-python-sdk/github-actions-token-source",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["value"]

    def __repr__(self) -> str:
        return f"GitHubActionsTokenSource(audience={self._audience!r})"
