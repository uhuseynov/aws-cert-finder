# Deploying to AWS

One CloudFormation stack puts the whole project on AWS:

- **Website:** private S3 bucket, served over HTTPS by CloudFront (`https://d1abc….cloudfront.net/`)
- **Stats API:** Lambda + DynamoDB, reachable on the same domain at `/api/` (so no CORS setup)

About 15 minutes in the AWS console, no CLI needed. Event-sized traffic stays well inside the Free Tier.

## 1. Create the stack

1. Sign in to the AWS console. Check the region in the top right and do every step in that same region. The template works in any region.
   - **Free plan accounts (new AWS sign-up)** are locked to one region chosen from the contact address: **Europe (Stockholm) eu-north-1** for European addresses. Use that; Frankfurt isn't available on these accounts.
   - Older or upgraded accounts can pick any region, e.g. Frankfurt eu-central-1.
   - Everything this stack uses (S3, CloudFront, Lambda, DynamoDB, CloudFormation, CloudWatch Logs, IAM) is available on the free plan. It does not use Lambda@Edge or AWS WAF, which free plan accounts can't use.
2. Open **CloudFormation → Create stack → With new resources (standard)**.
3. **Upload a template file** → choose `backend/template.yaml` → Next.
4. Stack name: `cert-finder`.
5. Parameters: leave both defaults (`AllowedOrigin` only matters for hosting outside AWS, see the end).
6. Next → Next → tick **"I acknowledge that AWS CloudFormation might create IAM resources"** → **Submit**.
7. Wait for `CREATE_COMPLETE`. CloudFront makes this take **5–10 minutes**.

## 2. Upload the website

First set `statsApiUrl: "/api/"` in `config.js` (the repo default is `""` because the live site currently runs on Vercel without stats).

**In the console:**

1. Stack → **Outputs** → note **SiteBucketName** and **SiteUrl**.
2. **S3** → open that bucket → **Upload**.
3. **Add files**: `index.html`, `stats.html`, `config.js`.
   **Add folder**: `data` (so the bucket has `data/tree.json`).
4. **Upload**. Don't upload `backend/`, `scripts/`, `docs/` or `.git`; the bucket is for the site only.

**Or with the AWS CLI:** `./scripts/deploy_site.sh` (validates the tree, syncs the right files, refreshes CloudFront).

Open **SiteUrl**. With `statsApiUrl: "/api/"`, results are counted from the first visit.

## 3. Test it

```bash
SITE=https://d1abc123.cloudfront.net/      # your SiteUrl
curl -s -X POST "${SITE}api/result" -H 'content-type: application/json' -d '{"cert":"saa"}'
# {"ok": true}
curl -s "${SITE}api/stats"
# {"total": 1, "counts": [{"cert": "saa", "count": 1}, ...]}
```

Take the quiz on the site, then open `SiteUrl` + `stats.html` and check that the count went up within 5 seconds.

## 4. Before the event

- **Clear test counts:** DynamoDB → **Tables** → the table in the **StatsTableName** output → **Explore table items** → select all → **Actions → Delete items**.
- **QR code:** make it from **SiteUrl**. The presenter opens `SiteUrl` + `stats.html` on the projector.

## Updating the site

Upload the changed files again (same steps as section 2). CloudFront caches files for 60 seconds by default and 5 minutes at most, so changes appear within a few minutes. For an instant refresh: **CloudFront → distribution → Invalidations → Create** → `/*` (the script does this for you).

## Changing the Lambda code

1. Edit `backend/handler.py`.
2. `python backend/sync_template.py` (copies it into `template.yaml`; CloudFormation inline code is limited to 4096 characters and the script checks that).
3. `pytest backend/tests`.
4. CloudFormation → stack → **Update** → **Replace current template** → upload the new `template.yaml`.

## After the event

1. Screenshot `stats.html` if you want the numbers.
2. **S3** → the site bucket → **Empty** (a bucket with files in it can't be deleted).
3. **CloudFormation → cert-finder → Delete**. That removes everything: bucket, CloudFront, Lambda, table and role.

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| `AccessDenied` XML on the site | The file isn't in the bucket at that path. Check that `index.html` is at the bucket root and `tree.json` is inside `data/`. |
| Old version still showing | CloudFront cache. Wait up to 5 minutes or create an invalidation for `/*`. |
| Quiz works but stats stay at 0 | Open `SiteUrl` + `api/stats` in the browser. JSON means the API works and `config.js` is probably wrong (should be `"/api/"`); an error page means check **CloudWatch → Log groups → /aws/lambda/…**. |
| `400 unknown cert id` | The id isn't in the `CertIds` parameter. Update the stack parameter after adding or removing certs in `tree.json`. |
| Stack deletion fails on the bucket | Empty the bucket first, then delete the stack again. |
| Counts look inflated | The API is public, so anyone with the URL can add counts. Fine for one event; delete the stack afterwards. |

## Hosting the site elsewhere instead (Vercel, GitHub Pages)

The stack still works as the stats backend. Set `statsApiUrl` in `config.js` to the **StatsApiUrl** output (the direct Lambda URL), and set the stack's **AllowedOrigin** parameter to the site's origin, e.g. `https://aws-cert-finder.vercel.app` (no trailing slash). The S3 bucket and CloudFront then simply stay unused.

## Security notes

- The bucket is private; only this CloudFront distribution can read it.
- The API only accepts known cert ids and bodies up to 1 KB, and the Lambda role can only update and scan its one table.
- Never put AWS access keys in the frontend or the repo. The site doesn't need any.
- A budget alert (Billing → Budgets, e.g. $1) is a good habit on student accounts.
