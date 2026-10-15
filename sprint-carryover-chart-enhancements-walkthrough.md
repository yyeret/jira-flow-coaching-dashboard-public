# Sprint Carryover Chart Enhancements Walkthrough

We have successfully implemented the requested features on the Sprint Predictability & Carryover chart:
1. **Dropdown unit toggle**: Added a select dropdown to switch between **Issue Count** and **Story Points**.
2. **Missing Story Points default**: Set the default estimation value to `1` when summing story points for issues without an estimation.
3. **Statistical reference lines**: Created a custom Chart.js inline plugin to draw:
   - **85% Confidence Level** (15th percentile of completed values)
   - **50% Confidence Level** (median of completed values)
   - **Mean Line** (average of completed values)
4. **Standard Deviation band**: Shaded the region `[mean - stddev, mean + stddev]` in a semi-transparent premium violet color to highlight predictability visually.
5. **Future sprints exclusion**: Excluded any active or future sprint (with a finish date in the future) entirely from both the chart display and statistical calculations.

## Verification

We ran automated browser verification using a Puppeteer script (`test_local_dashboard.js`) against the local sample data, demonstrating:
- The dashboard loaded successfully.
- The Sprint Carryover Chart initialized.
- Toggling the measurement select to `points` dynamically recalculated metrics and correctly labeled the Y-axis as `Story Points`.
- Future-ending sprints are successfully filtered out from rendering.
- No JavaScript console errors were encountered.

### Dashboard Verification Screenshot

Below is the rendered dashboard showing the enhanced Sprint Predictability & Carryover chart with the new dropdown, dynamic reference lines, and shaded standard deviation band.

![Sprint Carryover Chart with Statistical Reference Lines](<local-path>)
