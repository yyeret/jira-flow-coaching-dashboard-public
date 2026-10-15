# Predictability and Estimation Analysis Spec

## Overview
This document outlines the approach for analyzing flow metrics to determine the predictability of software delivery, specifically focusing on the difference between count-based flow (Throughput) and point-based velocity.

## Required Data Coverage
The analysis requires a Jira export (or equivalent dataset) containing:
- Issue key, summary, issue type
- Created and updated dates
- Current status
- Timestamp columns for workflow states (e.g., `In Progress`, `Code Review`, `In QA`, `Done`)

To conduct an advanced analysis (e.g., evaluating story points vs counting), the export must also include:
- Story Points / Original Estimate
- Sprint name, sprint start/end dates
- Team, board, assignee, and component fields
- Parent/epic hierarchy

## Flow Signals
The dashboard extracts the following signals:
- **Throughput:** How many stories/bugs finish per week/sprint.
- **Cycle Time:** Median, 85th percentile, and 95th percentile times for issues to go from "In Progress" to "Done".
- **Aging WIP:** Which active items are older than normal compared to historical distributions.
- **Flow Debt:** Items that sit in progress for months and distort averages.

## Forecasting Approach
To answer "is it more predictive to count stories or estimate them?", the analysis uses a walk-forward backtest:
1. Pick a prediction unit (e.g., sprint or two-week interval).
2. For each historical interval, pretend only prior intervals are known.
3. Forecast next-interval delivery using:
   - Story count throughput: trailing median/average completed stories.
   - Point velocity: trailing median/average completed story points.
4. Compare forecast errors (Mean Absolute Error, Forecast Interval Coverage).
5. If point velocity reduces forecast error materially, keep estimates. If story counts perform better, reserve estimates for risk discovery only.

## Recommendations
- The dashboard focuses on count-based throughput and cycle-time predictability.
- Highlight old in-progress outliers separately instead of letting them distort averages.
- Establish an 85% Service Level Expectation (SLE) for cycle time based on recent historical data.
