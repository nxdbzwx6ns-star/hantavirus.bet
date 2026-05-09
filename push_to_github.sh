#!/bin/bash
# ── HantaVirus.bet — One-click GitHub push ──────────────────────
# Запусти этот файл один раз из Терминала:
#   cd ~/Documents/Claude/Projects/Site\ hantavirus && bash push_to_github.sh

set -e

TOKEN="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"
REPO="https://${TOKEN}@github.com/nxdbzwx6ns-star/hantavirus.bet.git"

echo "→ Initializing git..."
git init
git branch -m main

echo "→ Staging files..."
git add index.html scraper.py news.json netlify.toml .gitignore .github/

echo "→ Committing..."
git -c user.email="bot@hantavirus.bet" -c user.name="HantaVirus Bot" \
    commit -m "initial commit: site + scraper + github actions"

echo "→ Pushing to GitHub..."
git remote add origin "$REPO" 2>/dev/null || git remote set-url origin "$REPO"
git push -u origin main --force

echo ""
echo "✓ Done! Repo is live at:"
echo "  https://github.com/nxdbzwx6ns-star/hantavirus.bet"
echo ""
echo "Next step: connect to Vercel (see instructions below)"
