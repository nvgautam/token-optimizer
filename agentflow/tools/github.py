"""GitHub REST API client. Auth via GITHUB_TOKEN env var only."""

import logging
import os
import re
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_REPO_RE = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
_BASE_URL = "https://api.github.com"


class AuthError(Exception):
    """Raised when GITHUB_TOKEN is absent or empty."""


class GitHubAPIError(Exception):
    """Raised on 4xx/5xx responses."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ReviewComment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"


@dataclass
class CheckResult:
    state: str
    checks: list[dict] = field(default_factory=list)


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise AuthError("GITHUB_TOKEN env var is not set or empty")
    return token


def _validate_repo(repo: str) -> None:
    if not _REPO_RE.match(repo):
        raise ValueError(f"Invalid repo format {repo!r}. Expected 'owner/name'.")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise GitHubAPIError(
            f"GitHub API error: {resp.status_code} {resp.text[:200]}",
            resp.status_code,
        )


def _post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    headers: dict,
    json: dict,
) -> httpx.Response:
    resp = client.post(url, headers=headers, json=json)
    if resp.status_code == 429:
        retry_after = min(int(resp.headers.get("Retry-After", "5")), 60)
        time.sleep(retry_after)
        resp = client.post(url, headers=headers, json=json)
    _raise_for_status(resp)
    return resp


def create_pr(repo: str, branch: str, base: str, title: str, body: str) -> int:
    """Create a PR and return the PR number."""
    _validate_repo(repo)
    token = _token()
    url = f"{_BASE_URL}/repos/{repo}/pulls"
    payload = {"title": title, "body": body, "head": branch, "base": base}
    with httpx.Client() as client:
        resp = _post_with_retry(client, url, headers=_headers(token), json=payload)
    return resp.json()["number"]


def post_review_comments(
    repo: str, pr_number: int, comments: list[ReviewComment]
) -> None:
    """Post all comments as a single PR review (one API call)."""
    _validate_repo(repo)
    token = _token()
    url = f"{_BASE_URL}/repos/{repo}/pulls/{pr_number}/reviews"
    payload = {
        "event": "COMMENT",
        "comments": [
            {"path": c.path, "line": c.line, "body": c.body, "side": c.side}
            for c in comments
        ],
    }
    with httpx.Client() as client:
        _post_with_retry(client, url, headers=_headers(token), json=payload)


def get_check_status(repo: str, pr_number: int) -> CheckResult:
    """Get the combined check status for the PR's head commit."""
    _validate_repo(repo)
    token = _token()
    # Fetch PR to get head sha
    pr_url = f"{_BASE_URL}/repos/{repo}/pulls/{pr_number}"
    checks_url_tpl = f"{_BASE_URL}/repos/{repo}/commits/{{sha}}/check-runs"
    with httpx.Client() as client:
        pr_resp = client.get(pr_url, headers=_headers(token))
        _raise_for_status(pr_resp)
        sha = pr_resp.json()["head"]["sha"]
        checks_resp = client.get(checks_url_tpl.format(sha=sha), headers=_headers(token))
        _raise_for_status(checks_resp)

    data = checks_resp.json()
    check_runs = data.get("check_runs", [])
    conclusions = {r.get("conclusion") for r in check_runs}
    if "failure" in conclusions or "cancelled" in conclusions:
        state = "failure"
    elif None in conclusions or "in_progress" in conclusions:
        state = "pending"
    elif all(c == "success" for c in conclusions):
        state = "success"
    else:
        state = "pending"

    return CheckResult(state=state, checks=check_runs)
