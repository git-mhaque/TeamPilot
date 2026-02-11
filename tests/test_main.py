import builtins
import io
import json
from types import SimpleNamespace

import pytest

from scripts import main


class DummyJira:
    def __init__(self, batches=None, issues=None, board_sprints=None):
        self._closed = []
        if batches:
            for batch in batches:
                if isinstance(batch, list):
                    self._closed.extend(batch)
                else:
                    self._closed.append(batch)
        self._issues = issues or []
        self._board_sprints = board_sprints or []

    def project(self, key):
        if key == "boom":
            raise RuntimeError("fail")
        return SimpleNamespace(key=key)

    def issue(self, key, expand=None):
        return SimpleNamespace(key=key, fields=SimpleNamespace(summary="issue"))

    def search_issues(self, jql, maxResults=None, expand=None):
        return list(self._issues)

    def sprints(self, board_id, state=None, startAt=0, maxResults=50):
        if state == "active":
            return list(self._board_sprints)
        end = startAt + maxResults
        return self._closed[startAt:end]

    def client_info(self):
        return "http://jira.local"


def test_get_jira_credentials_success(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.com")
    monkeypatch.setenv("JIRA_PAT", "token")
    assert main.get_jira_credentials() == ("https://example.com", "token")


def test_get_jira_credentials_missing(monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_PAT", raising=False)
    with pytest.raises(SystemExit):
        main.get_jira_credentials()


def test_connect_jira_success(monkeypatch):
    created = {}

    class Fake:
        def __init__(self, server, token_auth):
            created["server"] = server
            created["token"] = token_auth

    monkeypatch.setattr(main, "JIRA", Fake)
    result = main.connect_jira("url", "token")
    assert created == {"server": "url", "token": "token"}
    assert isinstance(result, Fake)


def test_connect_jira_failure(monkeypatch, caplog):
    def boom(*_, **__):
        raise RuntimeError("bad")

    monkeypatch.setattr(main, "JIRA", boom)
    with pytest.raises(SystemExit):
        main.connect_jira("url", "token")
    assert "Failed to connect" in caplog.text


def test_get_project_handles_exception(monkeypatch, caplog):
    def fail(*_, **__):
        raise RuntimeError("oops")

    jira = SimpleNamespace(project=fail)
    assert main.get_project(jira, "KEY") is None
    assert "Failed to fetch project" in caplog.text


def test_get_issue_returns_none(monkeypatch, caplog):
    def fail(*_, **__):
        raise RuntimeError("oops")

    jira = SimpleNamespace(issue=fail)
    assert main.get_issue(jira, "KEY") is None
    assert "Failed to fetch issue" in caplog.text


def test_get_project_data_handles_missing_attributes():
    project = SimpleNamespace(key="K", name="Name", description=None, lead=None, self="url")
    assert main.get_project_data(project) == {
        "key": "K",
        "name": "Name",
        "description": None,
        "lead": None,
        "url": "url",
    }


def test_get_issue_data_defaults_field_id():
    fields = SimpleNamespace(
        summary="Summary",
        status=SimpleNamespace(name="Done"),
        assignee=SimpleNamespace(displayName="A"),
        reporter=SimpleNamespace(displayName="R"),
        created="today",
        updated="tomorrow",
        resolution=SimpleNamespace(name="Fixed"),
        customfield_10004=8,
    )
    issue = SimpleNamespace(key="K", fields=fields)
    data = main.get_issue_data(issue)
    assert data["story_points"] == 8
    assert data["summary"] == "Summary"


def test_get_sprint_data_handles_attrs():
    sprint = SimpleNamespace(id=1, name="Sprint", state="closed", startDate="s", endDate="e", completeDate="c")
    assert main.get_sprint_data(sprint) == {
        "id": 1,
        "name": "Sprint",
        "state": "closed",
        "startDate": "s",
        "endDate": "e",
        "completeDate": "c",
    }


def test_write_dataset_to_csv(tmp_path):
    file_path = tmp_path / "out.csv"
    dataset = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    main.write_dataset_to_csv(dataset, filename=file_path)
    content = file_path.read_text().splitlines()
    assert content[0] == "a,b"
    assert "3,4" in content[2]


def test_write_dataset_to_csv_empty(tmp_path):
    file_path = tmp_path / "empty.csv"
    main.write_dataset_to_csv([], filename=file_path)
    assert file_path.exists()
    assert file_path.read_text() == ""


def test_get_all_closed_sprints_batches(monkeypatch):
    sprint1 = SimpleNamespace(startDate="2024-01-02")
    sprint2 = SimpleNamespace(startDate="2024-02-02")
    jira = DummyJira(batches=[[sprint1], [sprint2]])
    result = main.get_all_closed_sprints(jira, board_id=1)
    assert result == [sprint2, sprint1]


def make_history(status_changes):
    items = [SimpleNamespace(field="status", toString=status) for status in status_changes]
    return SimpleNamespace(created="2024-01-0{}T00:00:00Z".format(len(status_changes)), items=items)


def test_compute_cycle_time():
    history = SimpleNamespace(
        created="2024-01-05T00:00:00Z",
        items=[
            SimpleNamespace(field="status", toString="Analysis"),
            SimpleNamespace(field="status", toString="Release Ready"),
        ],
    )
    issue = SimpleNamespace(changelog=SimpleNamespace(histories=[history]), key="K")
    days = main.compute_cycle_time(issue)
    assert days == 0  # same timestamp -> zero days


def build_issue(summary="Issue", status_name="Done", category="Done", points=3, changelog=None):
    status = SimpleNamespace(name=status_name, statusCategory=SimpleNamespace(name=category))
    fields = SimpleNamespace(summary=summary, status=status, customfield_10004=points, assignee=None)
    issue = SimpleNamespace(key=summary, fields=fields, changelog=changelog or SimpleNamespace(histories=[]))
    return issue


def test_get_sprint_dataset(monkeypatch):
    issues = [build_issue(points=5), build_issue(points=2)]
    jira = DummyJira(issues=issues)
    sprint = SimpleNamespace(id=1, name="Sprint", startDate="2024-01-01", endDate="2024-01-15", completeDate="2024-01-16")
    dataset = main.get_sprint_dataset([sprint], jira)
    assert dataset[0]["CompletedStoryPoints"] == 7
    assert dataset[0]["AverageCycleTime"] == "N/A"


def test_plot_velocity_cycle_time(monkeypatch, tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("Name,CompletedDate,CompletedStoryPoints,AverageCycleTime\nS,2024-01-01,5,2\n")

    class FakePlot:
        def __init__(self):
            self.saved = False

        def subplots(self, figsize=None):
            ax = SimpleNamespace(
                bar=lambda *args, **kwargs: None,
                set_ylabel=lambda *args, **kwargs: None,
                set_xlabel=lambda *args, **kwargs: None,
                tick_params=lambda *args, **kwargs: None,
                set_ylim=lambda *args, **kwargs: None,
                set_title=lambda *args, **kwargs: None,
                twinx=lambda: SimpleNamespace(
                    plot=lambda *_, **__: None,
                    set_ylabel=lambda *_, **__: None,
                    set_ylim=lambda *_, **__: None,
                ),
                transAxes="axes",
            )
            fig = SimpleNamespace(tight_layout=lambda: None, legend=lambda *_, **__: None)
            return fig, ax

        def savefig(self, path):
            self.saved = path

    fake = FakePlot()
    monkeypatch.setattr(main, "plt", fake)
    output_path = tmp_path / "plot.png"
    main.plot_velocity_cycle_time(data_filename=csv_path, output_filename=output_path)
    assert fake.saved == output_path


def test_get_epics_dataset(monkeypatch):
    def issue(key):
        return SimpleNamespace(key=key, fields=SimpleNamespace(summary=f"Epic {key}"))

    bugs = [
        build_issue(summary="CEGBUPOL-1", category="Done"),
        build_issue(summary="ACXRM-1", category="Done"),
        build_issue(summary="CEGBUPOL-2", category="In Progress"),
    ]

    jira = DummyJira()
    jira.issue = issue
    jira.search_issues = lambda *args, **kwargs: bugs

    dataset = main.get_epics_dataset(jira, ["EPIC-1"])
    record = dataset[0]
    assert record["total_issues"] == 2  # skipped ACXRM
    assert record["completed"] == 1
    assert record["percentage_inprogress"] == 50.0


def test_get_sprint_insights_with_creep():
    sprint = SimpleNamespace(id=1, name="Sprint", startDate="2024-01-01T00:00:00Z", endDate="2024-01-15T00:00:00Z")
    history = SimpleNamespace(
        created="2024-01-05T00:00:00Z",
        items=[SimpleNamespace(field="sprint", to=str([1]))],
    )
    issue = build_issue(points=3, category="In Progress", changelog=SimpleNamespace(histories=[history]))
    jira = DummyJira(board_sprints=[sprint], issues=[issue])
    dataset = main.get_sprint_insights_with_creep(jira, board_id=1, sp_field_id="customfield_10004")
    assert dataset["metrics"]["scope_creep_count"] == 1
    assert dataset["points"]["total"] == 3


def test_write_dataset_to_json(tmp_path, capsys):
    file_path = tmp_path / "out.json"
    data = {"hello": "world"}
    assert main.write_dataset_to_json(data, filename=file_path)
    captured = json.loads(file_path.read_text())
    assert captured == data


def test_main_happy_path(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.com")
    monkeypatch.setenv("JIRA_PAT", "token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "CEGBUPOL")
    monkeypatch.setenv("JIRA_BOARD_ID", "123")

    fake_jira = DummyJira()
    monkeypatch.setattr(main, "get_jira_credentials", lambda: ("url", "token"))
    monkeypatch.setattr(main, "connect_jira", lambda *args, **kwargs: fake_jira)
    monkeypatch.setattr(main, "get_project", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(main, "get_project_data", lambda project: {"key": "K"})
    fake_issue = build_issue()
    monkeypatch.setattr(main, "get_issue", lambda *args, **kwargs: fake_issue)
    monkeypatch.setattr(main, "get_issue_data", lambda *args, **kwargs: {"key": "K"})
    monkeypatch.setattr(main, "compute_cycle_time", lambda *args, **kwargs: 1)
    monkeypatch.setattr(main, "get_all_closed_sprints", lambda *args, **kwargs: [SimpleNamespace(id=1)])
    monkeypatch.setattr(main, "get_sprint_dataset", lambda *args, **kwargs: [{"Name": "Sprint"}])
    monkeypatch.setattr(main, "write_dataset_to_csv", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "plot_velocity_cycle_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_epics_dataset", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "get_sprint_insights_with_creep", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "write_dataset_to_json", lambda *args, **kwargs: True)

    main.main()
