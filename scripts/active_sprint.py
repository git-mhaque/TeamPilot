import logging

import matplotlib.pyplot as plt
from jira import JIRA

from .charting import plot_velocity_cycle_time as _plot_velocity_cycle_time
from .config import get_jira_credentials, load_runtime_config
from .epic_service import get_epics_dataset as _build_epics_dataset
from .io_utils import write_dataset_to_csv, write_dataset_to_json
from .jira_client import (
    JiraService,
    connect_jira as _connect_jira_service
)
from .sprint_service import (
    compute_cycle_time,
    get_issue_data as _get_issue_payload,
    get_project_data as _get_project_payload,
    get_sprint_data as _get_sprint_data,
    get_sprint_dataset as _build_sprint_dataset,
    get_sprint_insights_with_creep as _build_sprint_insights,
)


def _ensure_service(jira_or_service) -> JiraService:
    if isinstance(jira_or_service, JiraService):
        return jira_or_service
    return JiraService(jira_or_service)


def connect_jira(jira_url, jira_pat):
    """Retain backward compatibility for tests expecting a raw Jira client."""

    return _connect_jira_service(jira_url, jira_pat, jira_cls=JIRA).client


def get_sprint_insights_with_creep(jira_client, board_id, sp_field_id):
    service = _ensure_service(jira_client)
    return _build_sprint_insights(service, board_id, sp_field_id)


def main():
    logging.basicConfig(level=logging.WARN)
    logging.info("Starting Active Sprint Data Extraction...")

    runtime_config = load_runtime_config()
    jira_url, jira_pat = get_jira_credentials()
    jira_client = connect_jira(jira_url, jira_pat)
    jira_service = _ensure_service(jira_client)

    sprint_dataset = get_sprint_insights_with_creep(
        jira_service, runtime_config.board_id, runtime_config.story_points_field
    )

    write_dataset_to_json(sprint_dataset, filename="sprint_report.json")

    print(sprint_dataset)

if __name__ == "__main__":
    main()

