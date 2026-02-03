import os
from jira import JIRA
from dotenv import load_dotenv

def main():
    # Load environment variables from .env file if it exists
    load_dotenv()

    jira_url = os.getenv("JIRA_BASE_URL")
    jira_pat = os.getenv("JIRA_PAT")

    print(jira_url, jira_pat)

    if not jira_url or not jira_pat:
        print("Please set JIRA_BASE_URL and JIRA_PAT in your environment or .env file.")
        return

    try:
        jira = JIRA(
            server=jira_url,
            token_auth=jira_pat
        )
        print(jira.myself())
    except Exception as e:
        print("Failed to connect to JIRA", e)
        return

    try:
        projects = jira.projects()
        if not projects:
            print("No projects found or insufficient permissions.")
            return

        for project in projects:
            print(f"Found project: {project.key} ({project.name})")
    except Exception as e:
        print("Failed to fetch project list:")

if __name__ == "__main__":
    main()