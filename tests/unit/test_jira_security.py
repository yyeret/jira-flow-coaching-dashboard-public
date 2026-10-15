import pytest

from jira_security import validate_jira_url


@pytest.mark.parametrize("value", ["https://example.atlassian.net", "https://example.com/jira"])
def test_https_instance_and_context_path_are_allowed(value):
    validate_jira_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.atlassian.net",
        "",
        "https://",
        "https://user:password@example.com",
        "https://example.com?token=private",
        "https://example.com#private",
    ],
)
def test_unsafe_instance_urls_fail_without_echoing_configuration(value):
    with pytest.raises(ValueError) as error:
        validate_jira_url(value)
    assert "private" not in str(error.value)
    assert "password" not in str(error.value)


@pytest.mark.parametrize(
    "module_name,function_name",
    [
        ("jira_export", "get_auth"),
        ("export_epic_parents", "get_auth"),
        ("export_sprint_data", "auth"),
    ],
)
def test_exporters_validate_transport_before_returning_credentials(
    monkeypatch, module_name, function_name
):
    import importlib

    exporter = importlib.import_module(module_name)
    monkeypatch.setattr(exporter, "JIRA_BASE_URL", "http://example.atlassian.net")
    monkeypatch.setattr(exporter, "JIRA_USER", "example@example.com")
    monkeypatch.setattr(exporter, "JIRA_API_TOKEN", "test-token")
    with pytest.raises(ValueError, match="HTTPS"):
        getattr(exporter, function_name)()
