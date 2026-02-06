import os
import sys
import logging
from jira import JIRA
from dotenv import load_dotenv
from datetime import datetime
from dateutil import parser
import csv
import pandas as pd
import matplotlib.pyplot as plt


def get_jira_credentials():
    load_dotenv()
    jira_url = os.getenv("JIRA_BASE_URL")
    jira_pat = os.getenv("JIRA_PAT")
    if not jira_url or not jira_pat:
        logging.error("Please set JIRA_BASE_URL and JIRA_PAT in your environment or .env file.")
        sys.exit(1)
    return jira_url, jira_pat

def connect_jira(jira_url, jira_pat):
    try:
        jira = JIRA(server=jira_url, token_auth=jira_pat)
        return jira
    except Exception as e:
        logging.error(f"Failed to connect to JIRA: {e}")
        sys.exit(2)

def get_project(jira, project_key):
    try:
        project = jira.project(project_key)
        return project
    except Exception as e:
        logging.error(f"Failed to fetch project details: {e}")

def get_issue(jira, issue_key):
    try:
        return jira.issue(issue_key, expand='changelog')
    except Exception as e:
        logging.error(f"Failed to fetch issue '{issue_key}': {e}")
        return None

def get_project_data(project):
    return {
        "key": getattr(project, 'key', None),
        "name": getattr(project, 'name', None),
        "description": getattr(project, 'description', None),
        "lead": getattr(getattr(project, 'lead', None), 'displayName', None),
        "url": getattr(project, 'self', None),
    }

def get_sprint_data(sprint):
    return {
        "id": getattr(sprint, "id", None),
        "name": getattr(sprint, "name", None),
        "state": getattr(sprint, "state", None),
        "startDate": getattr(sprint, "startDate", None),
        "endDate": getattr(sprint, "endDate", None),
        "completeDate": getattr(sprint, "completeDate", None),
        # "goal": getattr(sprint, "goal", None),
    }

def get_issue_data(issue):
    fields = getattr(issue, "fields", None)
    return {
        "key": getattr(issue, "key", None),
        "summary": getattr(fields, "summary", None) if fields else None,
        # "description": getattr(fields, "description", None) if fields else None,
        "status": getattr(getattr(fields, "status", None), "name", None) if fields else None,
        "assignee": getattr(getattr(fields, "assignee", None), "displayName", None) if fields else None,
        "reporter": getattr(getattr(fields, "reporter", None), "displayName", None) if fields else None,
        "created": getattr(fields, "created", None) if fields else None,
        "updated": getattr(fields, "updated", None) if fields else None,
        "resolution": getattr(getattr(fields, "resolution", None), "name", None) if fields else None,
        "story_points": getattr(fields, "customfield_10004", None) if fields else None,  # Adjust field ID if necessary
    }


def write_dataset_to_csv(dataset, filename="dataset.csv"):
    """
    Write a list of dictionaries (dataset) to a CSV file in the working directory.

    Args:
        dataset: List of dictionaries, where each dict represents a row.
        filename: Name of the output CSV file (default 'dataset.csv').

    Behavior:
        - If dataset is empty, creates an empty file with no header.
        - If dataset is non-empty, columns are inferred from keys of the first dict.
    """
    if not dataset:
        with open(filename, "w", newline='') as f:
            pass  # Create empty file
        return

    fieldnames = dataset[0].keys()
    with open(filename, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in dataset:
            writer.writerow(row)

def get_all_closed_sprints(jira, board_id):
    all_sprints = []
    start_at = 0
    max_results = 50  # safe default

    while True:
        batch = jira.sprints(
            board_id,
            state='closed',
            startAt=start_at,
            maxResults=max_results
        )

        if not batch:
            break

        all_sprints.extend(batch)

        if len(batch) < max_results:
            break

        start_at += max_results

    sprints_sorted = sorted(
        [s for s in all_sprints if hasattr(s, "startDate")],
        key=lambda s: s.startDate,
        reverse=True
    )

    return sprints_sorted

def compute_cycle_time(issue):
    logging.info(f"Computing cycle time for issue {getattr(issue, 'key', 'unknown')}...")
    changelog = getattr(issue, "changelog", None)
    history_entries = getattr(changelog, "histories", [])
    logging.info(f"{len(history_entries)} changelog entries.")

    start_date = None
    end_date = None

    # Status names to look for (adjust based on your Jira workflow)
    in_progress_statuses = ["Analysis", "Kickoff", "In Progress"]
    done_statuses = ["Closed", "Release Ready"]

    for history in history_entries:
        for item in history.items:
            if item.field == "status":
               
                # Capture the FIRST time it moved to an active state
                if item.toString in in_progress_statuses and start_date is None:
                    logging.info(f"Status found: {item.toString} at {history.created}")
                    start_date = parser.parse(history.created)
                
                # Capture the LAST time it moved to a Done state
                if item.toString in done_statuses:
                    logging.info(f"Status found: {item.toString} at {history.created}")
                    end_date = parser.parse(history.created)

    if start_date and end_date:
        # If it was moved back from Done, and then Done again, 
        # ensure end_date is actually after start_date
        delta = end_date - start_date
        return max(0, delta.total_seconds() / 86400) # Returns float days

    return None

def get_sprint_dataset(sprints, jira, story_points_field='customfield_10004'):
    results = []

    for sprint in sprints:
        sprint_id = getattr(sprint, "id", None)
        name = getattr(sprint, "name", "N/A")
        start_date = getattr(sprint, "startDate", "N/A")
        end_date = getattr(sprint, "endDate", "N/A")
        complete_date = getattr(sprint, "completeDate", "N/A")

        # Get completed issues in this sprint
        jql = f'sprint = {sprint_id} AND statusCategory = Done'
        issues = jira.search_issues(jql, maxResults=1000, expand='changelog')

        total_story_points = 0.0
        cycle_times = []
        for issue in issues:
            # Story Points
            points = getattr(issue.fields, story_points_field, 0)
            if points is not None:
                try:
                    total_story_points += float(points)
                except Exception as e:
                    import logging
                    logging.warning(f"Could not convert story points '{points}' on issue {getattr(issue, 'key', 'unknown')}: {e}")

            # Use helper to compute cycle time in days
            cycle_days = compute_cycle_time(issue)
            if cycle_days is not None and cycle_days >= 0:  # sanity check
                cycle_times.append(cycle_days)

        avg_cycle_time = sum(cycle_times) / len(cycle_times) if cycle_times else None

        results.append({
            "Name": name,
            "StartDate": start_date,
            "EndDate": end_date,
            "CompletedDate": complete_date,
            "CompletedStoryPoints": total_story_points,
            "AverageCycleTime": avg_cycle_time if avg_cycle_time is not None else "N/A",
        })
    return results

def plot_velocity_cycle_time(data_filename="sprint_dataset.csv", output_filename="velocity_cycle_time.png"):
 
    df = pd.read_csv(data_filename)
    sprints = df['Name']
    velocity = df['CompletedStoryPoints']
    cycle_time = df['AverageCycleTime']
    
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()
    
    bars = ax1.bar(sprints, velocity, width=0.4, color='#1f77b4', label='Velocity (Story Points)')
    ax1.set_ylabel('Velocity (Story Points)', color='#1f77b4')
    ax1.set_xlabel('Sprint')
    ax1.set_ylim(0, max(velocity)*1.15)
    
    line = ax2.plot(sprints, cycle_time, color='#d62728', marker='o', linewidth=3, label='Avg Cycle Time (days)')
    ax2.set_ylabel('Avg Cycle Time (days)', color='#d62728')
    ax2.set_ylim(0, max(cycle_time)*1.25)
    
    ax1.set_title('Sprint Velocity & Cycle Time')
    fig.tight_layout()
    fig.legend(loc='upper right', bbox_to_anchor=(1, 1), bbox_transform=ax1.transAxes)
    plt.savefig(output_filename)


def main():
    logging.basicConfig(level=logging.WARN)
    logging.info("Starting JIRA Data Extraction...")

    board_id = 27193 # TODO: Make this configurable 
    story_points_field = 'customfield_10004' # TODO: Make this configurable 

    jira_url, jira_pat = get_jira_credentials()
    jira = connect_jira(jira_url, jira_pat)
    
    # project_key = os.getenv("JIRA_PROJECT_KEY")

    # project = get_project(jira, project_key)
    # project_data = get_project_data(project)
    # print("Project Data:", project_data)

    # issue = get_issue(jira, "CEGBUPOL-4524")
    # issue_data= get_issue_data(issue)
    # print("Issue Data:", issue_data)

    # cycle_time = compute_cycle_time(issue);
    # print(f"Cycle time (days): {cycle_time}")

    sprints = get_all_closed_sprints(jira, board_id)
    print(f"Total closed sprints: {len(sprints)}")

    sprint_data = get_sprint_dataset(sprints[:6], jira, story_points_field)
    print("Sprint Dataset:", sprint_data)

    write_dataset_to_csv(sprint_data, filename="sprint_dataset.csv")

    plot_velocity_cycle_time(data_filename="sprint_dataset.csv", output_filename="velocity_cycle_time.png")

if __name__ == "__main__":
    main()

