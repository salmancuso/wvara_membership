#!/bin/bash
# =====================================================================
# WVARA Site Rebuild - deploy the TEST site to salmancuso.com (ADDED 2026-11-09)
# Run from your Mac, on the site-rebuild branch:  ./deploy-site.sh
#
# Same steps as deploy.sh, but for the test site only:
# 1. Backs up the TEST database on the server (skipped if there isn't one yet)
# 2. Copies the code up (never touches instance/, wvara.keys or venv)
# 3. Resets file permissions so Apache can read the app
# 4. Reloads Apache so the new code is picked up
#
# The live tool (/tools/wvara) is never touched by this script.
# =====================================================================
set -euo pipefail

SERVER="root@salmancuso.com"
REMOTE_DIR="/var/www/html/salmancuso/tools/wvara-site"
BACKUP_DIR="/root/wvara-site-backups"
LOCAL_DIR="/Users/smancuso/Documents/Personal/Sal/programming/wvara_membership"
STAMP="$(date +%Y%m%d-%H%M%S)"

# The test site only ever deploys from the site-rebuild branch
BRANCH="$(git -C "$LOCAL_DIR" rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "site-rebuild" ]]; then
    echo "STOP: you're on branch '$BRANCH'."
    echo "deploy-site.sh only deploys the TEST site from 'site-rebuild'."
    echo "  Test site?       git switch site-rebuild   then ./deploy-site.sh"
    echo "  Live tool fix?   ./deploy.sh  (from main)"
    echo "Nothing was changed."
    exit 1
fi

echo "=========================================="
echo " Deploying the WVARA TEST site"
echo "   branch: $BRANCH"
echo "     from: $LOCAL_DIR"
echo "       to: $SERVER:$REMOTE_DIR"
echo "=========================================="
read -r -p "Continue? (y/n) " answer
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Cancelled. Nothing was changed."
    exit 0
fi

echo ""
echo "Step 1 of 4: backing up the TEST database on the server..."
ssh "$SERVER" "if [ -f $REMOTE_DIR/instance/wvara_membership.db ]; then \
    mkdir -p $BACKUP_DIR && \
    cp -p $REMOTE_DIR/instance/wvara_membership.db $BACKUP_DIR/wvara_membership-$STAMP.db && \
    ls -la $BACKUP_DIR/wvara_membership-$STAMP.db; \
  else echo '  No test database yet; skipping the backup.'; fi"

echo ""
echo "Step 2 of 4: copying code to the server..."
rsync -av \
    --exclude 'venv' \
    --exclude 'instance/' \
    --exclude 'wvara.keys' \
    --exclude '__pycache__' \
    --exclude '*-2026*' \
    --exclude 'archive/' \
    --exclude '.DS_Store' \
    --exclude '.git' \
    --exclude 'deploy.sh' \
    --exclude 'deploy-site.sh' \
    "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

echo ""
echo "Step 3 of 4: resetting permissions and Step 4 of 4: reloading Apache..."
ssh "$SERVER" "cd $REMOTE_DIR && \
    find . -path ./instance -prune -o -path ./venv -prune -o ! -name wvara.keys -exec chown root:www-data {} + && \
    find . -path ./instance -prune -o -path ./venv -prune -o ! -name wvara.keys -exec chmod u=rwX,g=rX,o= {} + && \
    apache2ctl configtest && systemctl reload apache2"

echo ""
echo "=========================================="
echo " Done! Check https://salmancuso.com/tools/wvara-site"
echo " Test database backup (if any): $BACKUP_DIR/wvara_membership-$STAMP.db"
echo "=========================================="
