# AWS Cert Finder

A short quiz for the AWS Student Builder Group event at Constructor University: visitors answer 4–6 questions about their field of study and goals, and get a recommended AWS certification plus a next step. Optional live stats let the presenter show which certifications the room got.

- **Questions & results:** `data/tree.json` (one file, no code)
- **Site:** static, hosted on Vercel (see Deploying)
- **Optional AWS stack** (one CloudFormation template): Lambda + DynamoDB stats API, and S3 + CloudFront hosting with the API on the same domain under `/api/`

```
index.html            reference quiz page (works as-is; the real frontend can replace it)
stats.html            presenter view: live counts, refreshes every 5 s
config.js             settings: stats API URL (empty = stats off)
data/tree.json        all questions, answers, results and cert info
scripts/
  validate_tree.py    checks tree.json (dead ends, loops, missing fields); --paths prints every path
  dev_server.py       local server + fake stats API, no AWS needed
  deploy_site.sh      uploads the site to S3 and refreshes CloudFront (AWS CLI)
backend/
  handler.py          Lambda code (source of truth)
  template.yaml       CloudFormation: S3 + CloudFront site, DynamoDB + Lambda API
  sync_template.py    copies handler.py into template.yaml
  tests/              pytest + moto (mocked DynamoDB)
docs/DEPLOY.md        step-by-step deploy, upload, reset and teardown
```

```
visitor ──https──▶ CloudFront ──/*──────▶ S3 bucket (index.html, stats.html, config.js, data/)
                              └─/api/*──▶ Lambda Function URL ──▶ DynamoDB (one counter per cert)
```

## Run it locally

```bash
python scripts/dev_server.py
# open http://localhost:8000          (quiz)
# open http://localhost:8000/stats.html (live stats)
```

The dev server also serves a fake stats API at `/api/`. To try the stats flow locally, set `statsApiUrl: "/api/"` in `config.js` (and set it back before pushing). Opening `index.html` straight from disk won't work because browsers block `fetch()` of local files; use the server.

## For the frontend: the data contract

The frontend only **walks the tree**. All logic lives in `tree.json`.

```jsonc
{
  "start": "q_experience",               // first node to show
  "meta": { "title", "subtitle", "updated", "disclaimer", "price_note", "resources": [{ "label", "url" }] },
  "nodes": {
    "q_experience": {
      "type": "question",
      "text": "How much hands-on experience ...?",
      "options": [ { "label": "None yet ...", "next": "q_background" } ]   // 2–6 options
    },
    "r_saa": {
      "type": "result",
      "primary": "saa",                   // key in certs: show this as the recommendation
      "next_step": "sap",                 // optional: what to do after
      "reason": "Why this fits the visitor (1–3 sentences)"
    }
  },
  "certs": {
    "saa": {
      "name": "AWS Certified Solutions Architect – Associate",
      "short_name": "Solutions Architect – Associate",
      "level": "Associate",               // Foundational | Associate | Professional | Specialty | Business
      "summary": "...", "good_for": "...",
      "price_usd": 150,                   // or null (e.g. beta exams)
      "status": "active",                 // active | beta
      "note": "optional, e.g. exam version change",
      "url": "https://aws.amazon.com/certification/..."
    }
  }
}
```

Walking it:

1. Load `data/tree.json`, show `nodes[start]`.
2. Question node → show `text` and one button per option. On click, push `{node, answer}` to a history stack and go to `option.next`.
3. Result node → show `certs[primary]` (name, level, summary, price, link), the `reason`, and `certs[next_step]` if present.
4. Back = pop the history stack. Start over = clear it.

Rules worth keeping:

- Don't hard-code questions or exam codes in the frontend. Exam versions change (several do in Nov–Dec 2026), so the data has names, not codes.
- Show `meta.disclaimer`: this is not an official AWS tool.
- Use your own design and colors; don't use AWS logos or the "Powered by AWS" mark.

### Live stats API (optional)

When a visitor reaches a result, send **one** request per quiz run:

```js
fetch(STATS_URL + "result", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ cert: "saa" }),   // the result's primary cert id
  keepalive: true
}).catch(() => {});                        // never block or show an error to the visitor
```

| Call | Response |
|---|---|
| `POST /result` `{"cert": "<id>"}` | `200 {"ok": true}` · `400` unknown id or bad JSON · `413` body > 1 KB |
| `GET /stats` | `200 {"total": 12, "counts": [{"cert": "saa", "count": 5}, ...]}` sorted by count, every cert included (zeros too) |

`STATS_URL` comes from `config.js` (`statsApiUrl`) and ends with `/`. When it's empty, skip the call. `index.html` shows the full pattern if you want to copy it.

## How the questions are organized

The first question is the field of study. Each field has its own track, and every question after it changes the result:

| Field (first answer) | Track | Typical results |
|---|---|---|
| Computer science, software, data science, engineering | `q_tech_*`, `q_focus`, `q_data`, `q_ai`, `q_focus_pro` | All 12 certs, from Foundational to Professional |
| Physics, mathematics | `q_quant_*` | Cloud/AI Practitioner, or Solutions Architect, Data Engineer, ML Engineer |
| Biology, chemistry, biochemistry, earth & environment | `q_life_*` | Same as physics, with field-specific use cases |
| Business, economics, management | `q_biz_*` | Cloud Practitioner, AI Practitioner, AI Business Strategist; Data Engineer for data people |
| Psychology, social sciences, politics, media, humanities | `q_soc_*` | AI Practitioner, AI Business Strategist, Cloud Practitioner; Data/ML Engineer for data people |
| Something else / not a student | `q_experience` and the general questions | Any |

Anyone who answers that they already use the cloud regularly jumps to the technical track (`q_tech_cert_alot`), whatever their field.

Some nodes are shared between tracks (for example `q_time_data`, `q_sci_career` and the `r_research_*` results), so the "tree" is really a graph without loops. Changing a shared node changes it for every track that uses it.

## Editing questions

1. Edit `data/tree.json` (keep ids: questions start with `q_`, results with `r_`).
2. Run `python scripts/validate_tree.py --paths` and read the printed paths. It fails on broken links, loops, missing fields, and warns about unreachable nodes or unused certs.
3. If you add or remove a cert id, also update `CertIds` in the CloudFormation stack (see `docs/DEPLOY.md`), or the API will reject it.

Cert facts were checked against the official AWS exam guide list on 2026-11-03: the Machine Learning – Specialty is retired, SysOps Administrator is now CloudOps Engineer, AI Business Strategist is in beta, and Advanced Networking – Specialty is left out because it retires at the end of 2026.

## Tests

```bash
pip install -r backend/requirements-dev.txt
python scripts/validate_tree.py
python backend/sync_template.py --check
cfn-lint backend/template.yaml
pytest backend/tests
```

GitHub Actions runs the same checks on every push (`.github/workflows/checks.yml`).

## Deploying

**Current setup: Vercel (static, no build step).**

1. [vercel.com](https://vercel.com) → **Continue with GitHub**.
2. **Add New → Project** → import this repo.
3. **Framework Preset: Other**, leave Build and Output settings empty → **Deploy**.
4. Every push to `main` redeploys automatically. `.vercelignore` keeps `backend/`, `scripts/` and `docs/` off the site.

Live stats are off (`statsApiUrl: ""` in `config.js`). To turn them on later, deploy the AWS stack from `docs/DEPLOY.md` (needs a fully activated AWS account with CloudFormation access), put its **StatsApiUrl** output in `config.js`, and set the stack's **AllowedOrigin** to the Vercel URL.

The same stack can also host the whole site on S3 + CloudFront instead of Vercel; see `docs/DEPLOY.md`.
