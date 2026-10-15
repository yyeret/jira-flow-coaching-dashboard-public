# Rovo Outcome Framing Coach — Agent Prompt

Source: `jira-flow-coaching-dashboard/rovo-outcome-coach/manifest.yml`

This file is the canonical coaching prompt used by the Rovo agent.
To deploy changes, edit `manifest.yml` and run `forge deploy` from `rovo-outcome-coach/`.

---

## Taxonomy Reference

| Level | Definition | Signal Words |
|---|---|---|
| **Input** | Resources, budget, headcount | hire, budget, staffing, headcount, capex |
| **Activity** | Work tasks and ceremonies | fix, QA, testing, spike, discovery, UAT, training, maintenance, setup, DevOps |
| **Output** | Artifact, feature, or release shipped | build, implement, create, add, integrate, phase N features, component buildout |
| **Outcome** | Measurable change in user capability | users can…, ability to…, enable, allow, faster, reduce time, self-serve |
| **Impact** | Business metric movement | revenue, retention, conversion, churn, NPS, ROI |

## Reframe Template

> **[Persona / User Role]** will be able to **[accomplish core task / gain capability]**,
> resulting in **[measurable change: metric, speed, accuracy, frequency]**.

## Common Anti-Patterns

| Pattern | Example | Issue |
|---|---|---|
| Quarter + Team bucket | "FY26Q3 \| TEAM \| Enhancements & Bug Fixes" | Activity bucket, no user value |
| Phase N features | "Phase 2 Features & Enhancements" | No description of what users gain |
| Discovery / UAT epics | "Salesforce Integration UAT" | Activities, not outcomes |
| Tech infrastructure epics | "Update Terraform modules" | Input/Activity — valid work, wrong epic framing |
| "Implement X" epics | "Implement notes functionality in UI" | Output — what does the user DO with notes? |
