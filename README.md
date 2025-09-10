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

```bash
pip install -r requirements.txt
