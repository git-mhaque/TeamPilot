"""
JIRA Data Extraction CLI

Usage:
    python -m scripts.main [OPTIONS]

Options:
    --task {all,project,issue,sprint,chart,epics,report}
                        Select a specific task to run (default: all tasks)
    --sprint-out PATH   Output path for sprint dataset CSV (default: sprint_dataset.csv)
    --epics-out PATH    Output path for epics dataset CSV (default: epics_dataset.csv)
    --report-out PATH   Output path for sprint JSON report (default: sprint_report.json)
    --chart-out PATH    Output path for velocity/cycle PNG chart (default: velocity_cycle_time.png)

When --task is omitted or set to "all", the CLI runs the full pipeline in the
following order: project, issue, sprint, chart, epics, report. Specifying a
single task runs only that portion.

Examples:
    python -m scripts.main                       # run entire pipeline
    python -m scripts.main --task epics          # run only the epics dataset
    python -m scripts.main --task sprint --sprint-out my_sprints.csv

Environment variables JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT_KEY, and JIRA_BOARD_ID must be set or provided via a config file.
"""

import logging

import matplotlib.pyplot as plt
from jira import JIRA

from .charting import plot_velocity_cycle_time as _plot_velocity_cycle_time
from .config import get_jira_credentials, load_runtime_config
from .epic_service import get_epics_dataset as _build_epics_dataset
from .io_utils import write_dataset_to_csv, write_dataset_to_json
from .jira_client import (
    JiraService,
    connect_jira as _connect_jira_service,
    fetch_closed_sprints,
    fetch_issue,
    fetch_project,
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


def get_project(jira, project_key):
    service = _ensure_service(jira)
    return fetch_project(service, project_key)


def get_issue(jira, issue_key):
    service = _ensure_service(jira)
    return fetch_issue(service, issue_key)


def get_project_data(project):
    return _get_project_payload(project)


def get_issue_data(issue, sp_field_id=None):
    if sp_field_id is None:
        from .config import load_runtime_config

        sp_field_id = load_runtime_config().story_points_field
    return _get_issue_payload(issue, sp_field_id)


def get_sprint_data(sprint):
    return _get_sprint_data(sprint)


def get_all_closed_sprints(jira, board_id):
    service = _ensure_service(jira)
    return fetch_closed_sprints(service, board_id)


def get_sprint_dataset(sprints, jira, story_points_field="customfield_10004"):
    service = _ensure_service(jira)
    return _build_sprint_dataset(service, sprints, story_points_field)


def get_epics_dataset(jira_client, epic_keys):
    service = _ensure_service(jira_client)
    return _build_epics_dataset(service, epic_keys)


def get_sprint_insights_with_creep(jira_client, board_id, sp_field_id):
    service = _ensure_service(jira_client)
    return _build_sprint_insights(service, board_id, sp_field_id)


def plot_velocity_cycle_time(data_filename="sprint_dataset.csv", output_filename="velocity_cycle_time.png"):
    return _plot_velocity_cycle_time(
        data_filename=data_filename,
        output_filename=output_filename,
        plt_module=plt,
    )


import argparse

TASK_CHOICES = ("all", "project", "issue", "sprint", "chart", "epics", "report")


def run_cli(
    task: str = "all",
    sprint_out: str = "sprint_dataset.csv",
    epics_out: str = "epics_dataset.csv",
    report_out: str = "sprint_report.json",
    chart_out: str = "velocity_cycle_time.png",
):
    logging.basicConfig(level=logging.WARN)
    logging.info("Starting JIRA Data Extraction...")

    runtime_config = load_runtime_config()
    jira_url, jira_pat = get_jira_credentials()
    jira_client = connect_jira(jira_url, jira_pat)
    jira_service = _ensure_service(jira_client)

    selected_tasks = [task]
    if task == "all":
        selected_tasks = ["project", "issue", "sprint", "chart", "epics", "report"]

    def run_project():
        project = get_project(jira_service, runtime_config.project_key)
        project_data = get_project_data(project)
        print("Project Data:", project_data)

    def run_issue():
        issue = get_issue(jira_service, runtime_config.sample_issue_key)
        issue_data = get_issue_data(issue, runtime_config.story_points_field)
        print("Issue Data:", issue_data)
        cycle_time = compute_cycle_time(issue)
        print(f"Cycle time (days): {cycle_time}")

    def run_sprint():
        sprints = get_all_closed_sprints(jira_service, runtime_config.board_id)
        print(f"Total closed sprints: {len(sprints)}")
        sprint_data = get_sprint_dataset(sprints[:10], jira_service, runtime_config.story_points_field)
        print("Sprint Dataset:", sprint_data)
        write_dataset_to_csv(sprint_data, filename=sprint_out)

    def run_chart():
        plot_velocity_cycle_time(
            data_filename=sprint_out,
            output_filename=chart_out,
        )

    # Epics keys could be another CLI arg in future; for now, keep static:
    epics = [
        "CEGBUPOL-4468",
        "CEGBUPOL-4485",
        "CEGBUPOL-4484",
        "CEGBUPOL-4483",
        "CEGBUPOL-4470",
        "CEGBUPOL-4187",
        "CEGBUPOL-3635",
        "CEGBUPOL-4487",
        "CEGBUPOL-3553",
        "CEGBUPOL-4486",
    ]

    def run_epics():
        epic_data = get_epics_dataset(jira_service, epics)
        print("Epics Dataset:", epic_data)
        write_dataset_to_csv(epic_data, filename=epics_out)

    def run_report():
        sprint_dataset = get_sprint_insights_with_creep(
            jira_service, runtime_config.board_id, runtime_config.story_points_field
        )
        write_dataset_to_json(sprint_dataset, filename=report_out)
        print(sprint_dataset)

    task_map = {
        "project": run_project,
        "issue": run_issue,
        "sprint": run_sprint,
        "chart": run_chart,
        "epics": run_epics,
        "report": run_report,
    }

    for name in selected_tasks:
        task_runner = task_map.get(name)
        if task_runner is None:
            raise ValueError(f"Unknown task '{name}'. Expected one of {', '.join(TASK_CHOICES)}")
        task_runner()


def main():
    parser = argparse.ArgumentParser(description="JIRA Data Extraction CLI")
    parser.add_argument(
        "--task",
        choices=TASK_CHOICES,
        default="all",
        help="Select a specific task to run (default: all tasks)",
    )
    parser.add_argument("--sprint-out", type=str, default="sprint_dataset.csv", help="Sprint dataset output file")
    parser.add_argument("--epics-out", type=str, default="epics_dataset.csv", help="Epics dataset output file")
    parser.add_argument("--report-out", type=str, default="sprint_report.json", help="Sprint JSON report output file")
    parser.add_argument("--chart-out", type=str, default="velocity_cycle_time.png", help="Velocity/cycle chart output file")
    args = parser.parse_args()

    run_cli(
        task=args.task,
        sprint_out=args.sprint_out,
        epics_out=args.epics_out,
        report_out=args.report_out,
        chart_out=args.chart_out,
    )

if __name__ == "__main__":
    main()

