#!/usr/bin/env bash
# Upload the website to the stack's S3 bucket and refresh CloudFront.
# Needs the AWS CLI, signed in to the same account/region as the stack.
#
#   ./scripts/deploy_site.sh                # stack named "cert-finder"
#   ./scripts/deploy_site.sh my-stack-name
#
# Without the CLI, upload the same files in the S3 console (docs/DEPLOY.md, step 2).
set -euo pipefail

STACK="${1:-cert-finder}"
cd "$(dirname "$0")/.."

output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

python3 scripts/validate_tree.py

BUCKET="$(output SiteBucketName)"
DIST="$(output DistributionId)"
SITE="$(output SiteUrl)"
echo "Uploading to s3://$BUCKET ..."

# Only the public site files; scripts, backend and docs stay out of the bucket.
aws s3 sync . "s3://$BUCKET/" --delete \
  --exclude "*" \
  --include "index.html" \
  --include "stats.html" \
  --include "config.js" \
  --include "data/*"

aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
  --query "Invalidation.Id" --output text >/dev/null

echo "Done: $SITE  (new files show within a minute)"
