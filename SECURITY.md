# Security and data handling

Report vulnerabilities privately through the repository owner's GitHub profile.
Do not open a public issue containing credentials, Jira exports, or customer data.

The dashboards process selected CSV files in your browser and retain them in
IndexedDB so you can return to an analysis. Use **Clear saved data** before
switching customers or sharing a browser profile. Pages on the same origin share
this cache; host the dashboard on a dedicated origin.

AI coaching is optional. Each request asks before sending aggregate metrics and
selected workflow, sprint, and blocker names to Google Gemini. Those names can
still be confidential. The API key stays in the current tab's memory and is sent
to Google in a request header. Reloading clears the key. Use a restricted key and
appropriate quotas. Browser-side keys are visible to the browser user and any
trusted script executing on that origin.

Exporters require HTTPS and read credentials from environment variables. Keep
real exports and classification results outside the repository. Only simulator
data belongs in `sample_data/`. Git ignore rules do not remove files already
committed, and do not scrub history.

CSV exports preserve original values for analytics. If an issue field starts
with a spreadsheet formula, opening the CSV directly in a spreadsheet may
execute it. Treat exports as untrusted; import text columns explicitly as text.

`npm run build` creates an explicit public asset bundle in `dist/`. Serve and
deploy that directory only. It includes third-party license notices and
Cloudflare security headers. The current HTML uses inline scripts and event
handlers, so the CSP still allows inline scripts; escaping untrusted fields and
rendering AI results as text remain essential defenses.

Before any public release, run:

```bash
npm ci
npm run lint
npm test
npm audit
python3 scripts/check_public_tree.py
python3 scripts/scan_secrets.py --history
python3 scripts/scan_secrets.py
```

The scanner downloads a checksum-pinned Gitleaks binary into ignored `.tools/`
on macOS, Linux, or Windows x64. The history scan requires a complete clone.
Neither scanner proves the absence of sensitive business information; review
sample provenance, screenshots, documents, and Git history separately.
