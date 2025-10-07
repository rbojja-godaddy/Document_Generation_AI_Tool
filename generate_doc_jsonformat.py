#!/usr/bin/env python3
"""
Generates structured JSON documentation from repo source files
using Claude via GoCaaS (instead of Confluence wiki markup).

Supports:
- Local folder (recursively scans all files)
- Glob patterns (e.g. /src/*)
- Multiple local files/folders (space separated)
- GitHub URLs (blob/tree) - automatically fetches content
"""

import os
import sys
import glob
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
import requests
from gd_gocaas_python.client import createClient as gocaas
from gd_gocaas_python.generated.models.prompts_post_prompt_body import PromptsPostPromptBody

# === Load environment variables ===
load_dotenv()

# === GitHub helper functions ===
def fetch_github_blob(url: str) -> tuple[str, str] | None:
    """Download file content from a GitHub blob URL and return (path, content)."""
    try:
        parts = url.split("/blob/")
        if len(parts) != 2:
            print(f"⚠️ Unsupported GitHub blob URL: {url}")
            return None
        base, rel_path = parts
        raw_url = base.replace("github.com", "raw.githubusercontent.com") + "/" + rel_path
        resp = requests.get(raw_url)
        if resp.status_code == 200:
            return rel_path, resp.text
        else:
            print(f"⚠️ Failed to fetch {url} (HTTP {resp.status_code})")
            return None
    except Exception as e:
        print(f"⚠️ Error fetching {url}: {e}")
        return None

def fetch_github_tree(url: str) -> list[tuple[str, str]]:
    """Download all files under a GitHub tree URL via GitHub API."""
    try:
        if "/tree/" not in url:
            print(f"⚠️ Unsupported GitHub tree URL: {url}")
            return []
        parts = url.split("/tree/")
        base, rel_dir = parts
        repo_parts = base.split("/")
        if len(repo_parts) < 5:
            print(f"⚠️ Invalid GitHub repo URL: {url}")
            return []
        owner, repo = repo_parts[-2], repo_parts[-1]
        branch, *path_parts = rel_dir.split("/")
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{'/'.join(path_parts)}?ref={branch}"
        resp = requests.get(api_url)
        if resp.status_code != 200:
            print(f"⚠️ Failed to fetch GitHub tree {url} (HTTP {resp.status_code})")
            return []
        files = []
        for item in resp.json():
            if item["type"] == "file":
                raw_url = item["download_url"]
                rel_path = "/".join(path_parts + [item["name"]])
                content = requests.get(raw_url).text
                files.append((rel_path, content))
        return files
    except Exception as e:
        print(f"⚠️ Error fetching GitHub tree {url}: {e}")
        return []

# === File loading ===
def load_files(input_arg: str) -> list[tuple[str, str]]:
    """Return list of (path, content) for input paths, globs, or URLs."""
    results = []

    # GitHub URLs
    if input_arg.startswith("http"):
        if "/blob/" in input_arg:
            f = fetch_github_blob(input_arg)
            if f:
                results.append(f)
        elif "/tree/" in input_arg:
            results.extend(fetch_github_tree(input_arg))
        else:
            print(f"⚠️ Unsupported GitHub URL format: {input_arg}")
        return results

    # Glob patterns
    if "*" in input_arg or "?" in input_arg or "[" in input_arg:
        expanded = glob.glob(input_arg)
        for path in expanded:
            p = Path(path)
            if p.is_file():
                try:
                    results.append((str(p), p.read_text(encoding="utf-8")))
                except Exception as e:
                    print(f"⚠️ Could not read {p}: {e}")
            elif p.is_dir():
                for f in p.rglob("*.*"):
                    try:
                        results.append((str(f), f.read_text(encoding="utf-8")))
                    except Exception as e:
                        print(f"⚠️ Could not read {f}: {e}")
        return results

    # Local folder or file
    p = Path(input_arg)
    if p.is_dir():
        for f in p.rglob("*.*"):
            try:
                results.append((str(f), f.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"⚠️ Could not read {f}: {e}")
    elif p.is_file():
        try:
            results.append((str(p), p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"⚠️ Could not read {p}: {e}")
    else:
        print(f"⚠️ Path not found: {input_arg}")

    return results

# === Main function ===
def main():
    parser = argparse.ArgumentParser(description="Generate JSON Docs from repo")
    parser.add_argument(
        "paths",
        nargs="+",
        help="Path(s) or GitHub URL(s), space separated"
    )
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--out", default="doc_output.json", help="Output JSON file")
    args = parser.parse_args()

    # Load GoCaaS config
    gocaas_env = os.getenv("GOCAAS_ENV", "prod")
    gocaas_jwt = os.getenv("GOCAAS_JWT")
    if not gocaas_jwt:
        print("❌ Missing required environment variable: GOCAAS_JWT")
        sys.exit(1)

    _client = gocaas(env=gocaas_env, jwt=gocaas_jwt)

    # Load all files
    files_with_content = []
    for p in args.paths:
        files_with_content.extend(load_files(p))

    if not files_with_content:
        print("⚠️ No files loaded. Please check your paths/URLs.")
    print(f"📂 Total files loaded: {len(files_with_content)}")

    repo_files_content = "\n\n".join(
        f"--- FILE: {path} ---\n{content}" for path, content in files_with_content
    )

    # Build JSON prompt
    prompt = f"""
You are a senior data engineering documentation expert.
Analyze the provided repository files and output structured JSON documentation.
Include output table details in process overview section.
Provide detail explanation about columnname in description in output_table_schema
Do analysis in pyspark script and provide exact sql mapping logic from pyspark script in data_lineage section
with the following keys:
{{
  "title": "{args.title}",
  "process_overview": "string summary of purpose, data flow, main logic, outputs",
  "detailed_steps": ["step 1", "step 2", "..."],
  "input_tables": ["db.table1", "db.table2", "..."],
  "output_table_schema": [
    {{"column": "col1", "type": "STRING", "description": "meaning"}},
    {{"column": "col2", "type": "DATE", "description": "meaning"}}
  ],
  "data_lineage": {{
    "column1": "mapping explanation",
    "column2": "mapping explanation"
  }},
  "dependencies_and_scheduling": "string description",
  "error_handling_and_logging": "string description",
  "data_validation_and_dex_checks": "string description"
}}
Rules:
- Output ONLY valid JSON, no markdown, no comments, no explanations.
- Use arrays for lists (steps, tables).
- Use objects for table schemas (column/type/description).
- Keep terminology consistent with repo and DDL.
- Expand short descriptions into clear explanations.
- If info missing, leave field as empty string "" or empty list [].
- Do not wrap JSON in code fences.

Inputs:
{repo_files_content}
"""

    # Call Claude via GoCaaS
    body = PromptsPostPromptBody(
        prompts=[{"from": "user", "content": [{"type": "text", "value": prompt}]}],
        provider="anthropic_chat",
        store=False,
        is_private=False,
        provider_options={
            "model": "claude-3-sonnet-20240229-v1:0",
            "max_tokens": 4000,
            "temperature": 0,
            "top_p": 1,
        },
    )

    response = _client.prompts().post_prompt(body)
    response_content = response.data.value["content"].strip()

    # Parse and save JSON
    try:
        doc_json = json.loads(response_content)
    except json.JSONDecodeError as e:
        print("❌ Claude did not return valid JSON:", e)
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc_json, f, indent=2, ensure_ascii=False)

    print(f"✅ Documentation JSON saved to {args.out}")


if __name__ == "__main__":
    main()
