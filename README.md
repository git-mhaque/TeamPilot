# TeamPilot

> TeamPilot: Your AI-Powered Command Center for Team Success.

`TeamPilot` transforms raw Jira data into actionable intelligence. By orchestrating automated workflows through the lens of three expert AI personas — `The Scrum Master`, `The Agile Coach`, and `The Delivery Manager` — it provides the navigation and insights teams need to land their sprints on time, every time.

|Persona |	TeamPilot Role	| Focus Area |
|---|--|---|
| Scrum Master	| The Navigator |	Tactical sprint execution and obstacle removal.| 
| Agile Coach	| The Flight Instructor	| Long-term growth, health metrics, and cultural evolution. | 
| Delivery Manager |	The Mission Director |	Strategic alignment across multiple initiatives and timelines. |
|||


This project orchestrates and automates team workflows and generates insights via Cline workflows. These workflows use Jira as a primary data source and leverage Python to fetch and preprocess relevant data, and then utilize AI to generate insightful artifacts. 


# Quick Start


## Python Setup
1. **Clone/download this project.**

2. **(Recommended) Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3. **Install dependencies:**
    ```
    pip install -r requirements.txt
    ```

4. **Copy the example environment file and update it with your details:** 
    ```
    cp .env.example .env
    ```

    Edit `.env` and set the required environment variables.

5. **Run the example:**
    ```
    python main.py
    ```

## Environment Variables
- `JIRA_BASE_URL`: Your JIRA URL (e.g., https://your-domain.atlassian.net).
- `JIRA_PAT`: Your JIRA Personal Access Token (PAT). Generate at https://id.atlassian.com/manage-profile/security/api-tokens.
- `JIRA_PROJECT_KEY`: Your Jira project key (e.g., CEGBUPOL).
- `JIRA_BOARD_ID`: The ID of your Jira Agile board (integer). 
- `JIRA_STORY_POINTS_FIELD`: The custom field ID for story points (e.g., customfield_10004). 

## Cline Rules 

include `Config.md` in `.clinerules` with following information:
```
# Jira 
- Jira project: <Your Jira Project Key>
- Agile board: <Your Agile Board Name>

# Conflucne 
- Space key: <Default Space Key>
- Create all pages under this parent page: `<Default Parent Page>` (pageId=<PArent Page ID>)
- Overwrite or update if any page with the same name already exists
```

# Running Workflows 

```
\sprint-insights.md 
```

```
\team-insights.md 
```

```
\initiative-insights.md 
```
