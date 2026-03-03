"""
JIRA Data Extraction CLI

Usage:
    python -m scripts.main [OPTIONS]

Options:
    --task {all,project,issue,sprints_dataset,epics,active_sprint}
                        Select a specific task to run (default: all tasks)
    --sprint-out PATH   Output path for sprint dataset CSV (default: sprint_dataset.csv)
    --epics-out PATH    Output path for epics dataset JSON (default: epics_dataset.json)
    --active-sprint-out PATH
                        Output path for active sprint JSON (default: active_sprint.json)
    --chart-out PATH    Output path for velocity/cycle PNG chart (default: velocity_cycle_time.png)

When --task is omitted or set to "all", the CLI runs the full pipeline in the
following order: project, issue, sprints_dataset, epics, active_sprint. Specifying a
single task runs only that portion.

Examples:
    python -m scripts.main                               # run entire pipeline
    python -m scripts.main --task epics                  # run only the epics dataset
    python -m scripts.main --task sprints_dataset --sprint-out my_sprints.csv

Environment variables JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT_KEY, and JIRA_BOARD_ID must be set or provided via a config file.
"""

import logging

import matplotlib.pyplot as plt
from jira import JIRA

from .charting import plot_velocity_cycle_time as _plot_velocity_cycle_time
from .config import get_jira_credentials, load_runtime_config
from .epic_service import get_epics_dataset as _build_epics_dataset
from .io_utils import (
    InitiativeLoadError,
    load_initiatives,
    merge_initiatives_with_epic_metrics,
    write_dataset_to_csv,
    write_dataset_to_json,
)
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

TASK_CHOICES = ("all", "project", "issue", "sprints_dataset", "epics", "active_sprint")


def run_cli(
    task: str = "all",
    sprint_out: str = "sprint_dataset.csv",
    epics_out: str = "epics_dataset.json",
    active_sprint_out: str = "active_sprint.json",
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
        selected_tasks = ["project", "issue", "sprints_dataset", "epics", "active_sprint"]

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

    def run_sprints_dataset():
        sprints = get_all_closed_sprints(jira_service, runtime_config.board_id)
        print(f"Total closed sprints: {len(sprints)}")
        sprint_data = get_sprint_dataset(sprints[:10], jira_service, runtime_config.story_points_field)
        print("Sprint Dataset:", sprint_data)
        write_dataset_to_csv(sprint_data, filename=sprint_out)
        plot_velocity_cycle_time(
            data_filename=sprint_out,
            output_filename=chart_out,
        )

    def run_epics():
        try:
            initiatives = load_initiatives()
        except FileNotFoundError as exc:
            logging.error("Cannot run epics task: %s", exc)
            return
        except InitiativeLoadError as exc:
            logging.error("Cannot run epics task: %s", exc)
            return

        epic_keys: list[str] = []
        for group in initiatives:
            for epic in group.get("epics", []):
                key = epic.get("key")
                if key and key not in epic_keys:
                    epic_keys.append(key)

        epic_data = get_epics_dataset(jira_service, epic_keys)
        print("Epics Dataset:", epic_data)

        enriched_initiatives = merge_initiatives_with_epic_metrics(initiatives, epic_data)
        write_dataset_to_json(enriched_initiatives, filename=epics_out)

    def run_active_sprint():
        sprint_dataset = get_sprint_insights_with_creep(
            jira_service, runtime_config.board_id, runtime_config.story_points_field
        )
        write_dataset_to_json(sprint_dataset, filename=active_sprint_out)
        print(sprint_dataset)

    task_map = {
        "project": run_project,
        "issue": run_issue,
        "sprints_dataset": run_sprints_dataset,
        "epics": run_epics,
        "active_sprint": run_active_sprint,
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
    parser.add_argument(
        "--epics-out",
        type=str,
        default="epics_dataset.json",
        help="Epics dataset JSON output file",
    )
    parser.add_argument(
        "--active-sprint-out",
        type=str,
        default="active_sprint.json",
        help="Active sprint JSON output file",
    )
    parser.add_argument("--chart-out", type=str, default="velocity_cycle_time.png", help="Velocity/cycle chart output file")
    args = parser.parse_args()

    run_cli(
        task=args.task,
        sprint_out=args.sprint_out,
        epics_out=args.epics_out,
        active_sprint_out=args.active_sprint_out,
        chart_out=args.chart_out,
    )

if __name__ == "__main__":
    main()

