#!/bin/bash
# =====================================================================
# WVARA Membership - deploy to salmancuso.com (ADDED 2026-11-05)
# Run from your Mac:  ./deploy.sh
#
# 1. Backs up the LIVE database on the server (timestamped)
# 2. Copies the code up (never touches instance/, wvara.keys or venv)
# 3. Resets file permissions so Apache can read the app
# 4. Reloads Apache so the new code is picked up
# =====================================================================
set -euo pipefail

SERVER="root@salmancuso.com"
REMOTE_DIR="/var/www/html/salmancuso/tools/wvara"
LOCAL_DIR="/Users/smancuso/Documents/Personal/Sal/programming/wvara_membership"
STAMP="$(date +%Y%m%d-%H%M%S)"

# ADDED 2026-11-09: the live tool only ever deploys from the main branch
# (the site rebuild lives on site-rebuild and deploys with ./deploy-site.sh)
BRANCH="$(git -C "$LOCAL_DIR" rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "main" ]]; then
    echo "STOP: you're on branch '$BRANCH'."
    echo "deploy.sh only deploys the LIVE tool from 'main'."
    echo "  Live tool fix?   git switch main   then ./deploy.sh"
    echo "  Test site?       ./deploy-site.sh  (from site-rebuild)"
    echo "Nothing was changed."
    exit 1
fi

echo "=========================================="
echo " Deploying WVARA Membership"
echo "   from: $LOCAL_DIR"
echo "     to: $SERVER:$REMOTE_DIR"
echo "=========================================="
read -r -p "Continue? (y/n) " answer
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Cancelled. Nothing was changed."
    exit 0
fi

echo ""
echo "Step 1 of 4: backing up the live database on the server..."
ssh "$SERVER" "mkdir -p /root/wvara-backups && cp -p $REMOTE_DIR/instance/wvara_membership.db /root/wvara-backups/wvara_membership-$STAMP.db && ls -la /root/wvara-backups/wvara_membership-$STAMP.db"

echo ""
echo "Step 2 of 4: copying code to the server..."
# ADDED 2026-11-06: --exclude 'archive/' keeps the local backup archive off the server
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
# ADDED 2026-11-09: --exclude 'deploy-site.sh' (the test-site deploy script stays on the Mac)

echo ""
echo "Step 3 of 4: resetting permissions and Step 4 of 4: reloading Apache..."
ssh "$SERVER" "cd $REMOTE_DIR && \
    find . -path ./instance -prune -o -path ./venv -prune -o ! -name wvara.keys -exec chown root:www-data {} + && \
    find . -path ./instance -prune -o -path ./venv -prune -o ! -name wvara.keys -exec chmod u=rwX,g=rX,o= {} + && \
    apache2ctl configtest && systemctl reload apache2"

echo ""
echo "=========================================="
echo " Done! Check https://salmancuso.com/tools/wvara"
echo " Database backup: /root/wvara-backups/wvara_membership-$STAMP.db"
echo "=========================================="
