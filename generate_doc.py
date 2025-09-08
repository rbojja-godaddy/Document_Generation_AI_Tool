#!/usr/bin/env python3
"""
Generates Confluence-ready documentation from repo source files
using Claude via GoCaaS, then creates/updates the Confluence page.
"""

import os
import re
import sys
import glob
import json
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv
from gd_gocaas_python.client import createClient as gocaas
from gd_gocaas_python.generated.models.prompts_post_prompt_body import PromptsPostPromptBody


# === Load environment variables ===
load_dotenv()


# === Formatter Function for Confluence ===
def format_for_confluence(text: str) -> str:
    """
    Formats text for Confluence wiki markup:
    - Bold headings (h2., h3.)
    - Clean up table syntax for Confluence rendering
    """
    # Bold headings
    text = re.sub(r'^(h[23]\.\s*)(.+)$', r'\1*\2*', text, flags=re.MULTILINE)

    def fix_table_row(row):
        cells = [cell.strip() for cell in row.strip('|').split('|')]
        return '|| ' + ' || '.join(cells)

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('||'):  # header row
            lines[i] = fix_table_row(line)
        elif line.startswith('|') and not line.startswith('||'):  # normal row
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            lines[i] = '| ' + ' | '.join(cells)
    return '\n'.join(lines)


# === Main function ===
def main():
    parser = argparse.ArgumentParser(description="Generate Confluence Docs from repo")
    parser.add_argument("path", help="Path pattern to repo files, e.g. '/repo/src/*'")
    parser.add_argument("--title", required=True, help="Confluence page title")
    args = parser.parse_args()

    # === Load config from env ===
    gocaas_env = os.getenv("GOCAAS_ENV", "prod")
    gocaas_jwt = os.getenv("GOCAAS_JWT")
    confluence_base_url = os.getenv("CONFLUENCE_BASE_URL")
    space_key = os.getenv("CONFLUENCE_SPACE_KEY")
    confluence_email = os.getenv("CONFLUENCE_EMAIL")
    confluence_token = os.getenv("CONFLUENCE_API_TOKEN")

    if not all([gocaas_jwt, confluence_base_url, space_key, confluence_email, confluence_token]):
        print("❌ Missing required environment variables. Please check your .env file.")
        sys.exit(1)

    # === Initialize gocaas client ===
    _client = gocaas(env=gocaas_env, jwt=gocaas_jwt)

    # === Step 1: Gather repo files ===
    top_dirs = glob.glob(args.path)
    all_files = []
    for d in top_dirs:
        p = Path(d)
        if p.is_dir():
            all_files.extend(p.rglob('*.*'))

    print(f"📂 Total files found: {len(all_files)}")

    repo_files_content = "\n\n".join(
        f"--- FILE: {f} ---\n{f.read_text(encoding='utf-8')}"
        for f in all_files if f.is_file()
    )

    # === Step 2: Build prompt ===
    prompt = f"""
You are a senior data engineering documentation expert.  
Analyze the provided repository files and produce a Confluence-ready document with:

1. Process Overview – 2–4 paragraphs summarizing purpose, data flow, main logic, and outputs.
2. Detailed Steps – ordered list of processing logic, SQL transformations, Python functions, dependencies, and business rules.
3. Input Tables – Present as a bulleted list in this format: * database.tablename
    - One table per line, starting with "* ".
    - Remove single quotes around input tables.
    - Do not include this string "Database.TableName" in the list.
4. Output Table Schema – from DDL files, table: Column Name | Data Type | Description.
    + Use the DDL description if available, but expand it into a clear explanation including the column's purpose, meaning, and typical values.
    + Do NOT include data lineage information here; data lineage should be described separately in the Data Lineage section.
    + If no description exists, infer a detailed one from context in repo files.
5. Data Lineage – mapping of each output column to source columns/tables and transformations.
6. Dependencies & Scheduling – describe external sources, APIs, libraries, and run triggers.
7. Error Handling & Logging – describe handling of failures and logging.
8. Do NOT include data lineage in Output Table Schema; data lineage goes in its own section.
9. Do not include formatting rules in response_content

Formatting rules:
- Use Confluence heading markup (h2., h3.) for headings.
- Output Table Schema must be a proper Confluence table (||Header|| style).
- Code/SQL in fenced code blocks.
- No AI disclaimers or commentary.
- Use only repo content, no invented functionality.
- Keep terminology consistent with repo and DDL, but expand definitions for clarity.

Inputs:
{repo_files_content}
"""

    # === Step 3: Call Claude via gocaas ===
    body = PromptsPostPromptBody(
        prompts=[{"from": "user", "content": [{"type": "text", "value": prompt}]}],
        provider="anthropic_chat",
        store=False,
        is_private=False,
        provider_options={
            "model": "claude-3-sonnet-20240229-v1:0",
            "max_tokens": 4000
        }
    )

    response = _client.prompts().post_prompt(body)
    response_content = response.data.value["content"].strip()

    # === Step 4: Format for Confluence ===
    wiki_content = format_for_confluence(response_content)

    # === Step 5: Check if page exists ===
    search_url = f"{confluence_base_url}/rest/api/content"
    params = {"title": args.title, "spaceKey": space_key, "expand": "version"}
    r = requests.get(search_url, params=params, auth=(confluence_email, confluence_token))
    r.raise_for_status()
    data = r.json()

    if data["results"]:
        page_id = data["results"][0]["id"]
        current_version = data["results"][0]["version"]["number"]
    else:
        page_id = None
        current_version = 0

    headers = {"Content-Type": "application/json"}

    # === Step 6: Create or update Confluence page ===
    if page_id:
        url = f"{confluence_base_url}/rest/api/content/{page_id}"
        new_version = current_version + 1
        payload = {
            "id": page_id,
            "type": "page",
            "title": args.title,
            "space": {"key": space_key},
            "version": {"number": new_version},
            "body": {"wiki": {"value": wiki_content, "representation": "wiki"}},
        }
        response = requests.put(url, data=json.dumps(payload), headers=headers, auth=(confluence_email, confluence_token))
    else:
        url = f"{confluence_base_url}/rest/api/content/"
        payload = {
            "type": "page",
            "title": args.title,
            "space": {"key": space_key},
            "body": {"wiki": {"value": wiki_content, "representation": "wiki"}},
        }
        response = requests.post(url, data=json.dumps(payload), headers=headers, auth=(confluence_email, confluence_token))

    # === Step 7: Output result ===
    if response.ok:
        page_data = response.json()
        page_id = page_data.get("id")
        page_url = f"{confluence_base_url}/pages/viewpage.action?pageId={page_id}"
        print(f"✅ Confluence page updated/created successfully! URL: {page_url}")
    else:
        print(f"❌ Failed to update/create page: {response.status_code} {response.text}")


if __name__ == "__main__":
    main()
