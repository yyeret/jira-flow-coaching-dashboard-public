import os
import sys
from unittest.mock import patch
import requests

# Ensure the parent directory is in the path so we can import jira_export
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from jira_export import parse_issues, requests_retry_get, search_jira


def test_parse_issues_basic():
    # Mock Jira response for two issues
    issues = [
        {
            "key": "TEST-1",
            "fields": {
                "summary": "First Issue",
                "issuetype": {"name": "Story"},
                "created": "2023-01-01T10:00:00.000+0000",
                "updated": "2023-01-05T10:00:00.000+0000",
                "status": {"name": "Done"},
                "labels": ["backend", "frontend"],
                "customfield_10016": 5,  # Story Points
            },
            "changelog": {
                "histories": [
                    {
                        "created": "2023-01-02T10:00:00.000+0000",
                        "items": [
                            {"field": "status", "fromString": "Open", "toString": "In Progress"}
                        ],
                    },
                    {
                        "created": "2023-01-05T10:00:00.000+0000",
                        "items": [
                            {"field": "status", "fromString": "In Progress", "toString": "Done"}
                        ],
                    },
                ]
            },
        }
    ]

    field_names = {"customfield_10016": "Story point estimate"}

    main_rows, meta_rows, sprint_rows, link_rows, flag_rows, parent_rows, all_statuses = (
        parse_issues(issues, field_names)
    )

    assert len(main_rows) == 1
    assert main_rows[0]["Issue Key"] == "TEST-1"
    assert main_rows[0]["Summary"] == "First Issue"

    # Check statuses
    assert "In Progress" in all_statuses
    assert "Done" in all_statuses
    assert "Open" in all_statuses  # Derived from created date

    # Verify transition times
    assert main_rows[0]["Open"] == "2023-01-01T10:00:00.000+0000"
    assert main_rows[0]["In Progress"] == "2023-01-02T10:00:00.000+0000"
    assert main_rows[0]["Done"] == "2023-01-05T10:00:00.000+0000"

    assert len(meta_rows) == 1
    assert meta_rows[0]["Story Points"] == 5
    assert meta_rows[0]["Labels"] == "backend, frontend"


def test_classify_comment():
    from jira_export import classify_comment

    # 1. Jira Ticket ID found
    assert classify_comment("blocked by BEN-1234") == "Tech: Upstream Ticket Block (BEN-1234)"
    assert classify_comment("BEN-1234 is required") == "Tech: Upstream Ticket Block (BEN-1234)"

    # 2. Noise prefix stripping and trimming
    assert classify_comment("Flagged because we need details") == "Product: Missing Specs & AC"
    assert classify_comment('"Flagged as: waiting for PR approval"') == "Tech: PR / Code Review"
    assert classify_comment("  flagged  ") == "Impediment"

    # 3. Product clarification / UX
    assert classify_comment("need design review") == "Product: UX/Design Awaiting"
    assert classify_comment("clarify how this should work") == "Product: Missing Specs & AC"
    assert classify_comment("is there a question?") == "Product: Missing Specs & AC"

    # 4. Environment
    assert classify_comment("vpn down") == "Infra: Downtime / Outage"
    assert classify_comment("need db credentials") == "Infra: Access / Permissions"

    # 5. QA/Testing
    assert classify_comment("needs QA review") == "Tech: QA & Testing"

    # 6. Discussion
    assert classify_comment("let's discuss in the standup") == "Team: Discussion / Alignment"

    # 7. Short dynamic fallback
    assert classify_comment("some short comment") == "Some Short Comment"

    # 8. Long fallback
    assert (
        classify_comment(
            "this is a very long comment that does not contain any of the keywords we look for in our heuristics"
        )
        == "Other: Uncategorized Blocker"
    )


def test_requests_retry_get_success_after_429(requests_mock):
    url = "https://mock-jira.atlassian.net/test-endpoint"
    requests_mock.register_uri(
        "GET",
        url,
        [
            {"status_code": 429, "headers": {"Retry-After": "1"}},
            {"status_code": 200, "text": "success"},
        ],
    )

    with patch("time.sleep") as mock_sleep:
        response = requests_retry_get(url, max_retries=3, backoff_factor=1)
        assert response.status_code == 200
        assert response.text == "success"
        mock_sleep.assert_called_once_with(1)


def test_requests_retry_get_success_after_503(requests_mock):
    url = "https://mock-jira.atlassian.net/test-endpoint"
    requests_mock.register_uri(
        "GET",
        url,
        [
            {"status_code": 503},
            {"status_code": 200, "text": "success"},
        ],
    )

    with patch("time.sleep") as mock_sleep:
        response = requests_retry_get(url, max_retries=3, backoff_factor=2)
        assert response.status_code == 200
        assert response.text == "success"
        mock_sleep.assert_called_once_with(1)  # backoff_factor ** 0 = 1 second


def test_requests_retry_get_timeout_recovery(requests_mock):
    url = "https://mock-jira.atlassian.net/test-endpoint"
    requests_mock.register_uri(
        "GET",
        url,
        [
            {"exc": requests.exceptions.Timeout("Timeout!")},
            {"status_code": 200, "text": "success"},
        ],
    )

    with patch("time.sleep") as mock_sleep:
        response = requests_retry_get(url, max_retries=3, backoff_factor=1)
        assert response.status_code == 200
        assert response.text == "success"
        mock_sleep.assert_called_once()


def test_search_jira_pagination(requests_mock):
    with (
        patch("jira_export.get_auth", return_value=("test@user.com", "token")),
        patch("jira_export.JIRA_BASE_URL", "https://mock-jira.atlassian.net"),
    ):
        url = "https://mock-jira.atlassian.net/rest/api/3/search/jql"

        requests_mock.register_uri(
            "GET",
            url,
            [
                {
                    "json": {
                        "issues": [{"key": "TEST-1"}],
                        "names": {"customfield_10016": "Story Points"},
                        "isLast": False,
                        "nextPageToken": "token-page-2",
                        "total": 2,
                    }
                },
                {"json": {"issues": [{"key": "TEST-2"}], "isLast": True, "total": 2}},
            ],
        )

        issues, field_names = search_jira("project=TEST", max_results=1)
        assert len(issues) == 2
        assert issues[0]["key"] == "TEST-1"
        assert issues[1]["key"] == "TEST-2"
        assert field_names == {"customfield_10016": "Story Points"}


def test_sprint_field_parsing_dict_and_string():
    from jira_export import extract_sprints_from_field

    # 1. Dict variant (customfield_10020 or 10009)
    dict_payload = [
        {
            "id": 4070,
            "name": "Sprint 42",
            "state": "active",
            "startDate": "2026-07-15T00:00:00.000Z",
            "endDate": "2026-07-29T00:00:00.000Z",
        }
    ]
    res1 = extract_sprints_from_field(dict_payload)
    assert len(res1) == 1
    assert res1[0]["Sprint ID"] == "4070"
    assert res1[0]["Sprint Name"] == "Sprint 42"
    assert res1[0]["Sprint State"] == "active"

    # 2. String variant (legacy Atlassian greenhopper string)
    str_payload = "com.atlassian.greenhopper.service.sprint.Sprint@123[id=99,name=Sprint 99,state=CLOSED,startDate=2026-06-01,endDate=2026-06-15]"
    res2 = extract_sprints_from_field(str_payload)
    assert len(res2) == 1
    assert res2[0]["Sprint ID"] == "99"
    assert res2[0]["Sprint Name"] == "Sprint 99"
    assert res2[0]["Sprint State"] == "CLOSED"


def test_parse_issues_with_sprint_customfield_10009():
    issues = [
        {
            "key": "MNG-101",
            "fields": {
                "summary": "Sprint test story",
                "issuetype": {"name": "Story"},
                "created": "2026-07-01T10:00:00.000+0000",
                "updated": "2026-07-10T10:00:00.000+0000",
                "status": {"name": "In Progress"},
                "customfield_10009": [
                    {
                        "id": 100,
                        "name": "Sprint 100",
                        "state": "active",
                        "startDate": "2026-07-01",
                        "endDate": "2026-07-15",
                    }
                ],
            },
            "changelog": {"histories": []},
        }
    ]

    main_rows, meta_rows, sprint_rows, link_rows, flag_rows, parent_rows, all_statuses = (
        parse_issues(issues, {})
    )

    assert len(sprint_rows) == 1
    assert sprint_rows[0]["Issue Key"] == "MNG-101"
    assert sprint_rows[0]["Sprint ID"] == "100"
    assert sprint_rows[0]["Sprint Name"] == "Sprint 100"
    assert sprint_rows[0]["Sprint State"] == "active"
