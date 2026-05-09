#!/usr/bin/env python3
"""
HantaVirus.bet — One-click deployer
Запусти из Терминала:
    cd ~/Documents/Claude/Projects/Site\ hantavirus && python3 deploy.py
"""

import json, base64, os, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# ── TOKENS ────────────────────────────────────────────────────────
GITHUB_TOKEN  = "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"
VERCEL_TOKEN  = "vcp_7mCQgqOcefgxmIz4oGl8kBbL5K17MzKLEaFKEkU1RU5ak6fwsj4dvOKO"
GITHUB_OWNER  = "nxdbzwx6ns-star"
GITHUB_REPO   = "hantavirus.bet"
DOMAIN        = "hantavirus.bet"

ROOT = Path(__file__).parent

# Files to deploy
FILES = [
    "index.html",
    "scraper.py",
    "news.json",
    "netlify.toml",
    ".gitignore",
    ".github/workflows/scrape.yml",
]

# ── HELPERS ───────────────────────────────────────────────────────
def req(url, token, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    r = Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "HantaVirusDeployer/1.0",
        "Accept": "application/vnd.github.v3+json",
    })
    try:
        with urlopen(r, timeout=30) as resp:
            return json.loads(resp.read()), resp.status
    except HTTPError as e:
        return json.loads(e.read() or b"{}"), e.code

def gh(path, method="GET", data=None):
    return req(f"https://api.github.com{path}", GITHUB_TOKEN, method, data)

def vc(path, method="GET", data=None):
    return req(f"https://api.vercel.com{path}", VERCEL_TOKEN, method, data)

def ok(status): return 200 <= status < 300

# ── STEP 1: PUSH TO GITHUB ────────────────────────────────────────
def push_github():
    print("\n── Step 1: Push files to GitHub ─────────────────────")

    for rel in FILES:
        fpath = ROOT / rel
        if not fpath.exists():
            print(f"  ⚠ Skipping (not found): {rel}")
            continue

        content_b64 = base64.b64encode(fpath.read_bytes()).decode()

        # Check if file exists (to get its SHA for update)
        existing, status = gh(f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{rel}")
        sha = existing.get("sha") if ok(status) else None

        payload = {
            "message": f"deploy: update {rel}",
            "content": content_b64,
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha

        _, status = gh(
            f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{rel}",
            method="PUT",
            data=payload,
        )

        if ok(status):
            print(f"  ✓ {rel}")
        else:
            print(f"  ✗ {rel} (status {status})")

    print("  → GitHub done")

# ── STEP 2: CREATE / GET VERCEL PROJECT ───────────────────────────
def get_or_create_vercel_project():
    print("\n── Step 2: Vercel project ────────────────────────────")

    # Check existing projects
    data, status = vc("/v9/projects")
    if ok(status):
        for p in data.get("projects", []):
            if p.get("name") == "hantavirus-bet":
                print(f"  ✓ Project exists: {p['id']}")
                return p["id"]

    # Create new project linked to GitHub
    payload = {
        "name": "hantavirus-bet",
        "framework": None,
        "gitRepository": {
            "type": "github",
            "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        },
        "publicSource": True,
    }
    data, status = vc("/v10/projects", method="POST", data=payload)
    if ok(status):
        pid = data.get("id")
        print(f"  ✓ Project created: {pid}")
        return pid
    else:
        print(f"  ✗ Could not create project: {status} — {json.dumps(data)[:200]}")
        return None

# ── STEP 3: TRIGGER DEPLOYMENT ────────────────────────────────────
def deploy_vercel(project_id):
    print("\n── Step 3: Deploy ────────────────────────────────────")

    # Read files for direct upload
    file_payloads = []
    for rel in FILES:
        fpath = ROOT / rel
        if not fpath.exists():
            continue
        raw = fpath.read_bytes()
        file_payloads.append({
            "file": rel,
            "data": base64.b64encode(raw).decode(),
            "encoding": "base64",
        })

    payload = {
        "name": "hantavirus-bet",
        "projectId": project_id,
        "files": file_payloads,
        "target": "production",
        "gitSource": {
            "type": "github",
            "repoId": f"{GITHUB_OWNER}/{GITHUB_REPO}",
            "ref": "main",
        },
    }

    data, status = vc("/v13/deployments", method="POST", data=payload)
    if ok(status):
        dep_url = data.get("url", "—")
        dep_id  = data.get("id", "—")
        print(f"  ✓ Deployment created: https://{dep_url}")
        print(f"  ID: {dep_id}")
        return dep_url
    else:
        # Try simpler deployment without gitSource
        payload.pop("gitSource", None)
        data, status = vc("/v13/deployments", method="POST", data=payload)
        if ok(status):
            dep_url = data.get("url", "—")
            print(f"  ✓ Deployment created: https://{dep_url}")
            return dep_url
        else:
            print(f"  ✗ Deployment failed: {status}")
            print(f"     {json.dumps(data)[:300]}")
            return None

# ── STEP 4: ADD DOMAIN ────────────────────────────────────────────
def add_domain(project_id):
    print("\n── Step 4: Add domain ────────────────────────────────")

    data, status = vc(
        f"/v10/projects/{project_id}/domains",
        method="POST",
        data={"name": DOMAIN},
    )
    if ok(status):
        print(f"  ✓ Domain added: {DOMAIN}")
    elif status == 409:
        print(f"  ✓ Domain already configured")
    else:
        print(f"  ⚠ Domain: {status} — {json.dumps(data)[:200]}")

    # Get DNS instructions
    data, status = vc(f"/v9/projects/{project_id}/domains/{DOMAIN}")
    if ok(status):
        verification = data.get("verification", [])
        print("\n  ── DNS records to add in Beget ──────────────────")
        for v in verification:
            print(f"  Type: {v.get('type')}  Name: {v.get('domain')}  Value: {v.get('value')}")
        print()
        print("  A     @    76.76.21.21")
        print("  CNAME www  cname.vercel-dns.com")

# ── MAIN ──────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  HantaVirus.bet — Deployer")
    print("=" * 55)

    push_github()
    pid = get_or_create_vercel_project()
    if not pid:
        print("\n✗ Could not get/create Vercel project. Stopping.")
        sys.exit(1)

    url = deploy_vercel(pid)
    add_domain(pid)

    print("\n" + "=" * 55)
    if url:
        print(f"  ✓ Site live at:  https://{url}")
    print(f"  ✓ Domain target: https://{DOMAIN}")
    print("  → Add A record 76.76.21.21 in Beget DNS")
    print("  → DNS propagation: ~15 minutes")
    print("=" * 55)

if __name__ == "__main__":
    main()
