# Deploying to AWS

One CloudFormation template, two ways to use it:

- **Stats API only (current setup).** The site stays on Vercel; AWS runs Lambda + DynamoDB. Parameter `CreateWebsite` = `no` (default). About 2 minutes.
- **Everything on AWS.** `CreateWebsite` = `yes` also creates a private S3 bucket served by CloudFront, with the API on the same domain under `/api/`. About 10 minutes. See "Everything on AWS" below.

No CLI needed. Event-sized traffic stays well inside the Free Tier. Accounts on the new AWS sign-up need the **Paid plan** for CloudFormation; set a spend limit in **AWS Settings → Billing** (minimum $20) and a **Zero spend budget** alert in AWS Budgets.

## Stats API for the Vercel site (current setup)

1. In the AWS console, check the region in the top right (new accounts are fixed to one, e.g. **Europe (Stockholm) eu-north-1**). Do every step in that region.
2. **CloudFormation → Create stack → With new resources (standard)**.
3. **Choose an existing template → Upload a template file** → `backend/template.yaml` → **Next**.
4. Stack name `cert-finder`. Parameters: leave all three defaults (`AllowedOrigin` = `*`, `CertIds` = the long list, `CreateWebsite` = `no`) → **Next**.
5. **Next** again → tick **"I acknowledge that AWS CloudFormation might create IAM resources"** → **Submit**.
6. Wait for `CREATE_COMPLETE` (1–2 minutes).
7. **Outputs** → copy **StatsApiUrl** (`https://….lambda-url.<region>.on.aws/`).
8. Open `StatsApiUrl` + `stats` in the browser. You should see `{"total": 0, "counts": [...]}`.
9. Put the URL in `config.js`: `statsApiUrl: "https://….lambda-url.<region>.on.aws/",` then commit and push. Vercel redeploys in about a minute.
10. Take the quiz on the live site, then open `/stats.html`: the count should go up within 5 seconds.

`AllowedOrigin` = `*` lets the live site, Vercel preview links and local testing all call the API. The API is public either way, so a stricter origin wouldn't stop anyone from sending requests directly.

Before the event, clear the test counts (section 4), and afterwards delete the stack (section 5).

## Everything on AWS (S3 + CloudFront)

Same as above, but set **CreateWebsite** = `yes` in step 4. CloudFront adds 5–10 minutes. Then follow sections 1–3 below.

## 1. Create the stack

1. Sign in to the AWS console. Check the region in the top right and do every step in that same region. The template works in any region.
   - **Free plan accounts (new AWS sign-up)** are locked to one region chosen from the contact address: **Europe (Stockholm) eu-north-1** for European addresses. Use that; Frankfurt isn't available on these accounts.
   - Older or upgraded accounts can pick any region, e.g. Frankfurt eu-central-1.
   - Everything this stack uses (S3, CloudFront, Lambda, DynamoDB, CloudFormation, CloudWatch Logs, IAM) is available on the free plan. It does not use Lambda@Edge or AWS WAF, which free plan accounts can't use.
2. Open **CloudFormation → Create stack → With new resources (standard)**.
3. **Upload a template file** → choose `backend/template.yaml` → Next.
4. Stack name: `cert-finder`.
5. Parameters: set **CreateWebsite** = `yes`; leave the others.
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
- **QR code:** make it from the site's address (the Vercel URL, or **SiteUrl** on the all-AWS setup). The presenter opens the same address + `stats.html` on the projector.

## Updating the site

Upload the changed files again (same steps as section 2). CloudFront caches files for 60 seconds by default and 5 minutes at most, so changes appear within a few minutes. For an instant refresh: **CloudFront → distribution → Invalidations → Create** → `/*` (the script does this for you).

## Changing the Lambda code

1. Edit `backend/handler.py`.
2. `python backend/sync_template.py` (copies it into `template.yaml`; CloudFormation inline code is limited to 4096 characters and the script checks that).
3. `pytest backend/tests`.
4. CloudFormation → stack → **Update** → **Replace current template** → upload the new `template.yaml`.

## After the event

1. Screenshot `stats.html` if you want the numbers.
2. Only on the all-AWS setup: **S3** → the site bucket → **Empty** (a bucket with files in it can't be deleted).
3. **CloudFormation → cert-finder → Delete**. That removes everything the stack created: Lambda, table, role and, if created, bucket and CloudFront.
4. Set `statsApiUrl` back to `""` in `config.js` and push, so the site stops calling a deleted API.

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| `AccessDenied` XML on the site | The file isn't in the bucket at that path. Check that `index.html` is at the bucket root and `tree.json` is inside `data/`. |
| Old version still showing | CloudFront cache. Wait up to 5 minutes or create an invalidation for `/*`. |
| Quiz works but stats stay at 0 | Open the API's `stats` URL in the browser (`StatsApiUrl` + `stats`, or `SiteUrl` + `api/stats`). JSON means the API works and `config.js` is probably wrong; an error page means check **CloudWatch → Log groups → /aws/lambda/…**. |
| Browser console: CORS error | The stack's `AllowedOrigin` doesn't match the site. Set it to `*` (stack → **Update** → **Use current template** → change the parameter). |
| Stack fails with an IAM or "not authorized" error | The account can't create IAM roles yet (new AWS sign-up on the Free plan). Upgrade to the Paid plan in **AWS Settings**, then delete the failed stack and create it again. |
| `400 unknown cert id` | The id isn't in the `CertIds` parameter. Update the stack parameter after adding or removing certs in `tree.json`. |
| Stack deletion fails on the bucket | Empty the bucket first, then delete the stack again. |
| Counts look inflated | The API is public, so anyone with the URL can add counts. Fine for one event; delete the stack afterwards. |

## Security notes

- The bucket is private; only this CloudFront distribution can read it.
- The API only accepts known cert ids and bodies up to 1 KB, and the Lambda role can only update and scan its one table.
- Never put AWS access keys in the frontend or the repo. The site doesn't need any.
- A budget alert (Billing → Budgets, e.g. $1) is a good habit on student accounts.
