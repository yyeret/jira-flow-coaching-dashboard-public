# Goal Description

The user wants to restructure the Sprint Comet Chart to use a "Tetris" style layout. Instead of using actual Cycle Time for the Y-axis, the chart will assign each item to the lowest available "lane" (or track) based on its start time. This creates a dense, non-overlapping horizontal waterfall view of concurrent work.

## User Review Required

> [!TIP]
> Instead of completely replacing the current Cycle Time view, I propose adding a **Layout dropdown** to the Comet Chart that lets you toggle between `Cycle Time (Log Scale)` and `Tetris (Tracks)`. 
> 
> This way, you can still visualize outliers using the Cycle Time view, while using the Tetris view to understand concurrency and WIP density! Are you okay with adding this as a toggle option?

## Proposed Changes

### `index.html`

- **UI Updates:**
  - Add a `<select id="cometLayoutSelect">` inside the Comet Chart controls area with two options: `cycle_time` and `tetris`.
  - Hook it up to the `setupFilterListeners` to trigger a re-render when changed.

- **Data Processing (`renderSprintCometChart`):**
  - Extract all valid issues into a flat array first.
  - If `tetris` layout is selected, sort the array by `startTime` (ascending).
  - Implement a lane-packing algorithm: maintain an array `lanes` where `lanes[i]` stores the `endTime` of the last item assigned to lane `i`. For each item, find the lowest index `i` where `lanes[i] < startTime`. Assign the item to that lane, and update the lane's end time.
  - Set the `y` coordinate to the assigned lane index.
  - Pass the original `ctDays` inside the data object so the tooltip can still display the actual cycle time.

- **Chart.js Configuration (`renderSprintCometChart`):**
  - Dynamically swap the Y-axis configuration:
    - If `cycle_time`: use `type: 'logarithmic'`, title "Cycle Time (Days, Log Scale)".
    - If `tetris`: use `type: 'linear'`, title "Concurrent Tracks", and configure the grid to hide horizontal lines or format ticks as integers.

## Verification Plan

### Automated Tests
- Run the E2E puppeteer test script to verify that both the `tetris` and `cycle_time` layouts render without throwing JS exceptions.

### Manual Verification
- Visually verify that in Tetris mode, comets do not overlap horizontally and are tightly packed into vertical lanes.
