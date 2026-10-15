import {
  escapeHtml,
  renderUntrustedText,
  confirmAiTransfer,
  bindClearSavedData,
} from './security.js';

let geminiApiKey = '';
// Remove keys persisted by earlier versions; keys now live only in this page session.
localStorage.removeItem('geminiApiKey');

import {
  DEFAULT_ARCHIVED_PROJECTS,
  LABEL_STANDARDIZATION_MAP,
  parseDate,
  isDateString,
  getFormalParent,
  classifyCommentSemantic,
  buildFlagHistoryMap,
  parseIssues,
  priorityToCoD,
} from './models.js';

import {
  calculateFlowMetrics as calcFlowMetrics,
  computeCFDData,
  computeWipRunData,
  computeSprintCarryoverData,
} from './metrics.js';

import {
  getCssVar,
  getCategoryColor,
  getSemanticReasonColor,
  copyChartToClipboard,
  addCopyButtons,
} from './charts.js';

// Global app state
let rawData = [];
let parsedIssues = [];
let statusColumns = [];
let rawSprintData = [];
let rawMetadata = [];
let rawLinksData = [];
let rawFlagData = [];
let rawValueAnalysis = [];

let cfdChart = null;
let controlChart = null;
let workItemAgeChart = null;
let throughputChart = null;
let sprintCarryoverChart = null;
let sprintCometChart = null;
let wipRunChart = null;
let estimationChart = null;
let flagReasonChartInstance = null;
let defectTrendChart = null;
let valueCurveChart = null;

const statusColorPalette = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#14b8a6',
  '#f43f5e',
  '#a855f7',
  '#64748b',
  '#65a30d',
  '#0d9488',
  '#ea580c',
  '#475569',
];

window.addEventListener('DOMContentLoaded', async () => {
  bindClearSavedData();
  // Setup file folder listeners
  const folderInput = document.getElementById('folderInput');
  const uploadZone = document.getElementById('uploadZone');

  if (uploadZone && folderInput) {
    uploadZone.addEventListener('dragover', () => {
      uploadZone.style.borderColor = '#60a5fa';
      uploadZone.style.backgroundColor = '#1e2942';
    });

    uploadZone.addEventListener('dragleave', () => {
      uploadZone.style.borderColor = '#3b82f6';
      uploadZone.style.backgroundColor = 'var(--panel-bg)';
    });

    uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadZone.style.borderColor = '#3b82f6';
      uploadZone.style.backgroundColor = 'var(--panel-bg)';
      folderInput.click();
    });
  }

  if (folderInput) {
    folderInput.addEventListener('change', (e) => {
      const files = Array.from(e.target.files);
      const findFile = (exactName, fallbackSubstr) =>
        files.find((f) => f.name === exactName) ||
        files.find((f) => f.name.includes(fallbackSubstr));
      const mainFile = findFile('flow_analytics_export.csv', 'flow_analytics_export.csv');
      const sprintFile = findFile('sprint_data.csv', 'sprint_data.csv');
      const metaFile = findFile('issue_metadata.csv', 'issue_metadata.csv');
      const linkFile = findFile('issue_links.csv', 'issue_links.csv');
      const flagFile = findFile('flag_history.csv', 'flag_history.csv');
      const valueFile = findFile('issue_value_analysis.csv', 'issue_value_analysis.csv');

      if (!mainFile) {
        alert('Could not find a flow analytics export CSV in the selected folder.');
        return;
      }

      let metaPromise = metaFile ? parseLocalCSV(metaFile) : Promise.resolve([]);
      let sprintPromise = sprintFile ? parseLocalCSV(sprintFile) : Promise.resolve([]);
      let linkPromise = linkFile ? parseLocalCSV(linkFile) : Promise.resolve([]);
      let flagPromise = flagFile ? parseLocalCSV(flagFile) : Promise.resolve([]);
      let valuePromise = valueFile ? parseLocalCSV(valueFile) : Promise.resolve([]);
      let mainPromise = parseLocalCSV(mainFile, true);

      Promise.all([metaPromise, sprintPromise, mainPromise, linkPromise, flagPromise, valuePromise])
        .then((results) => {
          const metaData = results[0];
          const sprintData = results[1];
          const mainDataObj = results[2];
          const linksData = results[3];
          const flagData = results[4];
          const valueData = results[5];

          if (typeof localforage !== 'undefined') {
            localforage
              .setItem('cachedDashboardData', {
                metaData,
                sprintData,
                mainDataObj,
                linksData,
                flagData,
                valueData,
              })
              .catch((err) => console.error('Cache set error:', err));
          }

          applyDataToDashboard(metaData, sprintData, mainDataObj, linksData, flagData, valueData);
        })
        .catch((err) => {
          console.error('Error parsing files:', err);
          alert('Error parsing files: ' + err.message);
        });

      e.target.value = '';
    });
  }

  // Load from cache
  try {
    if (typeof localforage !== 'undefined') {
      const cached = await localforage.getItem('cachedDashboardData');
      if (cached && cached.mainDataObj) {
        applyDataToDashboard(
          cached.metaData,
          cached.sprintData,
          cached.mainDataObj,
          cached.linksData || [],
          cached.flagData || [],
          cached.valueData || []
        );
      }
    }
  } catch (err) {
    console.error('Error loading cached data', err);
  }

  // Dynamic print hook binding
  const printBtn = document.querySelector('button[title="Download PDF Report"]');
  if (printBtn) {
    printBtn.removeAttribute('onclick');
    printBtn.addEventListener('click', printReport);
  }

  // AI Settings Modal logic
  const geminiInput = document.getElementById('geminiApiKeyInput');
  const geminiModelSelect = document.getElementById('geminiModelSelect');
  const saveSettingsBtn = document.getElementById('saveApiSettingsBtn');

  if (geminiInput) {
    geminiInput.value = geminiApiKey;
  }
  if (geminiModelSelect) {
    geminiModelSelect.value = localStorage.getItem('geminiModel') || 'gemini-flash-latest';
  }

  if (saveSettingsBtn && geminiInput) {
    saveSettingsBtn.addEventListener('click', () => {
      const key = geminiInput.value.trim();
      const model = geminiModelSelect ? geminiModelSelect.value : 'gemini-flash-latest';
      geminiApiKey = key;
      geminiInput.value = '';
      localStorage.setItem('geminiModel', model);
      document.getElementById('apiSettingsModal').style.display = 'none';
      alert('Gemini API settings saved for this page session. The key is cleared when you reload.');
    });
  }
});

function parseLocalCSV(file, returnFullObj = false) {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: function (results) {
        if (returnFullObj) {
          resolve(results);
        } else {
          resolve(results.data);
        }
      },
      error: reject,
    });
  });
}

function applyDataToDashboard(
  metaData,
  sprintData,
  mainDataObj,
  linksData = [],
  flagData = [],
  valueData = []
) {
  try {
    rawMetadata = metaData;
    rawSprintData = sprintData;
    rawLinksData = linksData;
    rawFlagData = flagData;
    rawValueAnalysis = valueData;
    rawData = mainDataObj.data;
    processRawData(mainDataObj.meta.fields);

    const uploadZone = document.getElementById('uploadZone');
    const container = document.getElementById('dashboardContainer');
    if (uploadZone) uploadZone.style.display = 'none';
    if (container) container.style.display = 'grid';
  } catch (err) {
    console.error('Error applying data:', err.stack);
    alert('Error applying data: ' + err.message);
  }
}

function processRawData(fields) {
  const fixedHeaders = [
    'Issue Key',
    'Summary',
    'Issue Type',
    'Created Date',
    'Updated Date',
    'Current Status',
    'Story Points',
    'Story point estimate',
    'Estimation',
    'Labels',
    'Unplanned',
    'Priority',
    'Assignee',
    'Reporter',
    'Epic Link',
    'Components',
    'Sprint',
    'Sprints',
    'Sprint ID',
    'Sprint Name',
    'Sprint State',
    'Start Date',
    'End Date',
    'Complete Date',
  ];

  const activeFields =
    fields && fields.length > 0 ? fields : rawData.length > 0 ? Object.keys(rawData[0]) : [];

  const workflowOrder = [
    'Open',
    'To Do',
    'Specify/Plan',
    'Ready to Implement',
    'Next',
    'Implement',
    'Code Review',
    'Ready for Testing',
    'test and fix',
    'Ready for release',
    'Monitor/Adapt/Learn',
    'Done',
  ];

  statusColumns = activeFields
    .filter((f) => !fixedHeaders.includes(f))
    .filter((f) => {
      if (workflowOrder.includes(f)) return true;

      let hasDate = false;
      let hasInvalid = false;
      for (let i = 0; i < rawData.length; i++) {
        const val = rawData[i][f];
        if (val !== undefined && val !== null && val.trim() !== '') {
          if (isDateString(val)) {
            hasDate = true;
          } else {
            hasInvalid = true;
            break;
          }
        }
      }
      return hasDate && !hasInvalid;
    })
    .sort((a, b) => {
      let indexA = workflowOrder.indexOf(a);
      let indexB = workflowOrder.indexOf(b);
      return indexA - indexB;
    });

  const metaMap = {};
  rawMetadata.forEach((m) => {
    if (m['Issue Key']) metaMap[m['Issue Key']] = m;
  });

  const sprintMap = {};
  rawSprintData.forEach((s) => {
    if (!s['Issue Key']) return;
    if (!sprintMap[s['Issue Key']]) sprintMap[s['Issue Key']] = [];
    sprintMap[s['Issue Key']].push(s);
  });

  const flagHistoryMap = buildFlagHistoryMap(rawFlagData);

  parsedIssues = parseIssues(rawData, statusColumns, metaMap, sprintMap, flagHistoryMap);

  const valueMap = {};
  rawValueAnalysis.forEach((v) => {
    if (v['Issue Key']) valueMap[v['Issue Key']] = v;
  });
  parsedIssues.forEach((issue) => {
    const valRow = valueMap[issue.key];
    issue.taxonomy_level = valRow ? valRow['Taxonomy Level'] : 'Unclassified';
    issue.suggested_outcome_framing = valRow ? valRow['Suggested Outcome Framing'] : '';
    issue.rationale = valRow ? valRow['Rationale'] : '';
  });

  populateFilterOptions();
  setDefaultDates();
  setupFilterListeners();
  updateDashboard();
}

function populateFilterOptions() {
  const projects = [
    ...new Set(rawData.map((r) => (r['Issue Key'] ? r['Issue Key'].split('-')[0] : ''))),
  ].filter(Boolean);
  const projFilter = document.getElementById('projFilter');
  if (projFilter) {
    projFilter.innerHTML = '<option value="All">All Projects</option>';
    projects.forEach((p) => {
      projFilter.innerHTML += `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`;
    });
    projFilter.value = 'All';
  }

  const types = [...new Set(rawData.map((r) => r['Issue Type']))].filter(Boolean).sort();
  const typeChecklist = document.getElementById('typeChecklist');
  const typeFilter = document.getElementById('typeFilter');

  if (typeChecklist) {
    typeChecklist.innerHTML = '';
    types.forEach((t) => {
      const item = document.createElement('label');
      item.className = 'state-item';

      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.value = t;
      chk.checked = true;
      chk.className = 'type-chk';
      chk.addEventListener('change', updateDashboard);

      const txt = document.createElement('span');
      txt.textContent = t;

      item.appendChild(chk);
      item.appendChild(txt);
      typeChecklist.appendChild(item);
    });
  }

  if (typeFilter) {
    typeFilter.innerHTML = '<option value="All">All Types</option>';
    types.forEach((t) => {
      typeFilter.innerHTML += `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`;
    });
  }

  const toggleAllTypesBtn = document.getElementById('toggleAllTypesBtn');
  if (toggleAllTypesBtn && !toggleAllTypesBtn._hasListener) {
    toggleAllTypesBtn._hasListener = true;
    toggleAllTypesBtn.addEventListener('click', () => {
      const chks = document.querySelectorAll('.type-chk');
      const allChecked = Array.from(chks).every((c) => c.checked);
      chks.forEach((c) => (c.checked = !allChecked));
      updateDashboard();
    });
  }

  const allLabels = new Set();
  parsedIssues.forEach((issue) => {
    if (issue.labels) {
      issue.labels.forEach((l) => {
        if (l) allLabels.add(l);
      });
    }
  });
  const labelFilter = document.getElementById('labelFilter');
  if (labelFilter) {
    labelFilter.innerHTML = '<option value="All">All Labels</option>';
    Array.from(allLabels)
      .sort()
      .forEach((l) => {
        labelFilter.innerHTML += `<option value="${escapeHtml(l)}">${escapeHtml(l)}</option>`;
      });
  }

  const allResolutions = new Set();
  parsedIssues.forEach((issue) => {
    if (issue.resolution) allResolutions.add(issue.resolution);
  });
  const resolutionFilter = document.getElementById('resolutionFilter');
  if (resolutionFilter) {
    resolutionFilter.innerHTML = '<option value="All">All Resolutions</option>';
    Array.from(allResolutions)
      .sort()
      .forEach((r) => {
        resolutionFilter.innerHTML += `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`;
      });
  }

  const allEpics = new Set();
  parsedIssues.forEach((issue) => {
    if (issue.epicLink) allEpics.add(issue.epicLink);
  });
  const epicFilter = document.getElementById('epicFilter');
  if (epicFilter) {
    epicFilter.innerHTML = '<option value="All">All Epics</option>';
    Array.from(allEpics)
      .sort()
      .forEach((e) => {
        epicFilter.innerHTML += `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`;
      });
  }

  const startTimeSelect = document.getElementById('cycleStartTimeState');
  const endTimeSelect = document.getElementById('cycleEndTimeState');

  // Pick smart default start and end states based on what's available
  const startStateCandidates = ['Implement', 'In Progress', 'In Dev', 'Dev', 'Active'];
  const defaultStart =
    startStateCandidates.find((s) => statusColumns.includes(s)) || statusColumns[0];

  const endStateCandidates = ['Done', 'Closed', 'Complete', 'Resolved', 'Released'];
  const defaultEnd =
    endStateCandidates.find((s) => statusColumns.includes(s)) ||
    statusColumns[statusColumns.length - 1];

  if (startTimeSelect && endTimeSelect) {
    startTimeSelect.innerHTML = '';
    endTimeSelect.innerHTML = '';
    statusColumns.forEach((state) => {
      const startSelected = state === defaultStart ? 'selected' : '';
      const endSelected = state === defaultEnd ? 'selected' : '';
      startTimeSelect.innerHTML += `<option value="${escapeHtml(state)}" ${startSelected}>${escapeHtml(state)}</option>`;
      endTimeSelect.innerHTML += `<option value="${escapeHtml(state)}" ${endSelected}>${escapeHtml(state)}</option>`;
    });
  }

  // Determine which status columns actually have at least one transition in the dataset
  const activeStatuses = new Set();
  parsedIssues.forEach((issue) => {
    if (issue.transitions) {
      Object.keys(issue.transitions).forEach((state) => {
        activeStatuses.add(state);
      });
    }
  });

  const checklist = document.getElementById('cfdStatesChecklist');
  if (checklist) {
    checklist.innerHTML = '';
    statusColumns.forEach((state) => {
      // Remove empty/unused columns from the checklist entirely
      if (!activeStatuses.has(state)) return;

      const isChecked = ![
        'Open',
        'To Do',
        'Tabled',
        'Deferred',
        'Product Backlog',
        'Backlog',
        'Selected for Development',
      ].includes(state);
      checklist.innerHTML += `
                <label class="state-item">
                    <input type="checkbox" value="${escapeHtml(state)}" ${isChecked ? 'checked' : ''} class="cfd-state-chk">
                    <span>${escapeHtml(state)}</span>
                </label>
            `;
    });
  }
}

function setDefaultDates() {
  if (parsedIssues.length === 0) return;

  let earliest = new Date();
  let latest = new Date(0);

  parsedIssues.forEach((issue) => {
    if (issue.created && issue.created < earliest) earliest = issue.created;
    if (issue.created && issue.created > latest) latest = issue.created;
    if (issue.updated && issue.updated > latest) latest = issue.updated;
  });

  // Default to the last 90 days ending at the latest update/creation in the dataset
  const end = new Date(latest);
  const start = new Date(latest);
  start.setDate(start.getDate() - 90);

  if (start < earliest) {
    start.setTime(earliest.getTime());
  }

  const sEl = document.getElementById('startDateFilter');
  const eEl = document.getElementById('endDateFilter');
  if (sEl) sEl.value = start.toISOString().split('T')[0];
  if (eEl) eEl.value = end.toISOString().split('T')[0];
}

function setupFilterListeners() {
  const inputs = [
    'projFilter',
    'typeFilter',
    'labelFilter',
    'resolutionFilter',
    'startDateFilter',
    'endDateFilter',
    'cycleStartTimeState',
    'cycleEndTimeState',
    'colorBySelect',
    'throughputColorBySelect',
    'throughputTimebucketSelect',
    'cometSizeSelect',
    'cometLayoutSelect',
    'unplannedFilter',
    'carryoverUnitSelect',
    'epicFilter',
  ];
  inputs.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', updateDashboard);
  });

  document.querySelectorAll('.cfd-state-chk').forEach((chk) => {
    chk.addEventListener('change', updateDashboard);
  });
}

function updateDashboard() {
  if (parsedIssues.length === 0) return;

  const proj = document.getElementById('projFilter').value;
  const selectedTypeCheckboxes = document.querySelectorAll('.type-chk:checked');
  const selectedTypes = Array.from(selectedTypeCheckboxes).map((c) => c.value);
  const typeFilterEl = document.getElementById('typeFilter');
  const typeSelectVal = typeFilterEl ? typeFilterEl.value : 'All';

  const startStr = document.getElementById('startDateFilter').value;
  const endStr = document.getElementById('endDateFilter').value;

  const startDate = startStr ? new Date(startStr) : new Date(0);
  const endDate = endStr ? new Date(endStr) : new Date();
  endDate.setHours(23, 59, 59, 999);

  const startState = document.getElementById('cycleStartTimeState').value;
  const endState = document.getElementById('cycleEndTimeState').value;

  const filteredIssues = parsedIssues.filter((issue) => {
    const issueProj = issue.key.split('-')[0];
    if (proj !== 'All' && issueProj !== proj) return false;

    if (selectedTypeCheckboxes.length > 0) {
      if (!selectedTypes.includes(issue.type)) return false;
    } else if (typeSelectVal !== 'All' && issue.type !== typeSelectVal) {
      return false;
    }

    const selectedLabel = document.getElementById('labelFilter').value;
    if (selectedLabel !== 'All' && !issue.labels.includes(selectedLabel)) return false;

    const selectedResolution = document.getElementById('resolutionFilter')
      ? document.getElementById('resolutionFilter').value
      : 'All';
    if (selectedResolution !== 'All' && issue.resolution !== selectedResolution) return false;

    const selectedUnplanned = document.getElementById('unplannedFilter')
      ? document.getElementById('unplannedFilter').value
      : 'All';
    if (selectedUnplanned !== 'All' && issue.unplanned !== selectedUnplanned) return false;

    const selectedEpic = document.getElementById('epicFilter')
      ? document.getElementById('epicFilter').value
      : 'All';
    if (selectedEpic !== 'All' && issue.epicLink !== selectedEpic) return false;

    let matchesDate = false;
    if (issue.created >= startDate && issue.created <= endDate) {
      matchesDate = true;
    } else if (issue.updated && issue.updated >= startDate && issue.updated <= endDate) {
      matchesDate = true;
    } else if (issue.transitions) {
      for (const status in issue.transitions) {
        const tTime = issue.transitions[status];
        if (tTime && tTime >= startDate && tTime <= endDate) {
          matchesDate = true;
          break;
        }
      }
    }
    return matchesDate;
  });

  // Run Calculations & Render UIs
  updateKpis(filteredIssues, startState, endState, startDate, endDate);
  renderCFD(filteredIssues, startDate, endDate, startState, endState);
  renderWIP(filteredIssues, startDate, endDate);
  renderControl(filteredIssues, startState, endState, startDate);
  renderEstimation(filteredIssues, startState, endState);
  renderWorkItemAge(filteredIssues, startState, endState);

  const sprintIssues = parsedIssues.filter((issue) => {
    const issueProj = issue.key.split('-')[0];
    if (proj !== 'All' && issueProj !== proj) return false;
    if (selectedTypeCheckboxes.length > 0) {
      if (!selectedTypes.includes(issue.type)) return false;
    } else if (typeSelectVal !== 'All' && issue.type !== typeSelectVal) {
      return false;
    }
    const selectedLabel = document.getElementById('labelFilter').value;
    if (selectedLabel !== 'All' && !issue.labels.includes(selectedLabel)) return false;
    const selectedResolution = document.getElementById('resolutionFilter')
      ? document.getElementById('resolutionFilter').value
      : 'All';
    if (selectedResolution !== 'All' && issue.resolution !== selectedResolution) return false;
    const selectedUnplanned = document.getElementById('unplannedFilter')
      ? document.getElementById('unplannedFilter').value
      : 'All';
    if (selectedUnplanned !== 'All' && issue.unplanned !== selectedUnplanned) return false;
    return true;
  });

  renderSprintComet(sprintIssues, startState, endState, startDate);
  renderThroughput(filteredIssues, endState, startDate, endDate);
  renderDefectTrend(filteredIssues, startDate, endDate);
  renderValueCurve(filteredIssues, endState, startDate, endDate);
  renderSprintCarryover(sprintIssues, endState, startDate, endDate);
  renderDependency(filteredIssues, startState, endState);
  renderCoachingInsights(filteredIssues, sprintIssues, startState, endState);
  renderDataTable(filteredIssues, startState, endState);

  // Attach copy actions
  addCopyButtons();
}

function updateKpis(issues, startState, endState, startDate, endDate) {
  const stats = calcFlowMetrics(issues, startState, endState, startDate, endDate);

  document.getElementById('kpiCompleted').innerText = stats.completedCount;
  document.getElementById('kpiAvgCt').innerText =
    stats.completedCount > 0 ? `${stats.avgCt.toFixed(1)}d` : '-';
  document.getElementById('kpiP50').innerText =
    stats.completedCount > 0 ? `${stats.p50.toFixed(1)}d` : '-';
  document.getElementById('kpiP85').innerText =
    stats.completedCount > 0 ? `${stats.p85.toFixed(1)}d` : '-';
  document.getElementById('kpiWip').innerText = stats.activeWipCount;
}

function renderCFD(issues, startDate, endDate, startState, endState) {
  const chkStates = Array.from(document.querySelectorAll('.cfd-state-chk:checked')).map(
    (chk) => chk.value
  );
  const { daySteps, cfdData, wipArray, approxCtArray } = computeCFDData(
    issues,
    statusColumns,
    chkStates,
    startDate,
    endDate,
    endState
  );

  const datasets = chkStates
    .map((state, i) => ({
      label: state,
      data: cfdData[state],
      borderColor: statusColorPalette[i % statusColorPalette.length],
      backgroundColor: statusColorPalette[i % statusColorPalette.length] + 'b0',
      fill: true,
      tension: 0.1,
      pointRadius: 0,
    }))
    .reverse();

  if (cfdChart) cfdChart.destroy();

  const ctx = document.getElementById('cfdChartCanvas').getContext('2d');
  cfdChart = new Chart(ctx, {
    type: 'line',
    data: { labels: daySteps, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'time',
          time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd', displayFormats: { day: 'MMM dd' } },
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
        },
        y: {
          stacked: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: { display: true, text: 'Issue Count', color: getCssVar('--text-muted') },
        },
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: getCssVar('--text-color') } },
        tooltip: {
          mode: 'index',
          intersect: false,
          itemSort: (a, b) => b.datasetIndex - a.datasetIndex,
          callbacks: {
            afterBody: (tooltipItems) => {
              if (!tooltipItems || tooltipItems.length === 0) return '';
              const dayIdx = tooltipItems[0].dataIndex;
              return `\nEnd-to-End WIP: ${wipArray[dayIdx]}\nApprox Avg Cycle Time: ${approxCtArray[dayIdx].toFixed(1)}d`;
            },
          },
        },
      },
    },
  });
}

function renderWIP(issues, filterStartDate, filterEndDate) {
  const selectedStates = Array.from(document.querySelectorAll('.cfd-state-chk:checked'))
    .map((chk) => chk.value)
    .filter((s) => s !== 'Done');
  const { daySteps, datasetsData } = computeWipRunData(
    issues,
    statusColumns,
    selectedStates,
    filterStartDate,
    filterEndDate
  );

  const datasets = selectedStates
    .map((state, i) => {
      const c = statusColorPalette[i % statusColorPalette.length];
      return {
        label: state,
        data: datasetsData[state],
        backgroundColor: c,
        borderColor: c,
        borderWidth: 1,
      };
    })
    .reverse();

  if (wipRunChart) wipRunChart.destroy();

  const ctx = document.getElementById('wipRunChartCanvas').getContext('2d');
  wipRunChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: daySteps, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'time',
          stacked: true,
          time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd', displayFormats: { day: 'MMM dd' } },
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-color') },
        },
        y: {
          stacked: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-color') },
          title: { display: true, text: 'WIP Count', color: getCssVar('--text-color') },
          min: 0,
        },
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: getCssVar('--text-color') } },
      },
    },
  });
}

function renderControl(issues, startState, endState, filterStartDate) {
  const colorBy = document.getElementById('colorBySelect').value;
  const groups = {};
  const cycleTimes = [];

  const startFilterVal = new Date(document.getElementById('startDateFilter').value);
  const endFilterVal = new Date(document.getElementById('endDateFilter').value);
  endFilterVal.setHours(23, 59, 59, 999);

  issues.forEach((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];

    if (startTime && endTime && endTime >= startTime) {
      if (endTime < startFilterVal || endTime > endFilterVal) return;
      const ctDays = Math.max(0.5, (endTime - startTime) / 86400000);
      cycleTimes.push(ctDays);

      let category = 'None';
      if (colorBy === 'type') category = issue.type || 'None';
      else if (colorBy === 'label')
        category = issue.labels && issue.labels.length > 0 ? issue.labels[0] : 'None';
      else if (colorBy === 'unplanned') category = issue.unplanned || 'Unknown';
      else if (colorBy === 'resolution') category = issue.resolution || 'Unresolved';
      else if (colorBy === 'workclass') category = issue.workClass || 'Value';

      if (!groups[category]) groups[category] = [];
      groups[category].push({
        x: endTime,
        y: ctDays,
        key: issue.key,
        summary: issue.summary,
        type: issue.type,
        labels: (issue.labels || []).join(', '),
      });
    }
  });

  const percentileOf = (arr, p) => {
    if (!arr.length) return 0;
    const sorted = [...arr].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))];
  };

  if (controlChart) controlChart.destroy();

  const ctx = document.getElementById('controlChartCanvas').getContext('2d');
  const datasets = [];
  let colorIdx = 0;

  Object.keys(groups)
    .sort()
    .forEach((cat) => {
      const colors = getCategoryColor(cat, colorIdx, false);
      let bgColor = colors.bg;
      let borderColor = colors.border;
      colorIdx++;

      const pts = groups[cat];
      datasets.push({
        label: cat,
        data: pts,
        backgroundColor: bgColor,
        borderColor: borderColor,
        borderWidth: 1,
        pointRadius: 6,
        pointHoverRadius: 9,
        type: 'scatter',
      });

      const cts = pts.map((p) => p.y);
      if (cts.length > 0) {
        const cP50 = percentileOf(cts, 0.5);
        const cP85 = percentileOf(cts, 0.85);
        const linePrefix = Object.keys(groups).length > 1 ? `${cat} — ` : '';

        datasets.push({
          label: `${linePrefix}50% (${cP50.toFixed(1)}d)`,
          data: [
            { x: startFilterVal, y: cP50 },
            { x: endFilterVal, y: cP50 },
          ],
          borderColor: borderColor,
          borderWidth: 1.5,
          borderDash: [2, 3],
          fill: false,
          pointRadius: 0,
          type: 'line',
        });

        datasets.push({
          label: `${linePrefix}85% SLE (${cP85.toFixed(1)}d)`,
          data: [
            { x: startFilterVal, y: cP85 },
            { x: endFilterVal, y: cP85 },
          ],
          borderColor: borderColor,
          borderWidth: 2.5,
          borderDash: [9, 4],
          fill: false,
          pointRadius: 0,
          type: 'line',
        });
      }
    });

  controlChart = new Chart(ctx, {
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'time',
          min: filterStartDate ? filterStartDate.getTime() : undefined,
          time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd', displayFormats: { day: 'MMM dd' } },
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: { display: true, text: 'Completion Date', color: getCssVar('--text-muted') },
        },
        y: {
          type: 'logarithmic',
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text: 'Cycle Time (Days, Log Scale)',
            color: getCssVar('--text-muted'),
          },
          min: 0.5,
        },
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: getCssVar('--text-color'), usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label: function (c) {
              const pt = c.raw;
              if (c.dataset.type === 'line') return c.dataset.label;
              return `[${pt.key}] ${pt.summary} | CT: ${pt.y.toFixed(1)}d | L: ${pt.labels}`;
            },
          },
        },
      },
    },
  });
}

function renderEstimation(issues, startState, endState) {
  const dataPoints = [];
  issues.forEach((issue) => {
    if (issue.estimation !== null && !isNaN(issue.estimation)) {
      const startTime = issue.transitions[startState];
      const endTime = issue.transitions[endState];
      if (startTime && endTime && endTime >= startTime) {
        const ctDays = Math.max(0.5, (endTime - startTime) / 86400000);
        dataPoints.push({
          x: issue.estimation,
          y: ctDays,
          key: issue.key,
          summary: issue.summary,
          type: issue.type,
        });
      }
    }
  });

  if (estimationChart) estimationChart.destroy();

  const canvas = document.getElementById('estimationChartCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let correlationText = 'Correlation: N/A';
  if (dataPoints.length > 1) {
    const n = dataPoints.length;
    let sumX = 0,
      sumY = 0,
      sumXY = 0,
      sumX2 = 0,
      sumY2 = 0;
    dataPoints.forEach((p) => {
      sumX += p.x;
      sumY += p.y;
      sumXY += p.x * p.y;
      sumX2 += p.x * p.x;
      sumY2 += p.y * p.y;
    });
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
    if (denominator !== 0 && !isNaN(denominator)) {
      const r = (n * sumXY - sumX * sumY) / denominator;
      const r2 = r * r;
      const confidence = (r2 * 100).toFixed(1);

      let strength = 'None';
      if (r2 >= 0.5) strength = 'Strong';
      else if (r2 >= 0.25) strength = 'Moderate';
      else if (r2 >= 0.1) strength = 'Weak';

      correlationText = `Estimation Confidence (R²): ${confidence}% (${strength} Predictability)`;
    } else {
      correlationText = 'Estimation Confidence: Insufficient variance';
    }
  }

  const correlationPlugin = {
    id: 'correlationText',
    afterDraw: (chart) => {
      const c = chart.ctx;
      c.save();
      c.font = '600 12px "Outfit", sans-serif';
      c.textAlign = 'right';
      c.textBaseline = 'bottom';

      const xPos = chart.chartArea.right - 10;
      const yPos = chart.chartArea.bottom - 10;

      const textWidth = c.measureText(correlationText).width;
      c.fillStyle =
        getComputedStyle(document.body).getPropertyValue('--panel-bg').trim() || '#ffffff';
      c.globalAlpha = 0.85;
      c.fillRect(xPos - textWidth - 10, yPos - 18, textWidth + 20, 24);

      c.globalAlpha = 1.0;
      c.fillStyle =
        getComputedStyle(document.body).getPropertyValue('--text-color').trim() || '#111827';
      c.fillText(correlationText, xPos, yPos + 2);
      c.restore();
    },
  };

  estimationChart = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: 'Completed Items',
          data: dataPoints,
          backgroundColor: 'rgba(59, 130, 246, 0.6)',
          borderColor: 'rgba(59, 130, 246, 1)',
          pointRadius: 5,
          pointHoverRadius: 7,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text: 'Estimation (Story Points)',
            color: getCssVar('--text-muted'),
          },
          min: 0,
        },
        y: {
          type: 'logarithmic',
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text: 'Actual Cycle Time (Days, Log Scale)',
            color: getCssVar('--text-muted'),
          },
          min: 0.5,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (c) {
              const pt = c.raw;
              return `[${pt.key}] ${pt.summary} | Est: ${pt.x} | CT: ${pt.y.toFixed(1)}d`;
            },
          },
        },
      },
    },
    plugins: [correlationPlugin],
  });

  const tableContainer = document.getElementById('estimationConfidenceTable');
  if (tableContainer && dataPoints.length > 0) {
    const pointRatios = dataPoints
      .filter((p) => p.x > 0)
      .map((p) => p.y / p.x)
      .sort((a, b) => a - b);
    let overallRatioStr = 'N/A';
    if (pointRatios.length > 0) {
      overallRatioStr = pointRatios[Math.floor(pointRatios.length * 0.85)].toFixed(1);
    }

    const pointBuckets = {};
    dataPoints.forEach((p) => {
      if (!pointBuckets[p.x]) pointBuckets[p.x] = [];
      pointBuckets[p.x].push(p.y);
    });

    const fibs = [1, 2, 3, 5, 8, 13, 20];
    const activeBuckets = Object.keys(pointBuckets)
      .map(Number)
      .sort((a, b) => a - b);
    const bucketsToShow = Array.from(
      new Set([...fibs.filter((f) => pointBuckets[f]), ...activeBuckets])
    ).sort((a, b) => a - b);

    if (bucketsToShow.length > 0) {
      let tableHtml = `
            <div style="background: var(--panel-hover); padding: 1rem; border-radius: 8px; border: 1px solid var(--panel-border);">
                <h4 style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem;">Estimation Translation & Confidence</h4>
                <p style="font-size: 0.9rem; margin-bottom: 1rem; color: var(--text-color);">
                    <strong>Overall Rule of Thumb:</strong> Within an 85% confidence level, 1 story point translates to roughly <strong>${overallRatioStr} days</strong> of cycle time.
                </p>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--panel-border); color: var(--text-muted);">
                                <th style="padding: 0.5rem;">Story Points</th>
                                <th style="padding: 0.5rem;">Item Count</th>
                                <th style="padding: 0.5rem;">85% Confidence Cycle Time</th>
                                <th style="padding: 0.5rem;">Implied Days/Point</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

      bucketsToShow.forEach((sp) => {
        const ages = pointBuckets[sp];
        if (!ages || ages.length === 0) return;
        ages.sort((a, b) => a - b);
        const p85 = ages[Math.floor(ages.length * 0.85)];
        const ratio = sp > 0 ? (p85 / sp).toFixed(1) : 'N/A';
        tableHtml += `
                            <tr style="border-bottom: 1px solid var(--panel-border); color: var(--text-color);">
                                <td style="padding: 0.5rem;"><strong>${sp}</strong></td>
                                <td style="padding: 0.5rem;">${ages.length}</td>
                                <td style="padding: 0.5rem;"><strong>${p85.toFixed(1)} days</strong></td>
                                <td style="padding: 0.5rem;">${ratio} days/pt</td>
                            </tr>
                `;
      });

      tableHtml += `
                        </tbody>
                    </table>
                </div>
            </div>`;
      tableContainer.innerHTML = tableHtml;
    } else {
      tableContainer.innerHTML = '';
    }
  } else if (tableContainer) {
    tableContainer.innerHTML = '';
  }
}

function renderWorkItemAge(issues, startState, endState) {
  const activeStages = Array.from(document.querySelectorAll('.cfd-state-chk:checked')).map(
    (chk) => chk.value
  );
  const stages = activeStages.filter((s) => s !== endState);

  const stagePercentiles = {};
  stages.forEach((stage) => {
    const ages = [];
    issues.forEach((issue) => {
      const startTime = issue.transitions[startState];
      if (!startTime) return;
      if (!issue.transitions[stage]) return;

      let exitTime = null;
      const searchStages = activeStages.slice(activeStages.indexOf(stage) + 1);
      if (!searchStages.includes(endState)) searchStages.push(endState);

      for (let s of searchStages) {
        if (issue.transitions[s]) {
          if (!exitTime || issue.transitions[s] < exitTime) {
            exitTime = issue.transitions[s];
          }
        }
      }

      if (exitTime && exitTime >= startTime) {
        ages.push((exitTime - startTime) / 86400000);
      }
    });

    let p50 = 0,
      p70 = 0,
      p85 = 0,
      p95 = 0;
    if (ages.length > 0) {
      const sorted = [...ages].sort((a, b) => a - b);
      p50 = sorted[Math.floor(sorted.length * 0.5)];
      p70 = sorted[Math.floor(sorted.length * 0.7)];
      p85 = sorted[Math.floor(sorted.length * 0.85)];
      p95 = sorted[Math.floor(sorted.length * 0.95)];
    }
    stagePercentiles[stage] = { p50, p70, p85, p95 };
  });

  const scatterData = [];
  issues.forEach((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];

    if (startTime && !endTime) {
      const endStr = document.getElementById('endDateFilter')?.value;
      const today = endStr ? new Date(endStr) : new Date();
      if (endStr) today.setHours(23, 59, 59, 999);
      const trueAgeDays = Math.max(0, (today - startTime) / 86400000);
      const ageDays = Math.max(0.5, trueAgeDays);

      let currentStatus = issue.currentStatus;
      if (!stages.includes(currentStatus)) return;

      const p85 =
        stagePercentiles[currentStatus] && stagePercentiles[currentStatus].p85
          ? Math.max(1, stagePercentiles[currentStatus].p85)
          : 1;
      const slePenetration = (trueAgeDays / p85) * 100;

      const timeInColumnDays = issue.transitions[currentStatus]
        ? Math.max(0, (today - issue.transitions[currentStatus]) / 86400000)
        : trueAgeDays;

      scatterData.push({
        x: currentStatus,
        y: ageDays,
        trueAge: trueAgeDays,
        key: issue.key,
        summary: issue.summary,
        type: issue.type,
        timeInColumn: timeInColumnDays,
        p85: p85,
        slePenetration: slePenetration,
      });
    }
  });

  if (workItemAgeChart) workItemAgeChart.destroy();

  const bgPlugin = {
    id: 'agePercentileBands',
    beforeDraw: (chart) => {
      const ctx = chart.canvas.getContext('2d');
      const yAxis = chart.scales.y;
      const chartArea = chart.chartArea;
      ctx.save();

      const colWidth = chartArea.width / stages.length;
      const yBot0 = yAxis.bottom;
      const yTopMax = yAxis.top;

      stages.forEach((stage, i) => {
        const left = chartArea.left + i * colWidth;
        const pData = stagePercentiles[stage] || { p50: 0, p70: 0, p85: 0, p95: 0 };

        let y50 = yAxis.getPixelForValue(pData.p50);
        let y70 = yAxis.getPixelForValue(pData.p70);
        let y85 = yAxis.getPixelForValue(pData.p85);
        let y95 = yAxis.getPixelForValue(pData.p95);

        y50 = Math.max(yTopMax, Math.min(yBot0, y50));
        y70 = Math.max(yTopMax, Math.min(yBot0, y70));
        y85 = Math.max(yTopMax, Math.min(yBot0, y85));
        y95 = Math.max(yTopMax, Math.min(yBot0, y95));

        ctx.fillStyle = 'rgba(16, 185, 129, 0.1)';
        ctx.fillRect(left, y50, colWidth, yBot0 - y50);

        ctx.fillStyle = 'rgba(250, 204, 21, 0.1)';
        ctx.fillRect(left, y70, colWidth, y50 - y70);

        ctx.fillStyle = 'rgba(245, 158, 11, 0.15)';
        ctx.fillRect(left, y85, colWidth, y70 - y85);

        ctx.fillStyle = 'rgba(239, 68, 68, 0.15)';
        ctx.fillRect(left, y95, colWidth, y85 - y95);

        ctx.fillStyle = 'rgba(185, 28, 28, 0.2)';
        ctx.fillRect(left, yTopMax, colWidth, y95 - yTopMax);
      });
      ctx.restore();
    },
  };

  const ctx = document.getElementById('workItemAgeChartCanvas').getContext('2d');
  workItemAgeChart = new Chart(ctx, {
    type: 'scatter',
    data: {
      labels: stages,
      datasets: [
        {
          label: 'Active WIP Age',
          data: scatterData,
          backgroundColor: function (context) {
            const item = context.raw;
            if (!item) return 'rgba(16, 185, 129, 0.9)';
            const pData = stagePercentiles[item.x];
            if (!pData) return 'rgba(16, 185, 129, 0.9)';

            if (item.y > pData.p85) return 'rgba(239, 68, 68, 0.9)';
            if (item.y > pData.p70) return 'rgba(245, 158, 11, 0.9)';
            if (item.y > pData.p50) return 'rgba(250, 204, 21, 0.9)';
            return 'rgba(16, 185, 129, 0.9)';
          },
          borderColor: getCssVar('--panel-bg'),
          borderWidth: 2,
          pointRadius: 7,
          pointHoverRadius: 10,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'category',
          labels: stages,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: { display: true, text: 'Workflow Stage', color: getCssVar('--text-muted') },
        },
        y: {
          type: 'logarithmic',
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: { display: true, text: 'Age (Days, Log Scale)', color: getCssVar('--text-muted') },
          min: 0.5,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `[${c.raw.key}] ${c.raw.y.toFixed(1)} days - ${c.raw.summary}`,
          },
        },
      },
    },
    plugins: [bgPlugin],
  });

  const listContainer = document.getElementById('worryingCardsList');
  if (listContainer) {
    const worryingCards = scatterData
      .filter((item) => item.slePenetration >= 85)
      .sort((a, b) => b.slePenetration - a.slePenetration);

    if (worryingCards.length > 0) {
      let html = `
                <h4 style="margin-bottom: 0.5rem; font-size: 0.95rem; font-weight: 600; color: var(--danger-color);">Most Worrying Active Cards (Approaching or Exceeding SLE)</h4>
                <div class="table-wrapper" style="max-height: 250px; overflow-y: auto; margin-top: 0; border: 1px solid var(--panel-border); border-radius: 8px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                        <thead>
                            <tr>
                                <th style="padding: 0.5rem; text-align: left; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">Key</th>
                                <th style="padding: 0.5rem; text-align: left; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">Summary</th>
                                <th style="padding: 0.5rem; text-align: left; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">Current Stage</th>
                                <th style="padding: 0.5rem; text-align: right; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">SLE (85%)</th>
                                <th style="padding: 0.5rem; text-align: right; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">Total Age</th>
                                <th style="padding: 0.5rem; text-align: right; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">Time in Column</th>
                                <th style="padding: 0.5rem; text-align: right; background: var(--table-header-bg); border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 1;">SLE Penetration</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

      worryingCards.forEach((card) => {
        let penColor = 'var(--text-color)';
        if (card.slePenetration >= 100) penColor = 'var(--danger-color)';
        else penColor = 'var(--warning-color)';

        html += `
                    <tr style="border-bottom: 1px solid var(--table-border);">
                        <td style="padding: 0.5rem;"><strong>${escapeHtml(card.key)}</strong></td>
                        <td style="padding: 0.5rem; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(card.summary)}">${escapeHtml(card.summary)}</td>
                        <td style="padding: 0.5rem;">${escapeHtml(card.x)}</td>
                        <td style="padding: 0.5rem; text-align: right;">${card.p85.toFixed(1)}d</td>
                        <td style="padding: 0.5rem; text-align: right;">${card.trueAge.toFixed(1)}d</td>
                        <td style="padding: 0.5rem; text-align: right;">${card.timeInColumn.toFixed(1)}d</td>
                        <td style="padding: 0.5rem; text-align: right; color: ${penColor}; font-weight: 600;">${card.slePenetration.toFixed(0)}%</td>
                    </tr>
                `;
      });

      html += `
                        </tbody>
                    </table>
                </div>
            `;
      listContainer.innerHTML = html;
    } else {
      listContainer.innerHTML = `<p style="font-size: 0.85rem; color: var(--success-color);">No worrying cards right now. Flow looks healthy!</p>`;
    }
  }
}

function renderSprintComet(issues, startState, endState, filterStartDate) {
  const colorBy = document.getElementById('colorBySelect').value;
  const layoutType = document.getElementById('cometLayoutSelect')
    ? document.getElementById('cometLayoutSelect').value
    : 'cycle_time';

  const proj = document.getElementById('projFilter').value;
  const uniqueSprintsMap = {};
  rawSprintData.forEach((s) => {
    const issueProj = s['Issue Key'] ? s['Issue Key'].split('-')[0] : '';
    if (proj === 'All' || issueProj === proj) {
      if (s['Sprint Name'] && s['Start Date'] && s['End Date']) {
        uniqueSprintsMap[s['Sprint Name']] = {
          name: s['Sprint Name'],
          start: parseDate(s['Start Date']),
          end: parseDate(s['End Date']),
        };
      }
    }
  });
  const sprints = Object.values(uniqueSprintsMap).sort((a, b) => a.start - b.start);

  const startFilterVal = new Date(document.getElementById('startDateFilter').value);
  const endFilterVal = new Date(document.getElementById('endDateFilter').value);
  endFilterVal.setHours(23, 59, 59, 999);

  const validIssues = [];
  issues.forEach((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];
    if (startTime && endTime && endTime >= startTime) {
      if (endTime >= startFilterVal && endTime <= endFilterVal) {
        validIssues.push({ issue, startTime, endTime });
      }
    }
  });

  validIssues.sort((a, b) => a.startTime - b.startTime);
  const lanes = [];
  const groups = {};

  validIssues.forEach((item) => {
    const { issue, startTime, endTime } = item;
    const ctDays = Math.max(0.5, (endTime - startTime) / 86400000);
    let yValue = ctDays;

    if (layoutType === 'tetris') {
      let assignedLane = -1;
      for (let i = 0; i < lanes.length; i++) {
        if (lanes[i] <= startTime) {
          assignedLane = i;
          break;
        }
      }
      if (assignedLane === -1) {
        assignedLane = lanes.length;
        lanes.push(endTime);
      } else {
        lanes[assignedLane] = endTime;
      }
      yValue = assignedLane + 1;
    }

    let crossesSprint = false;
    if (issue.sprints && issue.sprints.length > 1) {
      crossesSprint = true;
    } else if (issue.sprints && issue.sprints.length === 1) {
      const sp = issue.sprints[0];
      const spStart = parseDate(sp['Start Date']);
      const spEnd = parseDate(sp['End Date']);
      if (spStart && spEnd) {
        spEnd.setDate(spEnd.getDate() + 1);
        if (startTime < spStart || endTime > spEnd) {
          crossesSprint = true;
        }
      }
    } else if (!issue.sprints || issue.sprints.length === 0) {
      if (sprints && sprints.length > 0) {
        let overlappingSprints = 0;
        for (const sp of sprints) {
          const spEnd = new Date(sp.end);
          spEnd.setDate(spEnd.getDate() + 1);
          if (startTime <= spEnd && endTime >= sp.start) {
            overlappingSprints++;
          }
        }
        crossesSprint = overlappingSprints > 1;
      }
    }

    let category = 'None';
    if (colorBy === 'type') category = issue.type || 'None';
    else if (colorBy === 'label')
      category = issue.labels && issue.labels.length > 0 ? issue.labels[0] : 'None';
    else if (colorBy === 'unplanned') category = issue.unplanned || 'Unknown';
    else if (colorBy === 'resolution') category = issue.resolution || 'Unresolved';

    if (crossesSprint) category += ' (Cross-Sprint)';
    if (!groups[category]) groups[category] = [];

    groups[category].push(
      {
        x: startTime,
        y: yValue,
        ctDays: ctDays,
        key: issue.key,
        summary: issue.summary,
        type: issue.type,
        labels: (issue.labels || []).join(', '),
        isStart: true,
        estimation: issue.estimation,
      },
      {
        x: endTime,
        y: yValue,
        ctDays: ctDays,
        key: issue.key,
        summary: issue.summary,
        type: issue.type,
        labels: (issue.labels || []).join(', '),
        isEnd: true,
        estimation: issue.estimation,
      },
      { x: null, y: null }
    );
  });

  if (sprintCometChart) sprintCometChart.destroy();

  const canvas = document.getElementById('sprintCometChartCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const datasets = [];
  let colorIdx = 0;

  Object.keys(groups)
    .sort()
    .forEach((cat) => {
      const isCross = cat.toLowerCase().includes('(cross-sprint)');
      const colors = getCategoryColor(cat.replace(' (Cross-Sprint)', ''), colorIdx, isCross);
      let bgColor = colors.bg;
      let borderColor = colors.border;
      if (!isCross) colorIdx++;

      const sizeBy = document.getElementById('cometSizeSelect')
        ? document.getElementById('cometSizeSelect').value
        : 'uniform';
      datasets.push({
        label: cat,
        data: groups[cat],
        backgroundColor: bgColor,
        borderColor: borderColor,
        borderWidth: 2,
        type: 'line',
        showLine: true,
        spanGaps: false,
        segment: {
          borderWidth: (c) => {
            if (sizeBy !== 'estimation') return 2;
            const p1 = c.p0DataIndex;
            const dataPt = c.chart.data.datasets[c.datasetIndex].data[p1];
            if (dataPt && dataPt.estimation !== null && !isNaN(dataPt.estimation)) {
              return Math.max(1, Math.min(10, dataPt.estimation));
            }
            return 2;
          },
        },
        pointRadius: function (context) {
          const pt = context.raw;
          if (!pt || !pt.isEnd) return 0;
          if (sizeBy === 'estimation' && pt.estimation !== null && !isNaN(pt.estimation)) {
            return Math.max(3, Math.min(15, pt.estimation * 2));
          }
          return 6;
        },
        pointHoverRadius: function (context) {
          const pt = context.raw;
          if (!pt || !pt.isEnd) return 0;
          if (sizeBy === 'estimation' && pt.estimation !== null && !isNaN(pt.estimation)) {
            return Math.max(5, Math.min(20, pt.estimation * 2.5));
          }
          return 9;
        },
      });
    });

  const textMuted = getCssVar('--text-muted');
  const sprintBgPlugin = {
    id: 'sprintTimeboxes',
    beforeDraw: (ctxChart) => {
      const chartCtx = ctxChart.ctx;
      const xAxis = ctxChart.scales.x;
      const chartArea = ctxChart.chartArea;
      chartCtx.save();
      let toggle = false;
      sprints.forEach((sprint) => {
        if (sprint.end.getTime() < xAxis.min || sprint.start.getTime() > xAxis.max) return;
        const xStart = Math.max(chartArea.left, xAxis.getPixelForValue(sprint.start.getTime()));
        const xEnd = Math.min(chartArea.right, xAxis.getPixelForValue(sprint.end.getTime()));
        const width = xEnd - xStart;

        if (width > 0) {
          if (toggle) {
            chartCtx.fillStyle = 'rgba(255, 255, 255, 0.03)';
            chartCtx.fillRect(xStart, chartArea.top, width, chartArea.bottom - chartArea.top);
          }
          toggle = !toggle;

          chartCtx.fillStyle = textMuted;
          chartCtx.font = '10px Inter';
          chartCtx.textAlign = 'center';
          const nameParts = sprint.name.split('|');
          chartCtx.fillText(
            nameParts[nameParts.length - 1].trim(),
            xStart + width / 2,
            chartArea.top + 15
          );

          chartCtx.beginPath();
          chartCtx.moveTo(xStart, chartArea.top);
          chartCtx.lineTo(xStart, chartArea.bottom);
          chartCtx.strokeStyle = textMuted;
          chartCtx.lineWidth = 2;
          chartCtx.stroke();
        }
      });
      chartCtx.restore();
    },
  };

  sprintCometChart = new Chart(ctx, {
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'time',
          min: filterStartDate ? filterStartDate.getTime() : undefined,
          time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd', displayFormats: { day: 'MMM dd' } },
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: textMuted },
          title: { display: true, text: 'Date (Flow Timeline)', color: textMuted },
        },
        y: {
          type: layoutType === 'tetris' ? 'linear' : 'logarithmic',
          grid: {
            color: layoutType === 'tetris' ? 'transparent' : getCssVar('--grid-color'),
            drawBorder: false,
          },
          ticks: {
            color: textMuted,
            stepSize: layoutType === 'tetris' ? 1 : undefined,
            display: layoutType !== 'tetris',
          },
          title: {
            display: true,
            text: layoutType === 'tetris' ? 'Concurrent Tracks' : 'Cycle Time (Days, Log Scale)',
            color: textMuted,
          },
          min: layoutType === 'tetris' ? 0 : 0.5,
          reverse: layoutType === 'tetris',
        },
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: getCssVar('--text-color'), usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label: function (c) {
              const pt = c.raw;
              if (!pt || pt.isStart) return '';
              const ctVal = pt.ctDays ? pt.ctDays : pt.y;
              return `[${pt.key}] ${pt.summary} | CT: ${ctVal.toFixed(1)}d | L: ${pt.labels}`;
            },
          },
        },
      },
    },
    plugins: [sprintBgPlugin],
  });
}

function renderThroughput(issues, endState, startDate, endDate) {
  const countsByWeekAndType = {};
  const typesSet = new Set();
  const timebucket = document.getElementById('throughputTimebucketSelect')
    ? document.getElementById('throughputTimebucketSelect').value
    : 'week';

  issues.forEach((issue) => {
    const endTime = issue.transitions[endState];
    if (endTime && endTime >= startDate && endTime <= endDate) {
      let bucketKey = 'Unknown';

      if (timebucket === 'week') {
        const d = new Date(endTime);
        d.setDate(d.getDate() - d.getDay());
        bucketKey = d.toISOString().split('T')[0];
      } else if (timebucket === 'month') {
        const d = new Date(endTime);
        bucketKey = `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}`;
      } else if (timebucket === 'quarter') {
        const d = new Date(endTime);
        bucketKey = `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3) + 1}`;
      } else if (timebucket === 'sprint') {
        const activeSprint = (issue.sprints || []).find((sp) => {
          const spStart = parseDate(sp['Start Date']);
          const spEnd = parseDate(sp['End Date']);
          if (!spStart || !spEnd) return false;
          spEnd.setDate(spEnd.getDate() + 1);
          return endTime >= spStart && endTime <= spEnd;
        });
        bucketKey = activeSprint
          ? activeSprint['Sprint Name'].split('|').pop().trim()
          : 'No Sprint';
      }

      const breakdownBy = document.getElementById('throughputColorBySelect').value;
      let type = 'None';
      if (breakdownBy === 'type') type = issue.type || 'None';
      else if (breakdownBy === 'label')
        type = issue.labels && issue.labels.length > 0 ? issue.labels[0] : 'None';
      else if (breakdownBy === 'unplanned') type = issue.unplanned || 'Unknown';
      else if (breakdownBy === 'resolution') type = issue.resolution || 'Unresolved';
      else if (breakdownBy === 'workclass') type = issue.workClass || 'Value';

      typesSet.add(type);
      if (!countsByWeekAndType[bucketKey]) countsByWeekAndType[bucketKey] = {};
      countsByWeekAndType[bucketKey][type] = (countsByWeekAndType[bucketKey][type] || 0) + 1;
    }
  });

  const sortedWeeks = Object.keys(countsByWeekAndType).sort();
  const types = Array.from(typesSet).sort();

  const datasets = types.map((type, i) => {
    const data = sortedWeeks.map((w) => countsByWeekAndType[w][type] || 0);
    const colors = getCategoryColor(type, i, false);
    return {
      label: type,
      data: data,
      backgroundColor: colors.bg,
      borderColor: colors.border,
      borderWidth: 1,
    };
  });

  if (throughputChart) throughputChart.destroy();

  const canvas = document.getElementById('throughputChartCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  throughputChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: sortedWeeks, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text:
              timebucket === 'week'
                ? 'Week Of'
                : timebucket === 'month'
                  ? 'Month'
                  : timebucket === 'quarter'
                    ? 'Quarter'
                    : 'Sprint',
            color: getCssVar('--text-muted'),
          },
        },
        y: {
          stacked: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: { display: true, text: 'Completed Items', color: getCssVar('--text-muted') },
          min: 0,
        },
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: getCssVar('--text-color') } },
      },
    },
  });
}

// ─── EXPERIMENTAL: Defect Trend run chart ────────────────────────────────────
// Failure-demand (rework/defect) items created per time bucket. A rising slope is
// an EBM Ability-to-Innovate warning that quality is eroding.
function renderDefectTrend(issues, startDate, endDate) {
  if (defectTrendChart) defectTrendChart.destroy();
  const canvas = document.getElementById('defectTrendChartCanvas');
  if (!canvas) return;

  const timebucket = document.getElementById('throughputTimebucketSelect')?.value || 'week';
  const bucketOf = (d) => {
    if (timebucket === 'month')
      return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}`;
    if (timebucket === 'quarter') return `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3) + 1}`;
    const w = new Date(d);
    w.setDate(w.getDate() - w.getDay());
    return w.toISOString().split('T')[0];
  };

  const counts = {};
  let totalDefects = 0;
  issues.forEach((issue) => {
    if ((issue.workClass || 'Value') !== 'Failure Demand') return;
    const c = issue.created;
    if (!c || c < startDate || c > endDate) return;
    const key = bucketOf(c);
    counts[key] = (counts[key] || 0) + 1;
    totalDefects++;
  });

  const buckets = Object.keys(counts).sort();
  const data = buckets.map((b) => counts[b]);

  const noteEl = document.getElementById('defectTrendNote');
  if (noteEl) {
    noteEl.textContent =
      totalDefects === 0
        ? 'No failure-demand items detected (Bugs / regression / defect labels). On a real export, defects are inferred from issue type = Bug and defect labels.'
        : `${totalDefects} failure-demand items created in range. A rising slope signals eroding quality and rework crowding out new value.`;
  }

  const ctx = canvas.getContext('2d');
  defectTrendChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: buckets,
      datasets: [
        {
          label: 'Defects / rework created',
          data: data,
          backgroundColor: 'rgba(239, 68, 68, 0.55)',
          borderColor: '#ef4444',
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text:
              timebucket === 'month' ? 'Month' : timebucket === 'quarter' ? 'Quarter' : 'Week Of',
            color: getCssVar('--text-muted'),
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted'), precision: 0 },
          title: { display: true, text: 'Items created', color: getCssVar('--text-muted') },
        },
      },
      plugins: { legend: { position: 'bottom', labels: { color: getCssVar('--text-color') } } },
    },
  });
}

// ─── EXPERIMENTAL: Value-delivery curve ──────────────────────────────────────
// Cumulative value delivered over time, actual sequencing vs. the ideal. The value
// signal degrades gracefully for real Jira exports:
//   1. explicit Cost of Delay column  -> WSJF-optimal ideal, true magnitudes
//   2. Priority field (Highest..Lowest) -> mapped to CoD magnitude, WSJF ideal
//   3. backlog Rank (LexoRank)          -> ordinal: ideal = rank order
//   4. nothing                          -> FIFO: arrival order is the implied value
// Non-value work (failure demand / maintenance) counts as zero new value.
// NOTE: a CSV export is a point-in-time snapshot — we can detect skips against the
// current rank/arrival order, but cannot see mid-flight re-ranking (rank history is
// not in the export). Hence "experimental".
function resolveValueSignal(items) {
  if (items.some((i) => i.costOfDelay !== null && i.costOfDelay !== undefined))
    return { mode: 'cod', label: 'explicit Cost of Delay' };
  if (items.some((i) => priorityToCoD(i.priorityField) !== null))
    return { mode: 'priority', label: 'Priority field (proxy)' };
  if (items.some((i) => i.rank)) return { mode: 'rank', label: 'backlog Rank order (proxy)' };
  return { mode: 'fifo', label: 'FIFO / arrival order (no value signal)' };
}

function renderValueCurve(issues, endState, startDate, endDate) {
  if (valueCurveChart) valueCurveChart.destroy();
  const canvas = document.getElementById('valueCurveChartCanvas');
  if (!canvas) return;

  const completed = issues.filter((i) => {
    const t = i.transitions[endState];
    return t && t >= startDate && t <= endDate && (i.type || '').toLowerCase() !== 'epic';
  });

  const noteEl = document.getElementById('valueCurveNote');
  if (completed.length === 0) {
    if (noteEl) noteEl.textContent = 'No completed items in range.';
    valueCurveChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: { responsive: true, maintainAspectRatio: false },
    });
    return;
  }

  const signal = resolveValueSignal(completed);
  const size = (i) =>
    i.estimation !== null && !isNaN(i.estimation) && i.estimation > 0 ? i.estimation : 1;

  // Per-item value magnitude. Only Value-class work creates new value.
  const isValue = (i) => (i.workClass || 'Value') === 'Value';
  let magnitude;
  if (signal.mode === 'cod') {
    magnitude = (i) => (isValue(i) ? i.costOfDelay || 0 : 0);
  } else if (signal.mode === 'priority') {
    magnitude = (i) => (isValue(i) ? (priorityToCoD(i.priorityField) ?? 35) : 0);
  } else if (signal.mode === 'rank') {
    const ranked = [...completed]
      .filter(isValue)
      .sort((a, b) => String(a.rank).localeCompare(String(b.rank)));
    const idxMap = new Map(ranked.map((i, idx) => [i.key, ranked.length - idx])); // top of backlog = highest
    magnitude = (i) => (isValue(i) ? idxMap.get(i.key) || 0 : 0);
  } else {
    // fifo: earliest arrival = highest implied value
    const arrived = [...completed].filter(isValue).sort((a, b) => a.created - b.created);
    const idxMap = new Map(arrived.map((i, idx) => [i.key, arrived.length - idx]));
    magnitude = (i) => (isValue(i) ? idxMap.get(i.key) || 0 : 0);
  }

  const origin = Math.min(...completed.map((i) => i.transitions[endState].getTime()));
  const day = (i) => (i.transitions[endState].getTime() - origin) / 86400000;

  const actual = [...completed].sort((a, b) => a.transitions[endState] - b.transitions[endState]);
  const slots = actual.map(day);

  // Ideal: magnitude modes use WSJF (value/size); ordinal modes honor the intended order.
  const ideal =
    signal.mode === 'cod' || signal.mode === 'priority'
      ? [...completed].sort((a, b) => magnitude(b) / size(b) - magnitude(a) / size(a))
      : [...completed].sort((a, b) => magnitude(b) - magnitude(a));

  let cumA = 0,
    cumI = 0,
    codA = 0,
    codI = 0;
  const actualPts = [],
    idealPts = [];
  for (let n = 0; n < slots.length; n++) {
    const t = slots[n];
    const va = magnitude(actual[n]);
    const vi = magnitude(ideal[n]);
    cumA += va;
    cumI += vi;
    codA += va * t;
    codI += vi * t;
    actualPts.push({ x: t, y: cumA });
    idealPts.push({ x: t, y: cumI });
  }
  const efficiency = codA > 0 ? (codI / codA) * 100 : 100;

  if (noteEl) {
    noteEl.innerHTML =
      `Value signal: <b>${signal.label}</b>. Value efficiency <b>${efficiency.toFixed(0)}%</b> ` +
      `(area under actual vs. ideal). ` +
      (signal.mode === 'fifo'
        ? 'No explicit value signal, so arrival order is treated as the intended order — this measures FIFO adherence (skips), not value magnitude.'
        : 'Gap = value delivered later than an ideal-sequenced system would.') +
      ' <i>Snapshot caveat: the export shows current order only; mid-flight re-ranking is not visible.</i>';
  }

  const ctx = canvas.getContext('2d');
  valueCurveChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Ideal (value-sequenced)',
          data: idealPts,
          parsing: false,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16,185,129,0.08)',
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0.1,
          fill: false,
        },
        {
          label: 'Actual delivery',
          data: actualPts,
          parsing: false,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.12)',
          pointRadius: 0,
          tension: 0.1,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'linear',
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text: 'Days since first delivery',
            color: getCssVar('--text-muted'),
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text: 'Cumulative value delivered',
            color: getCssVar('--text-muted'),
          },
        },
      },
      plugins: { legend: { position: 'bottom', labels: { color: getCssVar('--text-color') } } },
    },
  });
}

function renderSprintCarryover(issues, endState, sDate, eDate) {
  const unit = document.getElementById('carryoverUnitSelect')
    ? document.getElementById('carryoverUnitSelect').value
    : 'count';
  const { labels, completedData, carryoverData, mean, stddev, p50Val, p85Val } =
    computeSprintCarryoverData(issues, endState, sDate, eDate, unit);

  if (sprintCarryoverChart) sprintCarryoverChart.destroy();

  const carryoverStatsPlugin = {
    id: 'carryoverStatsLines',
    beforeDraw: (chart) => {
      if (completedData.length === 0) return;
      const ctx = chart.ctx;
      const yAxis = chart.scales.y;
      const chartArea = chart.chartArea;
      ctx.save();

      const yMeanMinusStd = yAxis.getPixelForValue(Math.max(0, mean - stddev));
      const yMeanPlusStd = yAxis.getPixelForValue(mean + stddev);

      ctx.fillStyle = 'rgba(99, 102, 241, 0.08)';
      ctx.fillRect(
        chartArea.left,
        Math.max(chartArea.top, yMeanPlusStd),
        chartArea.right - chartArea.left,
        Math.min(chartArea.bottom, yMeanMinusStd) - Math.max(chartArea.top, yMeanPlusStd)
      );

      ctx.strokeStyle = 'rgba(99, 102, 241, 0.25)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(chartArea.left, yMeanMinusStd);
      ctx.lineTo(chartArea.right, yMeanMinusStd);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(chartArea.left, yMeanPlusStd);
      ctx.lineTo(chartArea.right, yMeanPlusStd);
      ctx.stroke();
      ctx.setLineDash([]);

      const y85 = yAxis.getPixelForValue(p85Val);
      ctx.strokeStyle = 'rgba(245, 158, 11, 0.85)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      ctx.moveTo(chartArea.left, y85);
      ctx.lineTo(chartArea.right, y85);
      ctx.stroke();

      const y50 = yAxis.getPixelForValue(p50Val);
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.85)';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 4]);
      ctx.beginPath();
      ctx.moveTo(chartArea.left, y50);
      ctx.lineTo(chartArea.right, y50);
      ctx.stroke();
      ctx.setLineDash([]);

      const yMean = yAxis.getPixelForValue(mean);
      ctx.strokeStyle = 'rgba(59, 130, 246, 0.7)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, yMean);
      ctx.lineTo(chartArea.right, yMean);
      ctx.stroke();

      ctx.font = '500 10px Outfit, Inter, sans-serif';
      ctx.fillStyle = getCssVar('--text-color');
      ctx.textAlign = 'right';
      ctx.fillText(`85% Conf: ${p85Val.toFixed(1)}`, chartArea.right - 10, y85 - 4);
      ctx.fillText(`50% Conf: ${p50Val.toFixed(1)}`, chartArea.right - 10, y50 - 4);
      ctx.textAlign = 'left';
      ctx.fillText(`Mean: ${mean.toFixed(1)}`, chartArea.left + 10, yMean - 4);
      ctx.fillStyle = 'rgba(99, 102, 241, 0.7)';
      ctx.fillText(`±1 SD (${stddev.toFixed(1)})`, chartArea.left + 10, yMeanPlusStd - 4);
      ctx.restore();
    },
  };

  const ctx = document.getElementById('sprintCarryoverChartCanvas').getContext('2d');
  sprintCarryoverChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Completed in Sprint',
          data: completedData,
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
          borderColor: '#10b981',
          borderWidth: 1,
        },
        {
          label: 'Carryover (Not Completed)',
          data: carryoverData,
          backgroundColor: 'rgba(239, 68, 68, 0.7)',
          borderColor: '#ef4444',
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: { display: true, text: 'Sprint', color: getCssVar('--text-muted') },
        },
        y: {
          stacked: true,
          grid: { color: getCssVar('--grid-color') },
          ticks: { color: getCssVar('--text-muted') },
          title: {
            display: true,
            text: unit === 'points' ? 'Story Points' : 'Issues',
            color: getCssVar('--text-muted'),
          },
          min: 0,
        },
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: getCssVar('--text-color') } },
        tooltip: { mode: 'index', intersect: false },
      },
    },
    plugins: [carryoverStatsPlugin],
  });
}

function renderDependency(issues, startState, endState) {
  const unflaggedKpi = document.getElementById('unflaggedCycleTimeKpi');
  const flaggedKpi = document.getElementById('flaggedCycleTimeKpi');
  const penaltyLabel = document.getElementById('cycleTimePenaltyLabel');
  const doneDependenciesBody = document.getElementById('doneDependenciesTableBody');
  const flagImpactBody = document.getElementById('flagImpactTableBody');

  if (!unflaggedKpi || !flagImpactBody) return;

  let unflaggedCtSum = 0,
    unflaggedCount = 0;
  let flaggedCtSum = 0,
    flaggedCount = 0;

  issues.forEach((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];
    if (startTime && endTime && endTime >= startTime) {
      const ctDays = (endTime - startTime) / 86400000;
      if (issue.flaggedDays > 0 || issue.flagged) {
        flaggedCtSum += ctDays;
        flaggedCount++;
      } else {
        unflaggedCtSum += ctDays;
        unflaggedCount++;
      }
    }
  });

  const avgUnflagged = unflaggedCount > 0 ? unflaggedCtSum / unflaggedCount : 0;
  const avgFlagged = flaggedCount > 0 ? flaggedCtSum / flaggedCount : 0;

  unflaggedKpi.innerText = unflaggedCount > 0 ? `${avgUnflagged.toFixed(1)} days` : '-';
  flaggedKpi.innerText = flaggedCount > 0 ? `${avgFlagged.toFixed(1)} days` : '-';

  if (unflaggedCount > 0 && flaggedCount > 0 && avgFlagged > avgUnflagged) {
    penaltyLabel.innerText = `Penalty: +${(avgFlagged - avgUnflagged).toFixed(1)} days`;
  } else {
    penaltyLabel.innerText = 'Penalty: -';
  }

  const reasonTimeMap = {};
  issues.forEach((issue) => {
    if (issue.flaggedDays > 0 && issue.flagSemanticDurations) {
      Object.entries(issue.flagSemanticDurations).forEach(([semReason, days]) => {
        reasonTimeMap[semReason] = (reasonTimeMap[semReason] || 0) + days;
      });
    } else if (issue.flagged && issue.flagged.trim() !== '') {
      const semReason = classifyCommentSemantic('', issue.flagged);
      reasonTimeMap[semReason] = (reasonTimeMap[semReason] || 0) + 1;
    }
  });

  const sortedReasons = Object.entries(reasonTimeMap)
    .filter((r) => r[1] > 0)
    .sort((a, b) => b[1] - a[1]);
  const reasonLabels = sortedReasons.map((r) => r[0]);
  const reasonData = sortedReasons.map((r) => r[1]);
  const backgroundColors = sortedReasons.map((r) => getSemanticReasonColor(r[0]).bg);
  const borderColors = sortedReasons.map((r) => getSemanticReasonColor(r[0]).border);

  const ctx = document.getElementById('flagReasonChartCanvas');
  if (flagReasonChartInstance) flagReasonChartInstance.destroy();

  if (ctx && sortedReasons.length > 0) {
    ctx.parentElement.style.height = Math.max(300, sortedReasons.length * 28) + 'px';
    const textColor = getCssVar('--text-color') || '#e5e7eb';
    flagReasonChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: reasonLabels,
        datasets: [
          {
            label: 'Total Flagged Days',
            data: reasonData,
            backgroundColor: backgroundColors,
            borderColor: borderColors,
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          title: { display: true, text: 'Total Flagged Days by Semantic Reason', color: textColor },
        },
        scales: {
          x: {
            type: 'logarithmic',
            title: { display: true, text: 'Days (Log Scale)', color: textColor },
            ticks: {
              color: textColor,
              callback: (value) => {
                const valStr = value.toString();
                return valStr.startsWith('1') || valStr.startsWith('2') || valStr.startsWith('5')
                  ? value >= 1
                    ? Math.round(value).toLocaleString()
                    : value.toFixed(1)
                  : null;
              },
            },
            min: 0.1,
          },
          y: { ticks: { color: textColor, autoSkip: false } },
        },
      },
    });
  }

  const doneIssues = issues.filter((i) => i.transitions[endState]);
  const doneKeys = new Set(doneIssues.map((i) => i.key));
  let doneDepsHtml = '';
  let depsCount = 0;

  rawLinksData.forEach((link) => {
    const source = link['Source Issue Key'];
    const target = link['Target Issue Key'];
    const type = link['Link Type Name'];
    const direction = link['Direction'];

    if (doneKeys.has(source)) {
      depsCount++;
      doneDepsHtml += `<tr><td><a href="#" style="color:#60a5fa; text-decoration:none;">${escapeHtml(source)}</a></td><td>${escapeHtml(direction)} <a href="#" style="color:#9ca3af; text-decoration:none;">${escapeHtml(target)}</a> (${escapeHtml(type)})</td></tr>`;
    } else if (doneKeys.has(target)) {
      depsCount++;
      const revDir =
        direction === 'blocks'
          ? 'is blocked by'
          : direction === 'is blocked by'
            ? 'blocks'
            : `reverse of ${direction}`;
      doneDepsHtml += `<tr><td><a href="#" style="color:#60a5fa; text-decoration:none;">${escapeHtml(target)}</a></td><td>${escapeHtml(revDir)} <a href="#" style="color:#9ca3af; text-decoration:none;">${escapeHtml(source)}</a> (${escapeHtml(type)})</td></tr>`;
    }
  });

  if (depsCount === 0) {
    doneDepsHtml = `<tr><td colspan="2" style="text-align:center; padding: 20px; color:#9ca3af;">No dependencies found for completed items.</td></tr>`;
  }
  doneDependenciesBody.innerHTML = doneDepsHtml;

  const historicalFlagged = issues.filter(
    (i) => i.flaggedDays > 0 || (i.flagged && i.flagged.trim() !== '')
  );
  const sortedHistorical = historicalFlagged.sort(
    (a, b) => (b.flaggedDays || 0) - (a.flaggedDays || 0)
  );

  let flagHtml = '';
  sortedHistorical.slice(0, 20).forEach((issue) => {
    const days = issue.flaggedDays ? issue.flaggedDays.toFixed(1) : 'Unknown';
    const reasons =
      issue.flagSemanticReasons && issue.flagSemanticReasons.length > 0
        ? issue.flagSemanticReasons.join(', ')
        : issue.flagged
          ? classifyCommentSemantic('', issue.flagged)
          : 'Unknown';
    flagHtml += `<tr><td><a href="#" style="color:#60a5fa; text-decoration:none;">${escapeHtml(issue.key)}</a></td><td style="font-weight: bold; color: #f59e0b; text-align: right;">${days}</td><td>${escapeHtml(reasons)}</td><td><span class="badge" style="background:#374151; padding:2px 6px; border-radius:4px;">${escapeHtml(issue.currentStatus)}</span></td></tr>`;
  });

  if (sortedHistorical.length === 0) {
    flagHtml = `<tr><td colspan="4" style="text-align:center; padding: 20px; color:#9ca3af;">No historically flagged items found.</td></tr>`;
  }
  flagImpactBody.innerHTML = flagHtml;
}

function renderDataTable(issues, startState, endState) {
  const tableBody = document.getElementById('dataTableBody');
  if (!tableBody) return;
  tableBody.innerHTML = '';

  const sorted = [...issues].sort((a, b) => {
    const bTime = b.transitions[endState] || b.created;
    const aTime = a.transitions[endState] || a.created;
    return bTime - aTime;
  });

  const rows = sorted.map((issue) => {
    const startTime = issue.transitions[startState];
    const endTime = issue.transitions[endState];
    const ctStr =
      startTime && endTime && endTime >= startTime
        ? `${((endTime - startTime) / 86400000).toFixed(1)} days`
        : '-';
    return `
            <tr>
                <td style="font-weight: 600; color: #60a5fa;"><a href="https://your-domain.atlassian.net/browse/${encodeURIComponent(issue.key)}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">${escapeHtml(issue.key)}</a></td>
                <td title="${escapeHtml(issue.summary)}">${escapeHtml(issue.summary)}</td>
                <td>${escapeHtml(issue.type)}</td>
                <td>${escapeHtml(issue.currentStatus)}</td>
                <td>${issue.created ? issue.created.toISOString().split('T')[0] : '-'}</td>
                <td>${issue.updated ? issue.updated.toISOString().split('T')[0] : '-'}</td>
                <td style="font-weight: 500;">${ctStr}</td>
            </tr>
        `;
  });
  tableBody.innerHTML = rows.join('');
}

function renderCoachingInsights(issues, sprintIssues, startState, endState) {
  // Reset AI insight cards
  ['cfd', 'control', 'carryover'].forEach((type) => {
    const card = document.getElementById(`${type}AiInsightCard`);
    if (card) {
      card.style.display = 'none';
      card.innerHTML = '';
    }
  });

  // 1. Capacity Pull Advisor
  const sprintsMap = {};
  sprintIssues.forEach((issue) => {
    if (!issue.sprints) return;
    const est = issue.estimation !== null && !isNaN(issue.estimation) ? issue.estimation : 1;
    issue.sprints.forEach((sp) => {
      const spId = sp['Sprint ID'];
      if (!spId) return;
      if (!sprintsMap[spId]) {
        sprintsMap[spId] = {
          id: spId,
          name: sp['Sprint Name'],
          startDate: new Date(sp['Start Date']),
          endDate: new Date(sp['End Date']),
          plannedCount: 0,
          completedCount: 0,
          carryoverCount: 0,
        };
      }
      const s = sprintsMap[spId];
      s.plannedCount++;

      const endTransition = issue.transitions[endState];
      if (endTransition) {
        const spEndWithGrace = new Date(sp['End Date']);
        const spStartD = new Date(sp['Start Date']);
        spEndWithGrace.setDate(spEndWithGrace.getDate() + 1);

        if (endTransition >= spStartD && endTransition <= spEndWithGrace) {
          s.completedCount++;
        } else if (sp['Sprint State'] === 'active' && endTransition >= spStartD) {
          s.completedCount++;
        } else {
          s.carryoverCount++;
        }
      } else {
        s.carryoverCount++;
      }
    });
  });

  let today = new Date();
  const endStr = document.getElementById('endDateFilter')?.value;
  if (endStr) {
    today = new Date(endStr);
    today.setHours(23, 59, 59, 999);
  }
  const sortedSprints = Object.values(sprintsMap)
    .filter((s) => s.plannedCount > 0 && s.startDate && s.endDate <= today)
    .sort((a, b) => a.startDate - b.startDate);

  const recentSprints = sortedSprints.slice(-5);
  const completedCounts = recentSprints.map((s) => s.completedCount).filter((c) => c > 0);

  let recommendedPullCount = 0;
  let sprintAdvice = 'Not enough completed sprint data to make a recommendation.';
  let carryoverRate = 0.0;

  if (completedCounts.length > 0) {
    completedCounts.sort((a, b) => a - b);
    const idx = Math.max(0, Math.floor(completedCounts.length * 0.15));
    recommendedPullCount = completedCounts[idx];

    const totalPlanned = recentSprints.reduce((sum, s) => sum + s.plannedCount, 0);
    const totalCarryover = recentSprints.reduce((sum, s) => sum + s.carryoverCount, 0);
    carryoverRate = totalPlanned > 0 ? (totalCarryover / totalPlanned) * 100.0 : 0.0;

    sprintAdvice = `Based on your last ${completedCounts.length} sprints, your 85% confidence throughput is <b>${recommendedPullCount} items</b>. `;
    if (carryoverRate > 20) {
      sprintAdvice += `Currently, you carry over <b>${carryoverRate.toFixed(1)}%</b> of your planned items, indicating chronic over-commitment. `;
      sprintAdvice += `We strongly recommend capping the next sprint plan at <b>${recommendedPullCount} items</b> to stabilize flow.`;
    } else {
      sprintAdvice += `You have a healthy carryover rate of <b>${carryoverRate.toFixed(1)}%</b>. You can confidently pull up to <b>${recommendedPullCount} items</b>.`;
    }
  }
  const sprintAdviceEl = document.getElementById('coachingSprintAdvice');
  if (sprintAdviceEl) sprintAdviceEl.innerHTML = sprintAdvice;

  // 2. Retrospective Blocker Advisor
  const blockerDurations = {};
  issues.forEach((issue) => {
    if (issue.flagReasonDurations) {
      Object.keys(issue.flagReasonDurations).forEach((cat) => {
        blockerDurations[cat] = (blockerDurations[cat] || 0) + issue.flagReasonDurations[cat];
      });
    }
    if (issue.flagSemanticDurations) {
      Object.keys(issue.flagSemanticDurations).forEach((cat) => {
        blockerDurations[cat] = (blockerDurations[cat] || 0) + issue.flagSemanticDurations[cat];
      });
    }
  });

  let retroAdvice = 'No major blockers or flags recorded in this dataset.';
  const sortedBlockers = Object.entries(blockerDurations).sort((a, b) => b[1] - a[1]);
  if (sortedBlockers.length > 0) {
    const [topCat, topDur] = sortedBlockers[0];
    const totalBlockerDur = Object.values(blockerDurations).reduce((a, b) => a + b, 0);
    const pct = totalBlockerDur > 0 ? (topDur / totalBlockerDur) * 100.0 : 0;
    retroAdvice =
      `Focus your Retrospective on resolving blocks in category <b>'${escapeHtml(topCat)}'</b>. ` +
      `This category alone accounts for <b>${pct.toFixed(1)}%</b> of all blocker days (${topDur.toFixed(1)} days). ` +
      `Establishing an improvement experiment to reduce delays in '${escapeHtml(topCat)}' is your highest leverage action.`;
  }
  const retroAdviceEl = document.getElementById('coachingRetroAdvice');
  if (retroAdviceEl) retroAdviceEl.innerHTML = retroAdvice;

  // 3. Daily Standup Swarm Alerts
  let now = new Date();
  if (endStr) {
    now = new Date(endStr);
    now.setHours(23, 59, 59, 999);
  }
  const stats = calcFlowMetrics(issues, startState, endState, new Date(0), now);
  const p85Ct = stats.completedCount > 0 ? stats.p85 : 0;

  let standupAlertsCount = 0;
  issues.forEach((issue) => {
    const startT = issue.transitions[startState];
    const endT = issue.transitions[endState];
    if (startT && !endT) {
      const age = (now - startT) / 86400000;
      if (p85Ct > 0 && age > p85Ct) {
        standupAlertsCount++;
      }
    }
  });

  let standupAdvice = 'All active WIP items are currently within typical flow limits.';
  if (standupAlertsCount > 0) {
    standupAdvice =
      `Attention required! There are <b>${standupAlertsCount} items</b> currently in progress that exceed your ` +
      `85% Cycle Time SLE (${p85Ct.toFixed(1)} days). ` +
      `We advise swarming immediately to finish these before starting new work. Check the <b>Item Aging Chart</b> for the specific issues.`;
  }
  const standupAdviceEl = document.getElementById('coachingStandupAdvice');
  if (standupAdviceEl) standupAdviceEl.innerHTML = standupAdvice;

  // 4. Outcome Alignment
  let outputCount = 0;
  let totalTaxed = 0;
  let exampleEpic = 'N/A';

  issues.forEach((issue) => {
    const tax = issue.taxonomy_level;
    if (tax && tax !== 'Unclassified') {
      totalTaxed++;
      if (tax === 'Output' || tax === 'Activity') {
        outputCount++;
        if (issue.type === 'Epic' || issue.type === 'epic') {
          exampleEpic = issue.key;
        }
      }
    }
  });

  let outcomeAdvice =
    'Load <code>issue_value_analysis.csv</code> to enable outcome taxonomy auditing and feature factory risk checks.';
  if (totalTaxed > 0) {
    const outputPct = (outputCount / totalTaxed) * 100.0;
    const outcomePct = 100.0 - outputPct;
    if (outputPct > 70) {
      outcomeAdvice =
        `<b>Feature Factory Risk:</b> ${outputPct.toFixed(1)}% of classified items are Outputs or Activities, ` +
        `while only ${outcomePct.toFixed(1)}% are Outcome/Impact-oriented. ` +
        `We suggest auditing your Epic backlog and reframing technical outputs into behavioral outcomes. ` +
        (exampleEpic !== 'N/A'
          ? `For example, examine Epic <b>'${escapeHtml(exampleEpic)}'</b> which is currently framed as an Output.`
          : '');
    } else {
      outcomeAdvice = `<b>Healthy taxonomy alignment:</b> ${outcomePct.toFixed(1)}% of classified items are Outcome/Impact-oriented. Keep focusing on behavioral outcome goals!`;
    }
  }
  const outcomeAdviceEl = document.getElementById('coachingOutcomeAdvice');
  if (outcomeAdviceEl) outcomeAdviceEl.innerHTML = outcomeAdvice;

  // 5. Innovation Rate / Failure Demand (EBM Ability to Innovate)
  // Story-points-weighted share of delivered effort by work class.
  const effortByClass = { Value: 0, 'Failure Demand': 0, Maintenance: 0 };
  issues.forEach((issue) => {
    if ((issue.type || '').toLowerCase() === 'epic') return;
    if (!issue.transitions[endState]) return;
    const wc = issue.workClass || 'Value';
    const eff =
      issue.estimation !== null && !isNaN(issue.estimation) && issue.estimation > 0
        ? issue.estimation
        : 1;
    effortByClass[wc] = (effortByClass[wc] || 0) + eff;
  });
  const totalEffort = Object.values(effortByClass).reduce((a, b) => a + b, 0);
  let innovationAdvice = 'No completed items in range to assess Innovation Rate.';
  if (totalEffort > 0) {
    const invPct = (effortByClass['Value'] / totalEffort) * 100;
    const fdPct = (effortByClass['Failure Demand'] / totalEffort) * 100;
    const mnPct = (effortByClass['Maintenance'] / totalEffort) * 100;
    innovationAdvice =
      `<b>${invPct.toFixed(0)}%</b> of delivered effort created new value ` +
      `(failure demand <b>${fdPct.toFixed(0)}%</b>, maintenance/filler <b>${mnPct.toFixed(0)}%</b>). `;
    if (fdPct >= 15) {
      innovationAdvice += `<b>Quality alarm:</b> rework is preempting feature work — stabilize testing before pushing more throughput.`;
    } else if (mnPct >= 30) {
      innovationAdvice += `<b>Value starvation:</b> capacity is backfilled with low-value filler. Invest upstream in refinement instead of keeping people busy.`;
    } else {
      innovationAdvice += `Healthy — capacity is overwhelmingly going to new value.`;
    }
  }
  const innovationAdviceEl = document.getElementById('coachingInnovationAdvice');
  if (innovationAdviceEl) innovationAdviceEl.innerHTML = innovationAdvice;

  // Wire up prompt copy button
  const copyPromptBtn = document.getElementById('copyPromptBtn');
  if (copyPromptBtn) {
    copyPromptBtn.onclick = () => {
      const promptText = `I need flow coaching advice based on my Jira team flow metrics. Here is the raw context:
- Completed issues: ${stats.completedCount}
- Average cycle time: ${stats.completedCount > 0 ? stats.avgCt.toFixed(1) : 'N/A'} days
- p50 cycle time: ${stats.completedCount > 0 ? stats.p50.toFixed(1) : 'N/A'} days
- p85 cycle time (SLA/SLE): ${stats.completedCount > 0 ? stats.p85.toFixed(1) : 'N/A'} days
- Active WIP count: ${stats.activeWipCount}
- Top Blocker Categories: ${JSON.stringify(sortedBlockers.slice(0, 3))}
- Sprint Carryovers: Last 5 sprints completed counts are [${completedCounts.join(', ')}] with a carryover rate of ${carryoverRate.toFixed(1)}%
- Value taxonomy: Output/Activity ratio is ${totalTaxed > 0 ? ((outputCount / totalTaxed) * 100).toFixed(1) : 'N/A'}% vs Outcome/Impact ratio of ${totalTaxed > 0 ? (100 - (outputCount / totalTaxed) * 100).toFixed(1) : 'N/A'}%

Please provide 3 specific, actionable recommendations/experiments (e.g. sprint planning adjustments, retro improvement focuses, standup swarming priorities) matching Yuval Yeret's flow coaching principles (descaling, flow over utilization, finishing over starting).`;

      navigator.clipboard
        .writeText(promptText)
        .then(() => {
          alert(
            'Coaching Prompt copied to clipboard! You can paste it directly into Gemini, ChatGPT, or Claude to get advanced LLM coaching advice.'
          );
        })
        .catch((err) => {
          console.error('Clipboard error:', err);
          alert('Failed to copy automatically. Prompt context:\n\n' + promptText);
        });
    };
  }

  // Wire up run AI coach button
  const runAiCoachBtn = document.getElementById('runAiCoachBtn');
  if (runAiCoachBtn) {
    runAiCoachBtn.onclick = async () => {
      const apiKey = geminiApiKey;
      if (!apiKey) {
        alert(
          'Please configure your Gemini API Key in the AI Settings (⚙️ button in the header) first.'
        );
        document.getElementById('apiSettingsModal').style.display = 'flex';
        return;
      }

      if (!confirmAiTransfer()) return;
      const reportCard = document.getElementById('aiCoachingDeepDiveCard');
      const reportContent = document.getElementById('aiCoachingDeepDiveContent');

      if (reportCard && reportContent) {
        reportCard.style.display = 'block';
        reportContent.innerHTML =
          '<span style="color: #60a5fa; font-weight: 500; display: flex; align-items: center; gap: 8px;"><svg class="animate-spin" style="width: 16px; height: 16px; animation: spin 1s linear infinite;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M4 12a8 8 0 018-8v8H4z"></path></svg> Analyzing flow metrics and generating coaching recommendations...</span>';

        if (!document.getElementById('ai-spin-style')) {
          const style = document.createElement('style');
          style.id = 'ai-spin-style';
          style.innerHTML =
            '@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }';
          document.head.appendChild(style);
        }

        const promptText = `I need flow coaching advice based on my Jira team flow metrics. Here is the raw context:
- Completed issues: ${stats.completedCount}
- Average cycle time: ${stats.completedCount > 0 ? stats.avgCt.toFixed(1) : 'N/A'} days
- p50 cycle time: ${stats.completedCount > 0 ? stats.p50.toFixed(1) : 'N/A'} days
- p85 cycle time (SLA/SLE): ${stats.completedCount > 0 ? stats.p85.toFixed(1) : 'N/A'} days
- Active WIP count: ${stats.activeWipCount}
- Top Blocker Categories: ${JSON.stringify(sortedBlockers.slice(0, 3))}
- Sprint Carryovers: Last 5 sprints completed counts are [${completedCounts.join(', ')}] with a carryover rate of ${carryoverRate.toFixed(1)}%
- Value taxonomy: Output/Activity ratio is ${totalTaxed > 0 ? ((outputCount / totalTaxed) * 100).toFixed(1) : 'N/A'}% vs Outcome/Impact ratio of ${totalTaxed > 0 ? (100 - (outputCount / totalTaxed) * 100).toFixed(1) : 'N/A'}%

Please provide 3 specific, actionable recommendations/experiments (e.g. sprint planning adjustments, retro improvement focuses, standup swarming priorities) matching Yuval Yeret's flow coaching principles (descaling, flow over utilization, finishing over starting). Output the response as a clear markdown report.`;

        try {
          const model = localStorage.getItem('geminiModel') || 'gemini-flash-latest';
          const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-goog-api-key': apiKey,
            },
            body: JSON.stringify({
              contents: [
                {
                  parts: [{ text: promptText }],
                },
              ],
            }),
          });

          if (!response.ok) {
            throw new Error(`Gemini API returned HTTP ${response.status}.`);
          }

          const resData = await response.json();
          const text = resData.candidates?.[0]?.content?.parts?.[0]?.text;
          if (text) {
            renderUntrustedText(reportContent, text);
          } else {
            reportContent.innerHTML =
              '<span style="color: #ef4444;">Received empty response from Gemini API. Please check your prompt or model settings.</span>';
          }
        } catch (err) {
          console.error('AI Coach Error:', err);
          renderUntrustedText(reportContent, `Failed to run AI Coach: ${err.message}`);
        }
      }
    };
  }

  // Wire up on-demand chart AI insights
  const cfdBtn = document.getElementById('cfdAiInsightBtn');
  if (cfdBtn) {
    cfdBtn.onclick = async () => {
      await fetchChartInsight('cfd', issues, sprintIssues, startState, endState);
    };
  }
  const controlBtn = document.getElementById('controlAiInsightBtn');
  if (controlBtn) {
    controlBtn.onclick = async () => {
      await fetchChartInsight('control', issues, sprintIssues, startState, endState);
    };
  }
  const carryoverBtn = document.getElementById('carryoverAiInsightBtn');
  if (carryoverBtn) {
    carryoverBtn.onclick = async () => {
      await fetchChartInsight('carryover', issues, sprintIssues, startState, endState);
    };
  }
}

async function fetchChartInsight(chartType, issues, sprintIssues, startState, endState) {
  const apiKey = geminiApiKey;
  if (!apiKey) {
    alert(
      'Please configure your Gemini API Key in the AI Settings (⚙️ button in the header) first.'
    );
    document.getElementById('apiSettingsModal').style.display = 'flex';
    return;
  }

  if (!confirmAiTransfer()) return;
  const cardId = `${chartType}AiInsightCard`;
  const cardEl = document.getElementById(cardId);
  if (!cardEl) return;

  cardEl.style.display = 'block';
  cardEl.innerHTML =
    '<span style="color: #60a5fa; font-weight: 500; display: flex; align-items: center; gap: 8px;"><svg class="animate-spin" style="width: 16px; height: 16px; animation: spin 1s linear infinite;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M4 12a8 8 0 018-8v8H4z"></path></svg> Querying Gemini AI for chart insights...</span>';

  if (!document.getElementById('ai-spin-style')) {
    const style = document.createElement('style');
    style.id = 'ai-spin-style';
    style.innerHTML =
      '@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }';
    document.head.appendChild(style);
  }

  let promptText = '';

  if (chartType === 'cfd') {
    const startStr = document.getElementById('startDateFilter').value;
    const endStr = document.getElementById('endDateFilter').value;
    const startDate = startStr ? new Date(startStr) : new Date(0);
    const endDate = endStr ? new Date(endStr) : new Date();
    endDate.setHours(23, 59, 59, 999);
    const chkStates = Array.from(document.querySelectorAll('.cfd-state-chk:checked')).map(
      (chk) => chk.value
    );

    const { approxCtArray, wipArray } = computeCFDData(
      issues,
      statusColumns,
      chkStates,
      startDate,
      endDate,
      endState
    );
    const avgWip = wipArray.length > 0 ? wipArray.reduce((a, b) => a + b, 0) / wipArray.length : 0;
    const lastWip = wipArray.length > 0 ? wipArray[wipArray.length - 1] : 0;
    const avgApproxCt =
      approxCtArray.length > 0
        ? approxCtArray.reduce((a, b) => a + b, 0) / approxCtArray.length
        : 0;
    const lastApproxCt = approxCtArray.length > 0 ? approxCtArray[approxCtArray.length - 1] : 0;

    promptText = `You are a flow coaching AI. Analyze these Cumulative Flow Diagram (CFD) metrics for a software delivery team:
- Flow stages enabled in CFD: ${chkStates.join(', ')}
- Date range: ${startDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]}
- Average WIP count over this period: ${avgWip.toFixed(1)} issues
- Current (last day) WIP count: ${lastWip} issues
- Average approximate cycle time: ${avgApproxCt.toFixed(1)} days
- Current (last day) approximate cycle time: ${lastApproxCt.toFixed(1)} days

Based on these Cumulative Flow Diagram metrics, please analyze the team's flow stability, WIP limits, bottleneck stages, and predict whether lead times are expanding or shrinking. Keep your feedback concise (2 paragraphs maximum, with bullet points for recommendations). Focus on Yuval Yeret's Kanban/Scrum flow principles (descaling, flow over utilization, finishing over starting). Output the response as a clear markdown report.`;
  } else if (chartType === 'control') {
    const endStr = document.getElementById('endDateFilter')?.value;
    const endDate = endStr ? new Date(endStr) : new Date();
    if (endStr) endDate.setHours(23, 59, 59, 999);
    const stats = calcFlowMetrics(issues, startState, endState, new Date(0), endDate);
    const colorBy = document.getElementById('colorBySelect').value;

    promptText = `You are a flow coaching AI. Analyze these Cycle Time Control Chart (Scatterplot) metrics for a software delivery team:
- Completed issues in scope: ${stats.completedCount}
- Average cycle time: ${stats.completedCount > 0 ? stats.avgCt.toFixed(1) : 'N/A'} days
- p50 cycle time (median): ${stats.completedCount > 0 ? stats.p50.toFixed(1) : 'N/A'} days
- p85 cycle time (SLA/SLE): ${stats.completedCount > 0 ? stats.p85.toFixed(1) : 'N/A'} days
- Cycle times colored/grouped by: ${colorBy}
- Active WIP count: ${stats.activeWipCount}

Based on these Cycle Time Control Chart metrics, please evaluate the predictability of delivery. Are there clusters of outliers, or high variability? What might cause this, and what can the team do to improve cycle time consistency? Keep your feedback concise (2 paragraphs maximum, with bullet points for recommendations). Output the response as a clear markdown report.`;
  } else if (chartType === 'carryover') {
    const unit = document.getElementById('carryoverUnitSelect')
      ? document.getElementById('carryoverUnitSelect').value
      : 'count';
    const startStr = document.getElementById('startDateFilter').value;
    const endStr = document.getElementById('endDateFilter').value;
    const startDate = startStr ? new Date(startStr) : new Date(0);
    const endDate = endStr ? new Date(endStr) : new Date();
    endDate.setHours(23, 59, 59, 999);

    const { labels, completedData, carryoverData, mean, stddev, p50Val, p85Val } =
      computeSprintCarryoverData(sprintIssues, endState, startDate, endDate, unit);

    // Calculate recent carryover rate
    let carryoverRate = 0;
    let totalCompleted = completedData.reduce((a, b) => a + b, 0);
    let totalCarryover = carryoverData.reduce((a, b) => a + b, 0);
    let totalCommitted = totalCompleted + totalCarryover;
    if (totalCommitted > 0) {
      carryoverRate = (totalCarryover / totalCommitted) * 100;
    }

    promptText = `You are a flow coaching AI. Analyze these Sprint Predictability & Carryover metrics for a software delivery team:
- Measurement unit: ${unit}
- Sprints analyzed: ${labels.length} (${labels.join(', ')})
- Completed items per sprint: [${completedData.join(', ')}]
- Carried over items per sprint: [${carryoverData.join(', ')}]
- Average completed items per sprint (Mean): ${mean.toFixed(1)}
- Standard Deviation of completion: ${stddev.toFixed(1)}
- 50% confidence throughput: ${p50Val} items
- 85% confidence throughput: ${p85Val} items
- Overall carryover rate: ${carryoverRate.toFixed(1)}%

Based on these Sprint Carryover metrics, analyze the team's sprint planning behavior. Are they consistently over-committing? Suggest how they can use historical throughput (especially the 85% confidence throughput line) and carryover rates to set realistic commitments in sprint planning. Keep your feedback concise (2 paragraphs maximum, with bullet points for recommendations). Output the response as a clear markdown report.`;
  }

  try {
    const model = localStorage.getItem('geminiModel') || 'gemini-flash-latest';
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey,
      },
      body: JSON.stringify({
        contents: [
          {
            parts: [{ text: promptText }],
          },
        ],
      }),
    });

    if (!response.ok) {
      throw new Error(`Gemini API returned HTTP ${response.status}.`);
    }

    const resData = await response.json();
    const text = resData.candidates?.[0]?.content?.parts?.[0]?.text;
    if (text) {
      renderUntrustedText(cardEl, text);
    } else {
      cardEl.innerHTML =
        '<span style="color: #ef4444;">Received empty response from Gemini API. Please check your prompt or model settings.</span>';
    }
  } catch (err) {
    console.error('AI Chart Insight Error:', err);
    renderUntrustedText(cardEl, `Failed to run AI Chart Insight: ${err.message}`);
  }
}

function printReport() {
  const meta = document.getElementById('printMeta');
  if (meta) {
    const proj = document.getElementById('projFilter')?.value || 'All';
    const type = document.getElementById('typeFilter')?.value || 'All';
    meta.textContent = `Project: ${proj} · Type: ${type} · Generated: ${new Date().toLocaleDateString()}`;
  }
  window.print();
}

window.addEventListener('beforeprint', () => {
  document.querySelectorAll('.chart-container canvas').forEach((canvas) => {
    const existing = canvas.parentNode.querySelector('.chart-print-img');
    if (existing) existing.remove();
    const img = document.createElement('img');
    img.src = canvas.toDataURL('image/png');
    img.className = 'chart-print-img';
    canvas.parentNode.appendChild(img);
  });
});

window.addEventListener('afterprint', () => {
  document.querySelectorAll('.chart-print-img').forEach((img) => img.remove());
});
