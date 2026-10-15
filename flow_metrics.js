function calculateKpis(issues, startState, endState, startDate, endDate, activeStates, waitStates) {
  let totalCompleted = 0;
  let totalCycleTime = 0;
  let totalActiveMs = 0;
  let totalWaitMs = 0;

  issues.forEach((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];

    if (startTime && endTime && endTime >= startTime) {
      if (endTime >= startDate && endTime <= endDate) {
        totalCompleted++;
        totalCycleTime += (endTime - startTime) / 86400000;

        const trans = Object.keys(issue.transitions)
          .map((state) => ({ state, date: issue.transitions[state] }))
          .sort((a, b) => a.date - b.date);

        for (let i = 0; i < trans.length - 1; i++) {
          const current = trans[i];
          const next = trans[i + 1];
          const durationMs = next.date - current.date;

          if (activeStates.includes(current.state)) {
            totalActiveMs += durationMs;
          } else if (waitStates.includes(current.state)) {
            totalWaitMs += durationMs;
          }
        }
      }
    }
  });

  const filterDays = (endDate - startDate) / 86400000;
  let avgThroughput = 0;
  if (filterDays > 0) {
    avgThroughput = (totalCompleted / filterDays) * 7; // items per week
  }

  let avgCT = totalCompleted > 0 ? totalCycleTime / totalCompleted : 0;
  let flowEff =
    totalActiveMs + totalWaitMs > 0 ? (totalActiveMs / (totalActiveMs + totalWaitMs)) * 100 : 0;

  return { totalCompleted, avgCT, avgThroughput, flowEff };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { calculateKpis };
}
