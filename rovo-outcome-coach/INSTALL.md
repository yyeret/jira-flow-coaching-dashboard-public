# Rovo Outcome Framing Coach — Installation Guide

A Rovo Agent for Atlassian Jira that coaches teams to reframe work from
Activity/Output orientation toward Outcome/Impact orientation.

## What it does

- Classifies Jira epics using the **Input → Activity → Output → Outcome → Impact** taxonomy
- Identifies prescriptive language smells ("build X", "implement Y", "Phase N features")
- Suggests outcome-oriented rewrites using the template:
  `[Persona] will be able to [capability], resulting in [measurable change]`
- Analyzes an entire project's epics and shows taxonomy distribution
- Runs coaching conversations to help teams internalize outcome thinking

## Prerequisites

1. [Atlassian Forge CLI](https://developer.atlassian.com/platform/forge/getting-started/) installed:
   ```
   npm install -g @forge/cli
   ```
2. Logged into Forge:
   ```
   forge login
   ```
3. An Atlassian Cloud site with **Rovo** enabled (requires Rovo license or trial).

## Deploy

```bash
cd rovo-outcome-coach

# 1. Register the app (first time only — generates your app ID)
forge register

# 2. Copy the generated app ID into manifest.yml under app.id

# 3. Deploy to development environment
forge deploy

# 4. Install onto your Jira site
forge install --site <your-site>.atlassian.net
```

Select **Jira** when prompted for the product, and pick your site.

## Use in Jira

After installation, the **Outcome Framing Coach** appears in Rovo:

1. Open any Jira project.
2. Click the **Rovo** button (sparkle icon) in the top navigation.
3. Select **Outcome Framing Coach** from the agent list, or type `@Outcome Framing Coach`
   in the Rovo chat.
4. Use one of the conversation starters, or ask directly:
   - *"Analyze epics in project HEAT"*
   - *"Reframe this epic: 'Example | Planning Component Buildout'"*
   - *"What % of my backlog is outcome vs output oriented?"*

## Update the prompt

The entire coaching logic lives in `manifest.yml` under `modules.rovo:agent[0].prompt`.
Edit it and redeploy:

```bash
forge deploy
```

No code changes needed — the agent is prompt-only.

## Permissions

The agent requests:
- `read:jira-work` — to search and read Jira issues for analysis
- `search:confluence` — optional, for linking outcome coaching to Confluence docs/OKRs

## Related

- Local value dashboard: `value_dashboard.html` (same repo)
- Local classifier script: `offline_analysis_value.py`
- Taxonomy skill: `skills/jira-value-ops.md`
