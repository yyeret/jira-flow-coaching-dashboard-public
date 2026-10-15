/**
 * Sprint data pipeline tests.
 *
 * Tests cover:
 *  1. findFile – correct file selected when both sprint_data.csv and
 *                custom_sprint_data.csv are present in the folder
 *  2. buildSprintMap – sprint rows are grouped by issue key
 *  3. issueSprintAttachment – parsedIssues get .sprints populated
 *  4. carryoverFilter – only sprints whose End Date is within sDate..eDate
 *                        reach the chart
 *  5. carryoverCounting – planned / completed / carryover counts are correct
 */

// ---------------------------------------------------------------------------
// 1. findFile logic (extracted from index.html folderInput handler)
// ---------------------------------------------------------------------------

function findFile(files, exactName, fallbackSubstr) {
  return (
    files.find((f) => f.name === exactName) || files.find((f) => f.name.includes(fallbackSubstr))
  );
}

describe('findFile', () => {
  const makeFile = (name) => ({ name });

  it('prefers exact match over substring match', () => {
    const files = [
      makeFile('custom_sprint_data.csv'), // has substring but isn't exact
      makeFile('sprint_data.csv'), // exact match
    ];
    const found = findFile(files, 'sprint_data.csv', 'sprint_data.csv');
    expect(found.name).toBe('sprint_data.csv');
  });

  it('returns the custom_ prefixed file when exact name is absent', () => {
    const files = [makeFile('custom_sprint_data.csv')];
    const found = findFile(files, 'sprint_data.csv', 'sprint_data.csv');
    expect(found.name).toBe('custom_sprint_data.csv');
  });

  it('returns undefined when no file matches', () => {
    const files = [makeFile('flow_analytics_export.csv')];
    const found = findFile(files, 'sprint_data.csv', 'sprint_data.csv');
    expect(found).toBeUndefined();
  });

  it('exact match wins even when custom_ variant comes last', () => {
    const files = [makeFile('sprint_data.csv'), makeFile('custom_sprint_data.csv')];
    const found = findFile(files, 'sprint_data.csv', 'sprint_data.csv');
    expect(found.name).toBe('sprint_data.csv');
  });
});

// ---------------------------------------------------------------------------
// 2. buildSprintMap – groups sprint rows by issue key
// ---------------------------------------------------------------------------

function buildSprintMap(rawSprintData) {
  const map = {};
  rawSprintData.forEach((s) => {
    if (!s['Issue Key']) return;
    if (!map[s['Issue Key']]) map[s['Issue Key']] = [];
    map[s['Issue Key']].push(s);
  });
  return map;
}

describe('buildSprintMap', () => {
  const rows = [
    {
      'Issue Key': 'CI-1',
      'Sprint ID': '10',
      'Sprint Name': 'S1',
      'Sprint State': 'closed',
      'Start Date': '2026-04-01T00:00:00Z',
      'End Date': '2026-04-14T00:00:00Z',
    },
    {
      'Issue Key': 'CI-2',
      'Sprint ID': '10',
      'Sprint Name': 'S1',
      'Sprint State': 'closed',
      'Start Date': '2026-04-01T00:00:00Z',
      'End Date': '2026-04-14T00:00:00Z',
    },
    {
      'Issue Key': 'CI-1',
      'Sprint ID': '11',
      'Sprint Name': 'S2',
      'Sprint State': 'active',
      'Start Date': '2026-04-15T00:00:00Z',
      'End Date': '2026-04-28T00:00:00Z',
    },
  ];

  it('groups rows by issue key', () => {
    const map = buildSprintMap(rows);
    expect(Object.keys(map)).toHaveLength(2);
    expect(map['CI-1']).toHaveLength(2);
    expect(map['CI-2']).toHaveLength(1);
  });

  it('skips rows missing Issue Key', () => {
    const map = buildSprintMap([...rows, { 'Sprint ID': '99' }]);
    expect(Object.keys(map)).toHaveLength(2);
  });

  it('returns empty map for empty input', () => {
    expect(buildSprintMap([])).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// 3. issueSprintAttachment – issues get .sprints from the map
// ---------------------------------------------------------------------------

function attachSprints(rawIssues, sprintMap) {
  return rawIssues.map((r) => ({
    key: r['Issue Key'],
    sprints: sprintMap[r['Issue Key']] || [],
  }));
}

describe('issueSprintAttachment', () => {
  const sprintMap = {
    'CI-1': [
      {
        'Sprint ID': '10',
        'Sprint Name': 'S1',
        'Start Date': '2026-04-01T00:00:00Z',
        'End Date': '2026-04-14T00:00:00Z',
      },
    ],
  };

  it('attaches sprints to matching issue', () => {
    const issues = attachSprints([{ 'Issue Key': 'CI-1' }], sprintMap);
    expect(issues[0].sprints).toHaveLength(1);
    expect(issues[0].sprints[0]['Sprint Name']).toBe('S1');
  });

  it('attaches empty array when issue has no sprint rows', () => {
    const issues = attachSprints([{ 'Issue Key': 'CI-99' }], sprintMap);
    expect(issues[0].sprints).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 4 & 5. carryoverFilter + carryoverCounting
// ---------------------------------------------------------------------------

function parseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d) ? null : d;
}

function buildSprintsMap(issues, sDate, eDate, endState) {
  const sprintsMap = {};
  issues.forEach((issue) => {
    if (!issue.sprints) return;
    issue.sprints.forEach((sp) => {
      const spStart = parseDate(sp['Start Date']);
      const spEnd = parseDate(sp['End Date']);
      if (!spStart || !spEnd) return;
      if (spEnd < sDate || spStart > eDate) return; // outside date filter

      if (!sprintsMap[sp['Sprint ID']]) {
        sprintsMap[sp['Sprint ID']] = {
          id: sp['Sprint ID'],
          name: sp['Sprint Name'],
          startDate: sp['Start Date'],
          endDate: sp['End Date'],
          planned: 0,
          completed: 0,
          carryover: 0,
        };
      }
      sprintsMap[sp['Sprint ID']].planned += 1;

      const endTransition = issue.transitions && issue.transitions[endState];
      if (endTransition) {
        const spEndGrace = parseDate(sp['End Date']);
        spEndGrace.setDate(spEndGrace.getDate() + 1);
        if (endTransition >= spStart && endTransition <= spEndGrace) {
          sprintsMap[sp['Sprint ID']].completed += 1;
        } else if (sp['Sprint State'] === 'active' && endTransition >= spStart) {
          sprintsMap[sp['Sprint ID']].completed += 1;
        } else {
          sprintsMap[sp['Sprint ID']].carryover += 1;
        }
      } else {
        sprintsMap[sp['Sprint ID']].carryover += 1;
      }
    });
  });
  return sprintsMap;
}

const SPRINT = {
  'Sprint ID': '10',
  'Sprint Name': 'S1',
  'Sprint State': 'closed',
  'Start Date': '2026-04-01T00:00:00Z',
  'End Date': '2026-04-14T00:00:00Z',
};
const sDate = new Date('2026-01-01');
const eDate = new Date('2026-12-31');

describe('carryoverFilter', () => {
  it('includes sprints whose End Date is within date range', () => {
    const issues = [{ sprints: [SPRINT], transitions: {} }];
    const map = buildSprintsMap(issues, sDate, eDate, 'Done');
    expect(Object.keys(map)).toHaveLength(1);
  });

  it('excludes sprints ending before sDate', () => {
    const oldSprint = { ...SPRINT, 'End Date': '2025-01-01T00:00:00Z' };
    const issues = [{ sprints: [oldSprint], transitions: {} }];
    const map = buildSprintsMap(issues, sDate, eDate, 'Done');
    expect(Object.keys(map)).toHaveLength(0);
  });

  it('excludes sprints starting after eDate', () => {
    const futureSprint = {
      ...SPRINT,
      'Start Date': '2027-01-01T00:00:00Z',
      'End Date': '2027-01-14T00:00:00Z',
    };
    const issues = [{ sprints: [futureSprint], transitions: {} }];
    const map = buildSprintsMap(issues, sDate, eDate, 'Done');
    expect(Object.keys(map)).toHaveLength(0);
  });
});

describe('carryoverCounting', () => {
  it('counts completed issue when Done is within sprint window', () => {
    const issue = {
      sprints: [SPRINT],
      transitions: { Done: new Date('2026-04-10T00:00:00Z') },
    };
    const map = buildSprintsMap([issue], sDate, eDate, 'Done');
    expect(map['10'].planned).toBe(1);
    expect(map['10'].completed).toBe(1);
    expect(map['10'].carryover).toBe(0);
  });

  it('counts carryover when Done is after sprint end', () => {
    const issue = {
      sprints: [SPRINT],
      transitions: { Done: new Date('2026-05-01T00:00:00Z') },
    };
    const map = buildSprintsMap([issue], sDate, eDate, 'Done');
    expect(map['10'].carryover).toBe(1);
    expect(map['10'].completed).toBe(0);
  });

  it('counts carryover when issue has no Done transition', () => {
    const issue = { sprints: [SPRINT], transitions: {} };
    const map = buildSprintsMap([issue], sDate, eDate, 'Done');
    expect(map['10'].carryover).toBe(1);
  });

  it('counts carryover when issue is completed in a later sprint', () => {
    const laterSprint = {
      ...SPRINT,
      'Sprint ID': '11',
      'Sprint Name': 'S2',
      'Start Date': '2026-04-15T00:00:00Z',
      'End Date': '2026-04-28T00:00:00Z',
    };
    const issue = {
      sprints: [SPRINT, laterSprint],
      transitions: { Done: new Date('2026-04-20T00:00:00Z') },
    };
    const map = buildSprintsMap([issue], sDate, eDate, 'Done');
    expect(map['10'].carryover).toBe(1); // not done in S1
    expect(map['11'].completed).toBe(1); // done in S2
  });

  it('accumulates across multiple issues in one sprint', () => {
    const issues = [
      { sprints: [SPRINT], transitions: { Done: new Date('2026-04-10T00:00:00Z') } },
      { sprints: [SPRINT], transitions: {} },
      { sprints: [SPRINT], transitions: { Done: new Date('2026-05-01T00:00:00Z') } },
    ];
    const map = buildSprintsMap(issues, sDate, eDate, 'Done');
    expect(map['10'].planned).toBe(3);
    expect(map['10'].completed).toBe(1);
    expect(map['10'].carryover).toBe(2);
  });
});
