# Team Dashboard

This Python project demonstrates how to access your team's project data using the JIRA REST API to visualize various team analytics.

## Features
- Listing available projects.

## Quick Start

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
- `JIRA_BASE_URL`: Your JIRA URL. 
- `JIRA_PAT`: Your JIRA Personal Access Token (PAT).
