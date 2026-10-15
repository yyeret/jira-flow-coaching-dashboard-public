# Public readiness audit — 2026-10-15

**Verdict: do not change the existing repository's visibility.** The prepared
source tree addresses the identified release issues, but old commits still
contain customer-derived results and private operational context. Publish a new
repository from the reviewed snapshot. On 2026-10-15 the owner authorized
publication of the clean snapshot as a fresh public repository under ISC and
instructed that the original repository remain private.

## Findings and preparation

| Area | Finding | Prepared change |
| --- | --- | --- |
| Business data | Seven tracked classification batches contain customer issue identifiers and analysis. | Excluded from the release tree; new ignore and release checks. Originals remain in the private primary checkout/history. |
| Private context | Instance profile, personal paths, project exclusions, label mappings, debug scripts, browser artifacts, and a screenshot were mixed with reusable code. | Removed or generalized in the release tree. Default project exclusions are now empty; scope archived projects in export JQL. |
| Git history | Historical blobs retain customer context and classification data. | Prepared a history-free snapshot exporter. No history rewrite, force push, or visibility change. |
| Credentials | Gitleaks found no recognizable credentials in reachable Git history. | Added checksum-pinned, redacted scanning and a CI history scan. This is a bounded detector result, not proof no credential ever existed. |
| Browser injection | CSV fields and model responses reached HTML sinks. | Contextual escaping for CSV fields; text-only AI responses and API errors. Real-browser malicious-input regression coverage. |
| AI privacy | Persistent API keys, keys in request URLs, and no explicit transfer consent. | Memory-only keys, legacy key deletion, header authentication, and per-request disclosure and consent. |
| Retained data | CSV contents persisted in browser storage. | Clear saved data on all three dashboards; delete cache before reloading. |
| Deployment | The workflow and local agent launcher targeted the repository root. | Explicit `dist/` allowlist; no customer data, Python scripts, tests, source maps, or operational docs in the hosted bundle. |
| Supply chain | Unversioned CDN scripts and external fonts; six initial npm findings, three high. | Locally bundled locked scripts, system font fallback, dependency updates and narrow overrides; final npm audit clean. |
| Automation | Mutable action tags and the former Pages action. | Pinned action commits, read-only test permissions, maintained Wrangler action, dependency update configuration. Deployment remains unexecuted and is manual/opt-in in the fresh repository. |
| Transport | Exporters could send credentials over an HTTP instance URL. | Shared HTTPS/configuration validation in all three exporters, with regression tests. |
| Licensing | Both package manifests declared ISC, but no root license existed. | Added the ISC license with Yuval Yeret as holder; generated complete notices for bundled third-party libraries. Removed an unused Forge API dependency. |

The targeted NYC override uses `js-yaml` v4, whose `load` interface matches the
loader's actual call. The local server override updates `compression` within its
compatible major version. Both changes are locked and exercised by validation.

## Validation and limits

- Full JavaScript and Python suites, including real Chrome tests for malicious
  CSV inputs on all three pages, AI consent/header authentication, inert model
  output, and cache clearing. Final result: 34 JavaScript tests and 35 Python tests passed (69 total).
- ESLint, Prettier, Ruff lint/format, source-tree checks, and bundle build passed. ESLint reports seven pre-existing unused-variable warnings and zero errors.
- npm audit of the locked installation: no known vulnerabilities.
- pip-audit resolved 13 Python packages from `requirements.txt`: no known
  vulnerabilities at the time of review. Python dependencies are not locked.
- Gitleaks v8.30.1 reported 32 scanned commits and approximately 8.42 MB of
  history, with zero findings. A separate scan of historical blob content
  identified private context that a credential scanner does not detect.
- Local `npm start` smoke check returned 200 for the dashboard and bundled libraries, and 404 for operational docs, package metadata, scripts, and a removed data artifact.
- Current sample CSVs use simulator identifiers and templates from
  `simulate_flow.py`; no real customer export was identified in that directory.
- The presumed Pages hostname returned HTTP 403 for the homepage and probed
  artifact paths. This does not establish whether past deployments exposed
  files. Account deployment inventories, old deployment URLs, caches, GitHub
  Actions logs/artifacts, and remote-only refs were not audited.
- Browser validation ran on macOS Chrome. The initial audit did not run Linux CI or Windows execution. Release scripts use portable Node/Python APIs and
  include scanner checksums for those platforms.

The client-side cache is not encrypted by this application. The CSP retains
`unsafe-inline` for existing inline scripts and event handlers. Export CSVs can
contain spreadsheet formulas; see `SECURITY.md`. AI requests can disclose
confidential names even when issue bodies are omitted.

The only recorded Git authors are Yuval Yeret identities. That does not prove
ownership of commissioned work or permission to license customer-derived IP.
The ISC file formalizes the existing manifest declaration. The owner approved
ISC and authorized publication of the clean snapshot on 2026-10-15.
Bundled libraries retain their own licenses. Methodology links do not grant
rights to reproduce external guides or third-party trademarks.

Reference material: [ISC license](https://opensource.org/license/isc),
[OWASP XSS prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html),
[Cloudflare deployment action](https://github.com/cloudflare/wrangler-action).

### Release route

Run the snapshot exporter from the prepared branch, choosing a new directory
outside the repository:

```bash
python3 scripts/prepare_public_snapshot.py --output ../jira-flow-public-source
```

It copies the prospective Git tree, including new review files, without `.git`,
ignored exports, dependencies, or build artifacts. It refuses an existing output
directory and runs the source guard first. Review the snapshot, initialize a
new repository, and run the checks there before authorizing publication.

If retaining the current repository URL is mandatory, a separately approved
history rewrite must remove private files and old versions of modified files
from every relevant branch/tag, followed by a fresh-clone audit. A cleanup
commit on its own is insufficient.
