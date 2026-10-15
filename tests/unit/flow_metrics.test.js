const { calculateKpis } = require('../../flow_metrics');

describe('calculateKpis', () => {
  it('should calculate KPIs correctly for completed issues', () => {
    const issues = [
      {
        transitions: {
          Unmapped: new Date('2022-12-31').getTime(),
          Open: new Date('2023-01-01').getTime(),
          Implement: new Date('2023-01-02').getTime(),
          Done: new Date('2023-01-05').getTime(),
        },
      },
      {
        transitions: {
          Open: new Date('2023-01-01').getTime(),
          Implement: new Date('2023-01-03').getTime(),
          Done: new Date('2023-01-04').getTime(),
        },
      },
    ];

    const startState = 'Implement';
    const endState = 'Done';
    const startDate = new Date('2023-01-01').getTime();
    const endDate = new Date('2023-01-10').getTime();
    const activeStates = ['Implement'];
    const waitStates = ['Open'];

    const kpis = calculateKpis(
      issues,
      startState,
      endState,
      startDate,
      endDate,
      activeStates,
      waitStates
    );

    expect(kpis.totalCompleted).toBe(2);
    // Issue 1: 3 days, Issue 2: 1 day -> average 2 days
    expect(kpis.avgCT).toBe(2);
    // Total active ms = (Jan 5 - Jan 2) + (Jan 4 - Jan 3) = 3 days + 1 day = 4 days
    // Total wait ms = (Jan 2 - Jan 1) + (Jan 3 - Jan 1) = 1 day + 2 days = 3 days
    // Flow efficiency = 4 / 7 * 100 = 57.14%
    expect(kpis.flowEff).toBeCloseTo(57.14, 2);
  });

  it('should handle issues completed outside the date range', () => {
    const issues = [
      {
        transitions: {
          Open: new Date('2023-01-01').getTime(),
          Implement: new Date('2023-01-02').getTime(),
          Done: new Date('2023-01-05').getTime(),
        },
      },
    ];

    const startState = 'Implement';
    const endState = 'Done';
    const startDate = new Date('2023-01-06').getTime();
    const endDate = new Date('2023-01-10').getTime();
    const activeStates = ['Implement'];
    const waitStates = ['Open'];

    const kpis = calculateKpis(
      issues,
      startState,
      endState,
      startDate,
      endDate,
      activeStates,
      waitStates
    );

    expect(kpis.totalCompleted).toBe(0);
    expect(kpis.avgCT).toBe(0);
    expect(kpis.avgThroughput).toBe(0);
  });

  it('should return zeroes for an empty issue list', () => {
    const startDate = new Date('2023-01-01').getTime();
    const endDate = new Date('2023-01-10').getTime();
    const result = calculateKpis(
      [],
      'Implement',
      'Done',
      startDate,
      endDate,
      ['Implement'],
      ['Open']
    );

    expect(result).toEqual({
      totalCompleted: 0,
      avgCT: 0,
      avgThroughput: 0,
      flowEff: 0,
    });
  });

  it('should handle zero or negative date filter range gracefully', () => {
    const startDate = new Date('2023-01-10').getTime();
    const endDate = new Date('2023-01-01').getTime(); // Inverted range
    const issues = [
      {
        transitions: {
          Implement: new Date('2023-01-02').getTime(),
          Done: new Date('2023-01-05').getTime(),
        },
      },
    ];

    const result = calculateKpis(
      issues,
      'Implement',
      'Done',
      startDate,
      endDate,
      ['Implement'],
      ['Open']
    );

    expect(result.totalCompleted).toBe(0);
    expect(result.avgThroughput).toBe(0);
  });

  it('should handle missing start or end transitions gracefully', () => {
    const startDate = new Date('2023-01-01').getTime();
    const endDate = new Date('2023-01-10').getTime();

    const issues = [
      {
        // Missing start state
        transitions: {
          Done: new Date('2023-01-05').getTime(),
        },
      },
      {
        // Missing end state
        transitions: {
          Implement: new Date('2023-01-02').getTime(),
        },
      },
      {
        // End before start (invalid)
        transitions: {
          Implement: new Date('2023-01-05').getTime(),
          Done: new Date('2023-01-02').getTime(),
        },
      },
    ];

    const result = calculateKpis(
      issues,
      'Implement',
      'Done',
      startDate,
      endDate,
      ['Implement'],
      ['Open']
    );

    expect(result).toEqual({
      totalCompleted: 0,
      avgCT: 0,
      avgThroughput: 0,
      flowEff: 0,
    });
  });
});
