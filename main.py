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
import json
load_dotenv()

def get_jira_credentials():
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

def get_issue_data(issue, sp_field_id=None):
    if sp_field_id is None:
        sp_field_id = os.getenv("JIRA_STORY_POINTS_FIELD", "customfield_10004")
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
        "story_points": getattr(fields, sp_field_id, None) if fields else None,
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
    
    #df['CompletedDate'] = pd.to_datetime(df['CompletedDate'])
    df = df.sort_values(by='CompletedDate')
    
    sprints = df['Name']
    velocity = df['CompletedStoryPoints']
    cycle_time = df['AverageCycleTime']
    
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()
    
    bars = ax1.bar(sprints, velocity, width=0.4, color='#1f77b4', label='Velocity (Story Points)')
    ax1.set_ylabel('Velocity (Story Points)', color='#1f77b4')
    ax1.set_xlabel('Sprint')
    ax1.tick_params(axis='x', rotation=90)
    ax1.set_ylim(0, max(velocity)*1.15)
    
    line = ax2.plot(sprints, cycle_time, color='#d62728', marker='o', linewidth=3, label='Avg Cycle Time (days)')
    ax2.set_ylabel('Avg Cycle Time (days)', color='#d62728')
    ax2.set_ylim(0, max(cycle_time)*1.25)
    
    ax1.set_title('Sprint Velocity & Cycle Time')
    fig.tight_layout()
    fig.legend(loc='upper right', bbox_to_anchor=(1, 1), bbox_transform=ax1.transAxes)
    plt.savefig(output_filename)


def get_epics_dataset(jira_client, epic_keys):
    base_url = jira_client.client_info() # Gets the Jira base URL
    dataset = []

    for key in epic_keys:
        try:
            # 1. Fetch Epic Details
            epic = jira_client.issue(key)
            
            # 2. Find all issues belonging to this Epic
            # 'parent' works for Jira Cloud; 'cf[10001]' (Epic Link) for older Server/Data Center
            issues_in_epic = jira_client.search_issues(f'parent = "{key}" OR "Epic Link" = "{key}"', maxResults=False)
            
            

            total = len(issues_in_epic)
            stats = {"To Do": 0, "In Progress": 0, "Done": 0}

            # 3. Categorize issues by Status Category, skipping ACXRM project issues
            for issue in issues_in_epic:
                # Skip any issue whose issue key contains 'ACXRM'
                if "ACXRM" in getattr(issue, "key", ""):
                    #print(f"Skipping issue {getattr(issue, 'key', '')} as it belongs to ACXRM project.")
                    total -= 1  # Adjust total count since we're skipping this issue
                    continue
                category = issue.fields.status.statusCategory.name
                if category in stats:
                    stats[category] += 1

            # 4. Calculate Percentages (avoiding division by zero)
            def calc_pct(count):
                return round((count / total) * 100, 2) if total > 0 else 0

            print(f"Epic {key} has {total} issues.")
            
            # 5. Build the data object
            dataset.append({
                "issue_number": epic.key,
                "title": epic.fields.summary,
                "link": f"{base_url}/browse/{epic.key}",
                "total_issues": total,
                "completed": stats["Done"],
                "inprogress": stats["In Progress"],
                "todo": stats["To Do"],
                "percentage_done": calc_pct(stats["Done"]),
                "percentage_inprogress": calc_pct(stats["In Progress"]),
                "percentage_todo": calc_pct(stats["To Do"])
            })

        except Exception as e:
            print(f"Error processing Epic {key}: {e}")
            continue

    return dataset


def get_sprint_insights_with_creep(jira_client, board_id, sp_field_id):
    # 1. Get the active sprint
    sprints = jira_client.sprints(board_id, state='active')
    if not sprints:
        return "No active sprint found."
    
    active_sprint = sprints[0]
    sprint_id = active_sprint.id
    sprint_start_dt = parser.parse(active_sprint.startDate)

    # 2. Fetch issues with CHANGELOG expanded
    jql = f'sprint = {sprint_id}'
    issues = jira_client.search_issues(jql, expand='changelog', maxResults=False)

    # 3. Initialize Expanded Dataset
    dataset = {
        "sprint_info": {
            "name": active_sprint.name,
            "start": active_sprint.startDate,
            "end": getattr(active_sprint, 'endDate', None), # Added end_date
        },
        "metrics": {
            "total_issues": len(issues), 
            "scope_creep_count": 0, 
            "creep_points": 0
        },
        "stages": {"To Do": 0, "In Progress": 0, "Done": 0},
        "points": {"total": 0.0, "completed": 0.0, "remaining": 0.0},
        "issue_collection": [],
        "creep_issues": [] # Separate list for easy "Scope Change" reporting
    }

    for issue in issues:
        # --- Scope Creep Logic ---
        is_creep = False
        added_date = None
        histories = getattr(issue.changelog, 'histories', [])
        for history in histories:
            for item in history.items:
                if item.field.lower() == 'sprint' and str(sprint_id) in str(item.to):
                    added_date = parser.parse(history.created)
                    if added_date > sprint_start_dt:
                        is_creep = True
                    break

        # --- Status & Points Processing ---
        # Map specific status to Category (To Do, In Progress, Done)
        category = issue.fields.status.statusCategory.name
        if category in dataset["stages"]:
            dataset["stages"][category] += 1
        
        # Extract Story Points safely
        points = getattr(issue.fields, sp_field_id, 0) or 0
        dataset["points"]["total"] += points
        
        if category == "Done":
            dataset["points"]["completed"] += points
        else:
            dataset["points"]["remaining"] += points

        # --- Data Collection ---
        issue_data = {
            "key": issue.key,
            "title": issue.fields.summary,
            "assignee": str(issue.fields.assignee) if issue.fields.assignee else "Unassigned",
            "status": issue.fields.status.name,
            "category": category,
            "points": points,
            "is_creep": is_creep
        }
        
        dataset["issue_collection"].append(issue_data)

        if is_creep:
            dataset["metrics"]["scope_creep_count"] += 1
            dataset["metrics"]["creep_points"] += points
            dataset["creep_issues"].append({
                "key": issue.key,
                "added_at": added_date.strftime("%Y-%m-%d %H:%M"),
                "points": points
            })

    return dataset

def write_dataset_to_json(data, filename="sprint_report.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, default=str, ensure_ascii=False)
        
        print(f"Success: Data saved to '{os.path.abspath(filename)}'")
        return True
        
    except Exception as e:
        print(f"Error saving JSON: {e}")
        return False


def main():
    logging.basicConfig(level=logging.WARN)
    logging.info("Starting JIRA Data Extraction...")

    board_id_str = os.getenv("JIRA_BOARD_ID", "27193")
    try:
        board_id = int(board_id_str)
    except ValueError:
        logging.error("JIRA_BOARD_ID must be an integer. Current value: %s", board_id_str)
        sys.exit(1)
    story_points_field = os.getenv("JIRA_STORY_POINTS_FIELD", "customfield_10004")

    jira_url, jira_pat = get_jira_credentials()
    jira = connect_jira(jira_url, jira_pat)
    
    project_key = os.getenv("JIRA_PROJECT_KEY")

    project = get_project(jira, project_key)
    project_data = get_project_data(project)
    print("Project Data:", project_data)

    issue = get_issue(jira, "CEGBUPOL-4524")
    issue_data= get_issue_data(issue, story_points_field)
    print("Issue Data:", issue_data)

    cycle_time = compute_cycle_time(issue);
    print(f"Cycle time (days): {cycle_time}")

    sprints = get_all_closed_sprints(jira, board_id)
    print(f"Total closed sprints: {len(sprints)}")

    sprint_data = get_sprint_dataset(sprints[:10], jira, story_points_field)
    print("Sprint Dataset:", sprint_data)

    write_dataset_to_csv(sprint_data, filename="./data/sprint_dataset.csv")

    plot_velocity_cycle_time(data_filename="./data/sprint_dataset.csv", output_filename="./data/velocity_cycle_time.png")

    epics = [ 
              'CEGBUPOL-4468',
              'CEGBUPOL-4485', 
              'CEGBUPOL-4484', 
              'CEGBUPOL-4483', 
              'CEGBUPOL-4470', 
              'CEGBUPOL-4187', 
              'CEGBUPOL-3635', 
              'CEGBUPOL-4487', 
              'CEGBUPOL-3553', 
              'CEGBUPOL-4486' 
              ]
    data = get_epics_dataset(jira, epics)

    print("Epics Dataset:", data)

    write_dataset_to_csv(data, filename="./data/epics_dataset.csv")

    sprint_dataset = get_sprint_insights_with_creep(jira, board_id, story_points_field)

    write_dataset_to_json(sprint_dataset, filename="./data/sprint_report.json")

    print(sprint_dataset)

if __name__ == "__main__":
    main()

