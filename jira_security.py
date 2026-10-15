"""Credential transport checks shared by the command-line exporters."""

from urllib.parse import urlsplit


def validate_jira_url(value):
    """Reject plaintext transport and credentials embedded in configuration URLs."""
    try:
        url = urlsplit(value)
        valid = (
            url.scheme == "https"
            and bool(url.hostname)
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "JIRA_BASE_URL must use HTTPS and contain no credentials, query, or fragment."
        )
