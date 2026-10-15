import { parseDate } from './models.js';

export function calculateFlowMetrics(issues, startState, endState, startDate, endDate) {
  let completedCount = 0;
  let cycleTimes = [];
  let activeWipCount = 0;

  issues.forEach((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];

    if (startTime && endTime && endTime >= startTime) {
      const ctDays = (endTime - startTime) / 86400000;
      cycleTimes.push(ctDays);
      completedCount++;
    }

    const hasStarted = !!startTime;
    const hasFinished = !!endTime;
    if (hasStarted && !hasFinished) {
      activeWipCount++;
    }
  });

  let avgCt = 0;
  let p50 = 0;
  let p85 = 0;

  if (cycleTimes.length > 0) {
    avgCt = cycleTimes.reduce((a, b) => a + b, 0) / cycleTimes.length;
    const sortedCts = [...cycleTimes].sort((a, b) => a - b);
    p50 = sortedCts[Math.floor(sortedCts.length * 0.5)];
    p85 = sortedCts[Math.floor(sortedCts.length * 0.85)];
  }

  return { completedCount, avgCt, p50, p85, activeWipCount };
}

export function computeCFDData(issues, statusColumns, checkedStates, startDate, endDate, endState) {
  const daySteps = [];
  let current = new Date(startDate);
  while (current <= endDate) {
    daySteps.push(new Date(current));
    current.setDate(current.getDate() + 1);
  }

  const cfdData = {};
  checkedStates.forEach((state) => {
    cfdData[state] = new Array(daySteps.length).fill(0);
  });

  const startDayMs = daySteps[0].getTime();
  const msPerDay = 86400000;

  issues.forEach((issue) => {
    const issueTrans = [];
    issueTrans.push({ time: issue.created, state: 'Open' });

    statusColumns.forEach((state) => {
      const time = issue.transitions[state];
      if (time) {
        issueTrans.push({ time, state });
      }
    });

    issueTrans.sort((a, b) => a.time - b.time);

    for (let i = 0; i < issueTrans.length; i++) {
      const activeState = issueTrans[i].state;
      if (!checkedStates.includes(activeState)) continue;

      const t1 = issueTrans[i].time.getTime();
      const t2 =
        i + 1 < issueTrans.length ? issueTrans[i + 1].time.getTime() : endDate.getTime() + msPerDay;

      let d1Idx = Math.floor((t1 - startDayMs) / msPerDay);
      let d2Idx = Math.floor((t2 - startDayMs) / msPerDay);

      if (d1Idx < 0) d1Idx = 0;
      if (d2Idx > daySteps.length) d2Idx = daySteps.length;

      for (let d = d1Idx; d < d2Idx; d++) {
        cfdData[activeState][d]++;
      }
    }
  });

  const approxCtArray = new Array(daySteps.length).fill(0);
  const wipArray = new Array(daySteps.length).fill(0);
  const arrivals = new Array(daySteps.length).fill(0);
  const departures = new Array(daySteps.length).fill(0);

  daySteps.forEach((day, dayIdx) => {
    let wip = 0;
    let done = 0;
    checkedStates.forEach((state) => {
      if (state === endState || state === 'Done' || state === 'Closed') {
        done += cfdData[state][dayIdx];
      } else {
        wip += cfdData[state][dayIdx];
      }
    });
    wipArray[dayIdx] = wip;
    departures[dayIdx] = done;
    arrivals[dayIdx] = wip + done;
  });

  daySteps.forEach((day, dayIdx) => {
    const currentDone = departures[dayIdx];
    if (currentDone === 0) {
      approxCtArray[dayIdx] = 0;
      return;
    }
    let p = dayIdx;
    while (p >= 0 && arrivals[p] > currentDone) {
      p--;
    }
    if (p < 0) p = 0;
    const msDiff = daySteps[dayIdx] - daySteps[p];
    approxCtArray[dayIdx] = msDiff / 86400000;
  });

  return { daySteps, cfdData, wipArray, approxCtArray };
}

export function computeWipRunData(issues, statusColumns, selectedStates, startDate, endDate) {
  const startDay = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
  const endDay = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());

  const daySteps = [];
  for (let d = new Date(startDay); d <= endDay; d.setDate(d.getDate() + 1)) {
    daySteps.push(new Date(d));
  }

  const datasetsData = {};
  selectedStates.forEach((state) => (datasetsData[state] = new Array(daySteps.length).fill(0)));

  const startDayMs = startDay.getTime();
  const msPerDay = 86400000;

  issues.forEach((issue) => {
    const trans = [];
    statusColumns.forEach((state) => {
      if (issue.transitions[state]) trans.push({ time: issue.transitions[state], state: state });
    });
    trans.sort((a, b) => a.time - b.time);

    for (let i = 0; i < trans.length; i++) {
      const s = trans[i].state;
      if (!selectedStates.includes(s)) continue;

      const t1 = trans[i].time.getTime();
      const t2 = i + 1 < trans.length ? trans[i + 1].time.getTime() : endDay.getTime() + msPerDay;

      let d1Idx = Math.floor((t1 - startDayMs) / msPerDay);
      let d2Idx = Math.floor((t2 - startDayMs) / msPerDay);

      if (d1Idx < 0) d1Idx = 0;
      if (d2Idx > daySteps.length) d2Idx = daySteps.length;

      for (let d = d1Idx; d < d2Idx; d++) {
        datasetsData[s][d]++;
      }
    }
  });

  return { daySteps, datasetsData };
}

export function computeSprintCarryoverData(issues, endState, sDate, eDate, unit) {
  const sprintsMap = {};

  issues.forEach((issue) => {
    if (!issue.sprints) return;
    const est = issue.estimation !== null && !isNaN(issue.estimation) ? issue.estimation : 1;

    issue.sprints.forEach((sp) => {
      const spStart = parseDate(sp['Start Date']);
      const spEnd = parseDate(sp['End Date']);
      if (!spStart || !spEnd) return;
      if (spEnd < sDate || spStart > eDate) return;

      if (!sprintsMap[sp['Sprint ID']]) {
        sprintsMap[sp['Sprint ID']] = {
          id: sp['Sprint ID'],
          name: sp['Sprint Name'],
          startDate: sp['Start Date'],
          endDate: sp['End Date'],
          plannedCount: 0,
          plannedPoints: 0,
          completedCount: 0,
          completedPoints: 0,
          carryoverCount: 0,
          carryoverPoints: 0,
        };
      }

      sprintsMap[sp['Sprint ID']].plannedCount += 1;
      sprintsMap[sp['Sprint ID']].plannedPoints += est;

      const endTransition = issue.transitions[endState];
      if (endTransition) {
        const spEndWithGrace = parseDate(sp['End Date']);
        const spStartD = parseDate(sp['Start Date']);
        spEndWithGrace.setDate(spEndWithGrace.getDate() + 1); // grace period

        if (endTransition >= spStartD && endTransition <= spEndWithGrace) {
          sprintsMap[sp['Sprint ID']].completedCount += 1;
          sprintsMap[sp['Sprint ID']].completedPoints += est;
        } else if (sp['Sprint State'] === 'active' && endTransition >= spStartD) {
          sprintsMap[sp['Sprint ID']].completedCount += 1;
          sprintsMap[sp['Sprint ID']].completedPoints += est;
        } else {
          sprintsMap[sp['Sprint ID']].carryoverCount += 1;
          sprintsMap[sp['Sprint ID']].carryoverPoints += est;
        }
      } else {
        sprintsMap[sp['Sprint ID']].carryoverCount += 1;
        sprintsMap[sp['Sprint ID']].carryoverPoints += est;
      }
    });
  });

  let today = new Date();
  if (typeof document !== 'undefined') {
    const endStr = document.getElementById('endDateFilter')?.value;
    if (endStr) {
      today = new Date(endStr);
      today.setHours(23, 59, 59, 999);
    }
  }
  const sortedSprints = Object.values(sprintsMap)
    .filter((s) => s.plannedCount > 0 && s.startDate && new Date(s.endDate) <= today)
    .sort((a, b) => new Date(a.startDate) - new Date(b.startDate));

  const labels = sortedSprints.map((s) => s.name);
  const completedData = sortedSprints.map((s) =>
    unit === 'points' ? s.completedPoints : s.completedCount
  );
  const carryoverData = sortedSprints.map((s) =>
    unit === 'points' ? s.carryoverPoints : s.carryoverCount
  );

  let mean = 0;
  let stddev = 0;
  let p50Val = 0;
  let p85Val = 0;

  if (completedData.length > 0) {
    const sum = completedData.reduce((acc, val) => acc + val, 0);
    mean = sum / completedData.length;
    const variance =
      completedData.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / completedData.length;
    stddev = Math.sqrt(variance);

    const sortedCompleted = [...completedData].sort((a, b) => a - b);
    const getPercentile = (arr, p) => {
      if (arr.length === 0) return 0;
      const index = Math.floor(arr.length * p);
      return arr[Math.max(0, Math.min(arr.length - 1, index))];
    };
    p50Val = getPercentile(sortedCompleted, 0.5);
    p85Val = getPercentile(sortedCompleted, 0.15); // 15th percentile from sorted list represents 85% confidence to achieve
  }

  return { labels, completedData, carryoverData, mean, stddev, p50Val, p85Val };
}
