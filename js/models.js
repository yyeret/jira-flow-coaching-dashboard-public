// Scope archived projects in your export JQL; public defaults exclude no projects.
export const DEFAULT_ARCHIVED_PROJECTS = new Set();

// Generic label spellings only; keep organization-specific mappings private.
export const LABEL_STANDARDIZATION_MAP = {
  capex: 'Capex',
  'qa-needed': 'QA-Needed',
  'qa-not-needed': 'QA-Not-Needed',
  demo: 'Demo',
  blocked: 'Blocked',
};

// Work Class primitive: value / failure demand (rework) / maintenance (filler).
export const FAILURE_LABEL_TOKENS = new Set([
  'regression',
  'failure-demand',
  'defect',
  'incident',
  'hotfix',
  'prod-bug',
]);
export const MAINTENANCE_LABEL_TOKENS = new Set([
  'filler-techdebt',
  'filler-lowpriority',
  'lowpriority',
  'keep-busy',
  'chore',
]);

// Infer a work class from issue type + labels (for real Jira exports lacking an
// explicit Work Class column). Explicit metadata always takes precedence.
export function inferWorkClass(issueType, labels) {
  const labelSet = new Set((labels || []).map((l) => String(l).trim().toLowerCase()));
  const type = (issueType || '').trim().toLowerCase();
  if (type === 'bug' || [...labelSet].some((l) => FAILURE_LABEL_TOKENS.has(l)))
    return 'Failure Demand';
  if ([...labelSet].some((l) => MAINTENANCE_LABEL_TOKENS.has(l))) return 'Maintenance';
  return 'Value';
}

// Cost of Delay proxy for real Jira exports that have no CoD column. Jira's
// Priority field is the most common ordinal value signal; map it to a magnitude.
export const PRIORITY_COD_MAP = {
  highest: 90,
  blocker: 90,
  critical: 90,
  p1: 90,
  high: 60,
  major: 60,
  p2: 60,
  medium: 35,
  normal: 35,
  p3: 35,
  low: 15,
  minor: 15,
  p4: 15,
  lowest: 5,
  trivial: 5,
  p5: 5,
};

export function priorityToCoD(priorityStr) {
  if (!priorityStr) return null;
  const v = PRIORITY_COD_MAP[String(priorityStr).trim().toLowerCase()];
  return v === undefined ? null : v;
}

export function parseDate(dateStr) {
  if (!dateStr) return null;
  const cleanStr = dateStr.replace(' ', 'T');
  const d = new Date(cleanStr);
  return isNaN(d) ? null : d;
}

export function isDateString(str) {
  if (!str) return false;
  const cleanStr = str.replace(' ', 'T');
  const d = new Date(cleanStr);
  if (isNaN(d.getTime())) return false;
  return /[-/:]/.test(str);
}

export function getFormalParent(reason) {
  if (!reason) return 'Impediment';
  if (reason.startsWith('Product:')) return 'Requirements / Design';
  if (reason.startsWith('Tech:')) return 'Internal Code/Issue Dependency';
  if (reason.startsWith('Infra:')) return 'Environment / Infrastructure';
  if (reason.startsWith('External:')) return 'External Vendor/Tool Dependency';
  if (reason.startsWith('Team:')) return 'Team Dependency / Alignment';
  if (reason.startsWith('Other:')) return 'Other Blocker / Uncategorized';
  return reason;
}

export function classifyCommentSemantic(text, formalReason) {
  const cleanReason = (formalReason || 'Impediment').trim();
  if (
    ['Product:', 'Tech:', 'Infra:', 'External:', 'Team:', 'Other:'].some((prefix) =>
      cleanReason.startsWith(prefix)
    )
  ) {
    return cleanReason;
  }
  if (!text || text.trim() === '') {
    if (cleanReason === 'Internal Code/Issue Dependency') return 'Tech: Upstream Ticket Block';
    if (cleanReason === 'External Vendor/Tool Dependency')
      return 'External: Third-Party API / Vendor';
    if (cleanReason === 'Environment / Infrastructure') return 'Infra: Environment issue';
    if (cleanReason === 'Requirements / Design') return 'Product: Missing Specs & AC';
    return cleanReason;
  }

  // Clean quotes and spacing first
  let textClean = text.trim().replace(/^["'“”`‘\s]+|["'“”`’\s]+$/g, '');

  // Strip noise prefixes
  const noiseRegex =
    /^(?:flagged\s+as|flagged\s+because|flagged|flag\s+added|adding\s+flag|reopened\s+because|i\s+reopened\s+this\s+because|,?\s*i\s+reopened\s+this|blocker|blocked\s+because|blocked)[:,\s]*/i;
  textClean = textClean.replace(noiseRegex, '').trim();

  // Re-clean quotes/punctuation
  textClean = textClean.replace(/^["'“”`‘\s,.\-–—]+|["'“”`’\s,.\-–—]+$/g, '').trim();

  if (!textClean) {
    return cleanReason;
  }

  const textLower = textClean.toLowerCase();

  // 1. Check for Jira ticket match first (anywhere in comment)
  const ticketMatch = textClean.match(/\b([a-zA-Z]+-\d+)\b/);
  if (ticketMatch) {
    return `Tech: Upstream Ticket Block (${ticketMatch[1].toUpperCase()})`;
  }

  // 2. Specific Heuristic Classifications

  // Product: UX/Design
  if (['design', 'ux', 'wireframe', 'mock', 'ui', 'prototype'].some((k) => textLower.includes(k))) {
    return 'Product: UX/Design Awaiting';
  }

  // Product: Awaiting Decision / Priority Pivot
  if (
    [
      'decision',
      'prioritization',
      'priority',
      'direction',
      'product owner',
      'po',
      'pm',
      'owner',
      'on hold',
      'tbd',
      'decoupling',
      'sunset',
    ].some((k) => textLower.includes(k))
  ) {
    return 'Product: Priority Pivot / Decisions';
  }

  // Product: Missing Specs & AC
  if (
    cleanReason === 'Requirements / Design' ||
    [
      'details',
      'clarity',
      'ac',
      'acceptance criteria',
      'criteria',
      'edge cases',
      'spec',
      'requirement',
      'clarif',
      'question',
      'clarify',
      'confirm',
      '?',
      'ask',
      'needs definition',
      'need to groom',
      'to groom',
      'grooming',
    ].some((k) => textLower.includes(k))
  ) {
    return 'Product: Missing Specs & AC';
  }

  // External: Third-Party API / Vendor
  if (
    [
      'vendor',
      'sailthru',
      'third-party',
      'partner',
      'external',
      'hoot',
      'comscore',
      'blueconic',
      'facebook',
      'fb',
      'alley',
    ].some((k) => textLower.includes(k))
  ) {
    return 'External: Third-Party API / Vendor';
  }

  // External: Client / Stakeholder Feedback
  if (
    ['client', 'customer', 'feedback', 'stakeholder', 'email', 'adrian', 'cm ', 'property'].some(
      (k) => textLower.includes(k)
    )
  ) {
    return 'External: Client/Stakeholder Feed';
  }

  // Infra: Platform Environment Wait
  if (
    [
      'environment assist',
      'vip',
      'hosting',
      'pipeline',
      'build',
      'ci/cd',
      'staging env',
      'sandbox',
      'aws',
      'cloudflare',
    ].some((k) => textLower.includes(k))
  ) {
    return 'Infra: Platform Environment Wait';
  }

  // Infra: Downtime / Outage
  if (['down', 'outage', 'offline', 'crash', 'unreachable'].some((k) => textLower.includes(k))) {
    return 'Infra: Downtime / Outage';
  }

  // Infra: Access / Permissions
  if (
    ['access', 'credentials', 'permission', 'vpn', 'password', 'login', 'helpdesk'].some((k) =>
      textLower.includes(k)
    )
  ) {
    return 'Infra: Access / Permissions';
  }

  // Infra: DWH / Data Block
  if (['dwh', 'data', 'migration', 'database', 'db '].some((k) => textLower.includes(k))) {
    return 'Infra: DWH / Data Block';
  }

  // Team: Resource Capacity / Out
  if (
    ['sick', 'vacation', 'holiday', 'leave', 'capacity', 'out of office', 'ooo', 'away'].some((k) =>
      textLower.includes(k)
    )
  ) {
    return 'Team: Resource Capacity / Out';
  }

  // Team: Discussion / Alignment
  if (
    ['discuss', 'meeting', 'chat', 'align', 'sync', 'talk', 'standup'].some((k) =>
      textLower.includes(k)
    )
  ) {
    return 'Team: Discussion / Alignment';
  }

  // Tech: Co-deployment Batch Constraint
  if (
    [
      'released together',
      'go together',
      'co-deploy',
      'batch',
      'release window',
      'release train',
      'deploy together',
      'enotify',
    ].some((k) => textLower.includes(k))
  ) {
    return 'Tech: Co-deployment Batch Constraint';
  }

  // Tech: QA & Testing
  if (
    ['qa', 'test', 'verify', 'validation', 'bugs', 'regression', 'defect', 'testing'].some((k) =>
      textLower.includes(k)
    )
  ) {
    return 'Tech: QA & Testing';
  }

  // Tech: PR / Code Review
  if (
    ['pr ', 'pull request', 'merge', 'approved', 'deploy', 'code review', 'review'].some((k) =>
      textLower.includes(k)
    )
  ) {
    return 'Tech: PR / Code Review';
  }

  // 3. Fallback for short comment (<= 45 chars): make it a dynamic title-case category
  if (textClean.length <= 45) {
    return cleanToCategory(textClean);
  }

  // 4. Fallback for other long comments
  return 'Other: Uncategorized Blocker';
}

function cleanToCategory(str) {
  if (!str) return '';
  let clean = str.trim().replace(/^["'\-–—\s]+|["'\-–—\s\.]+$/g, '');
  return clean
    .split(/\s+/)
    .map((w) => {
      const upper = w.toUpperCase();
      if (['PR', 'QA', 'UX', 'UI', 'DB', 'API', 'SLA', 'PROD', 'DEV', 'UAT'].includes(upper)) {
        return upper;
      }
      if (/^[A-Z0-9]+-\d+$/i.test(w)) {
        return upper;
      }
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    })
    .join(' ');
}

export function buildFlagHistoryMap(rawFlagData) {
  const flagHistoryMap = {};
  if (!rawFlagData || rawFlagData.length === 0) return flagHistoryMap;

  const groupedFlags = {};
  rawFlagData.forEach((row) => {
    const key = row['Issue Key'];
    if (!key) return;
    if (!groupedFlags[key]) groupedFlags[key] = [];
    groupedFlags[key].push(row);
  });

  const now = new Date();
  Object.keys(groupedFlags).forEach((key) => {
    const events = groupedFlags[key].sort((a, b) => parseDate(a.Date) - parseDate(b.Date));
    let totalTimeMs = 0;
    let lastFlaggedTime = null;
    let lastFlagEvent = null;
    const reasons = new Set();
    const semanticReasons = new Set();
    const reasonDurationsMs = {};
    const semanticDurationsMs = {};

    events.forEach((e) => {
      const d = parseDate(e.Date);
      if (!d) return;

      if (e.Action === 'Flagged') {
        if (lastFlaggedTime) {
          const duration = d - lastFlaggedTime;
          totalTimeMs += duration;
          const prevSemantic = classifyCommentSemantic(
            lastFlagEvent.Comment,
            lastFlagEvent.Reason || 'Impediment'
          );
          const prevFormal = getFormalParent(prevSemantic);
          reasonDurationsMs[prevFormal] = (reasonDurationsMs[prevFormal] || 0) + duration;
          semanticDurationsMs[prevSemantic] = (semanticDurationsMs[prevSemantic] || 0) + duration;
        }
        lastFlaggedTime = d;
        lastFlagEvent = e;

        const sem = classifyCommentSemantic(e.Comment, e.Reason || 'Impediment');
        reasons.add(getFormalParent(sem));
        semanticReasons.add(sem);
      } else if (e.Action === 'Unflagged' || !e.Action) {
        if (lastFlaggedTime) {
          const duration = d - lastFlaggedTime;
          totalTimeMs += duration;

          const prevSemantic = classifyCommentSemantic(
            lastFlagEvent.Comment,
            lastFlagEvent.Reason || 'Impediment'
          );
          const prevFormal = getFormalParent(prevSemantic);
          reasonDurationsMs[prevFormal] = (reasonDurationsMs[prevFormal] || 0) + duration;
          semanticDurationsMs[prevSemantic] = (semanticDurationsMs[prevSemantic] || 0) + duration;

          lastFlaggedTime = null;
          lastFlagEvent = null;
        }
      }
    });

    if (lastFlaggedTime) {
      const duration = now - lastFlaggedTime;
      totalTimeMs += duration;

      const prevSemantic = classifyCommentSemantic(
        lastFlagEvent.Comment,
        lastFlagEvent.Reason || 'Impediment'
      );
      const prevFormal = getFormalParent(prevSemantic);
      reasonDurationsMs[prevFormal] = (reasonDurationsMs[prevFormal] || 0) + duration;
      semanticDurationsMs[prevSemantic] = (semanticDurationsMs[prevSemantic] || 0) + duration;
    }

    const reasonDurations = {};
    Object.keys(reasonDurationsMs).forEach((r) => {
      reasonDurations[r] = reasonDurationsMs[r] / 86400000;
    });

    const semanticDurations = {};
    Object.keys(semanticDurationsMs).forEach((s) => {
      semanticDurations[s] = semanticDurationsMs[s] / 86400000;
    });

    flagHistoryMap[key] = {
      totalFlaggedDays: totalTimeMs / 86400000,
      reasons: Array.from(reasons),
      semanticReasons: Array.from(semanticReasons),
      reasonDurations: reasonDurations,
      semanticDurations: semanticDurations,
    };
  });

  return flagHistoryMap;
}

export function parseIssues(rawData, statusColumns, metaMap, sprintMap, flagHistoryMap) {
  return rawData
    .filter((row) => {
      if (!row || !row['Issue Key']) return false;
      const proj = row['Issue Key'].split('-')[0];
      if (DEFAULT_ARCHIVED_PROJECTS.has(proj)) return false;
      return true;
    })
    .map((row) => {
      const issueKey = row['Issue Key'];
      const metaRow = metaMap[issueKey];
      const labelsStr = metaRow ? metaRow['Labels'] : '';
      const rawLabels = labelsStr
        ? labelsStr
            .split(',')
            .map((l) => l.trim())
            .filter((l) => l)
        : [];
      const labelsList = rawLabels.map((l) => {
        const cleanLow = l.toLowerCase();
        if (LABEL_STANDARDIZATION_MAP[cleanLow]) {
          return LABEL_STANDARDIZATION_MAP[cleanLow];
        }
        return l;
      });

      let rawUnplanned = null;
      const unplannedKeys = ['Unplanned'];
      for (let key of unplannedKeys) {
        if (row[key]) {
          rawUnplanned = row[key];
          break;
        }
        if (metaRow && metaRow[key]) {
          rawUnplanned = metaRow[key];
          break;
        }
      }
      let unplannedStatus = 'No';
      if (rawUnplanned !== null && rawUnplanned !== undefined && rawUnplanned.trim() !== '') {
        const low = rawUnplanned.toLowerCase();
        if (low === 'yes' || low === 'true' || low === '1') unplannedStatus = 'Yes';
        else unplannedStatus = 'No';
      }

      let rawEstimation = null;
      const estimationKeys = ['Story Points', 'Story point estimate', 'Estimation'];
      for (let key of estimationKeys) {
        if (row[key]) {
          rawEstimation = row[key];
          break;
        }
        if (metaRow && metaRow[key]) {
          rawEstimation = metaRow[key];
          break;
        }
      }
      const estimation = rawEstimation ? parseFloat(rawEstimation) : null;

      let rawFlagged = null;
      if (metaRow && metaRow['Flagged']) {
        rawFlagged = metaRow['Flagged'];
      }

      const resolution = metaRow && metaRow['Resolution'] ? metaRow['Resolution'].trim() : '';
      const flagInfo = flagHistoryMap[issueKey] || {
        totalFlaggedDays: 0,
        reasons: [],
        semanticReasons: [],
        reasonDurations: {},
        semanticDurations: {},
      };

      // Work Class / Cost of Delay: explicit column wins; otherwise infer from
      // issue type + labels so real Jira exports (no Work Class column) still classify.
      let workClass = metaRow && metaRow['Work Class'] ? metaRow['Work Class'].trim() : '';
      if (!workClass) workClass = inferWorkClass(row['Issue Type'], rawLabels);
      let costOfDelay = null;
      if (metaRow && metaRow['Cost of Delay']) {
        const c = parseFloat(metaRow['Cost of Delay']);
        if (!isNaN(c)) costOfDelay = c;
      }
      // Cost of Delay proxies for real Jira exports: Priority field, then backlog Rank.
      const pickField = (...names) => {
        for (const n of names) {
          if (metaRow && metaRow[n] && String(metaRow[n]).trim()) return String(metaRow[n]).trim();
          if (row[n] && String(row[n]).trim()) return String(row[n]).trim();
        }
        return '';
      };
      const priorityField = pickField('Priority');
      const rank = pickField('Rank', 'Rank (LexoRank)', 'Backlog Rank');

      const issue = {
        key: issueKey,
        summary: row['Summary'],
        type: row['Issue Type'],
        created: parseDate(row['Created Date']),
        updated: parseDate(row['Updated Date']),
        currentStatus: row['Current Status'],
        transitions: {},
        sprints: sprintMap[issueKey] || [],
        labels: labelsList,
        estimation: estimation,
        unplanned: unplannedStatus,
        resolution: resolution,
        flagged: rawFlagged,
        flaggedDays: flagInfo.totalFlaggedDays,
        flagReasons: flagInfo.reasons,
        flagSemanticReasons: flagInfo.semanticReasons,
        flagReasonDurations: flagInfo.reasonDurations,
        flagSemanticDurations: flagInfo.semanticDurations,
        epicLink: metaRow ? metaRow['Epic Link'] || '' : '',
        workClass: workClass,
        costOfDelay: costOfDelay,
        priorityField: priorityField,
        rank: rank,
      };

      statusColumns.forEach((status) => {
        if (row[status]) {
          issue.transitions[status] = parseDate(row[status]);
        }
      });

      return issue;
    })
    .filter((issue) => issue.created !== null);
}
