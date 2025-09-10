# Document Generation AI Tool

This tool generates Confluence-ready documentation for a repository using **Claude via GoCaaS**. It analyzes source files, extracts data lineage, table schemas then creates or updates the corresponding Confluence page.

## Features

- Generates a full data engineering documentation for repo source files.
- Extracts input tables, output table schemas, data lineage, dependencies, and error handling.
- Fully automated Confluence page creation or update.
- Uses only repo content; does not invent functionality.

---
## Requirements

- Python 3.12+
- Install dependencies from `requirements.txt`:

```
pip install -r requirements.txt
```

## Create a .env file in the project root with the following variables:

```
# GoCaaS (Claude) configuration
GOCAAS_ENV=prod
GOCAAS_JWT=YOUR_GOCAAS_JWT

# Confluence API configuration
CONFLUENCE_BASE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_SPACE_KEY=YOUR_SPACE_KEY
CONFLUENCE_EMAIL=YOUR_EMAIL
CONFLUENCE_API_TOKEN=YOUR_API_TOKEN
```
##Usage

```
python generate_doc.py "/path/to/your/repo/src/*" --title "Your_Confluence_Page_Title
```


