# Sprint Carryover Chart Enhancements

Add a unit toggle (Issue Count vs. Story Points) to the Sprint Predictability & Carryover chart. Additionally, calculate and overlay statistical reference indicators (85% confidence level, 50% confidence level, mean, and standard deviation band) on the completions data series, with visual highlights.

## User Review Required

> [!NOTE]
> The statistical confidence levels (85% and 50%) are calculated based on historical completed sprint velocity/throughput values shown in the filtered date range.
> - **50% Confidence Level**: The median of completed values (where 50% of sprints achieved at least this velocity).
> - **85% Confidence Level**: The 15th percentile of completed values (where 85% of sprints achieved at least this velocity).
> - **Standard Deviation**: Visually represented as a light shaded horizontal region (`[mean - stddev, mean + stddev]`) overlaying the completions to highlight velocity predictability/variability.

## Open Questions

There are no major open questions. As requested by the user, we will handle issues with missing story point estimations by treating their estimation as `1` when summing points.

## Proposed Changes

### Dashboard Application

---

#### [MODIFY] [index.html](file://<local-path>)

- **Add UI Toggle Dropdown**:
  Add `carryoverUnitSelect` select element inside the Sprint Predictability & Carryover chart panel's header matching the design of other controls.
- **Register Listener**:
  Include `'carryoverUnitSelect'` in the array of filtered elements in `setupFilterListeners()` so that toggling it triggers an immediate dashboard re-render.
- **Update Chart Rendering Logic**:
  - In `renderSprintCarryoverChart(issues, endState, sDate, eDate)`:
    - Update issue iterations to sum both `plannedCount`/`plannedPoints`, `completedCount`/`completedPoints`, and `carryoverCount`/`carryoverPoints`.
    - Retrieve the selected unit value.
    - Calculate `mean`, `stddev`, `50% Confidence (median)`, and `85% Confidence` on the completed series.
    - Construct dynamic Chart.js datasets based on the chosen unit.
    - Implement a custom inline Chart.js plugin to draw the reference lines (Mean, 50% Conf, 85% Conf) and the shaded standard deviation region (`[mean - stddev, mean + stddev]`) with elegant labels.
    - Adjust Y-axis titles dynamically based on the selected unit.

## Verification Plan

### Automated Tests
- We will execute a test script (`test_direct3.js` or a new script designed for local sample data) to verify that all charts render correctly, there are no browser console errors, and the new options can be selected successfully.

### Manual Verification
- Deploy/load `index.html` in a web browser using standard file paths or `npm start` and verify:
  1. The new "Measure By" select dropdown is fully visible and styled correctly on the Sprint Predictability & Carryover panel.
  2. Toggling between "Issue Count" and "Story Points" updates the chart correctly.
  3. The confidence reference lines (85%, 50%), the mean line, and the semi-transparent standard deviation shaded band are rendered properly on top of the completions (green section of the stacked bars) and labeled accurately.
