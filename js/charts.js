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

export function getCssVar(name) {
  if (typeof window !== 'undefined' && window.getComputedStyle) {
    return window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  return '';
}

export function getCategoryColor(category, colorIdx = 0, isCross = false) {
  const catLower = (category || '').toLowerCase();
  let hex = statusColorPalette[colorIdx % statusColorPalette.length];

  if (catLower.includes('bug') || catLower.includes('defect')) hex = '#ef4444';
  else if (catLower.includes('story')) hex = '#3b82f6';
  else if (catLower.includes('epic')) hex = '#f59e0b';
  else if (
    catLower.includes('task') ||
    catLower.includes('sub-task') ||
    catLower.includes('subtask')
  )
    hex = '#10b981';
  else if (catLower.includes('spike') || catLower.includes('research')) hex = '#8b5cf6';
  else if (catLower.includes('incident')) hex = '#f43f5e';
  else if (catLower.includes('action')) hex = '#06b6d4';
  else if (catLower.includes('enabler')) hex = '#6366f1';
  else if (catLower.includes('feature')) hex = '#14b8a6';

  let r = parseInt(hex.slice(1, 3), 16) || 0,
    g = parseInt(hex.slice(3, 5), 16) || 0,
    b = parseInt(hex.slice(5, 7), 16) || 0;

  if (isCross) {
    r = Math.floor(r * 0.4);
    g = Math.floor(g * 0.4);
    b = Math.floor(b * 0.4);
  }

  return {
    bg: `rgba(${r}, ${g}, ${b}, 0.7)`,
    border: `rgba(${r}, ${g}, ${b}, 1)`,
    hex: hex,
  };
}

export function getSemanticReasonColor(reason) {
  if (reason.startsWith('Product:')) {
    return {
      bg: 'rgba(245, 158, 11, 0.6)', // Amber/Gold
      border: 'rgba(245, 158, 11, 1)',
    };
  } else if (reason.startsWith('Tech:')) {
    return {
      bg: 'rgba(59, 130, 246, 0.6)', // Blue
      border: 'rgba(59, 130, 246, 1)',
    };
  } else if (reason.startsWith('Infra:')) {
    return {
      bg: 'rgba(239, 68, 68, 0.6)', // Red
      border: 'rgba(239, 68, 68, 1)',
    };
  } else if (reason.startsWith('External:')) {
    return {
      bg: 'rgba(147, 51, 234, 0.6)', // Purple
      border: 'rgba(147, 51, 234, 1)',
    };
  } else if (reason.startsWith('Team:')) {
    return {
      bg: 'rgba(16, 185, 129, 0.6)', // Teal/Green
      border: 'rgba(16, 185, 129, 1)',
    };
  }
  return {
    bg: 'rgba(107, 114, 128, 0.6)', // Grey
    border: 'rgba(107, 114, 128, 1)',
  };
}

export function copyChartToClipboard(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = canvas.width;
  tempCanvas.height = canvas.height;
  const ctx = tempCanvas.getContext('2d');

  ctx.fillStyle =
    getComputedStyle(document.body).getPropertyValue('--panel-bg').trim() || '#ffffff';
  ctx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);
  ctx.drawImage(canvas, 0, 0);

  tempCanvas.toBlob(function (blob) {
    if (!blob) {
      alert('Failed to copy image');
      return;
    }
    const item = new ClipboardItem({ 'image/png': blob });
    navigator.clipboard.write([item]).then(
      function () {
        const btn = document.querySelector(`button[data-canvas="${canvasId}"]`);
        if (btn) {
          const origText = btn.innerHTML;
          btn.innerHTML =
            '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path></svg> Copied!';
          setTimeout(() => (btn.innerHTML = origText), 2000);
        }
      },
      function (err) {
        console.error('Could not copy image: ', err);
        alert('Failed to copy: ' + err);
      }
    );
  }, 'image/png');
}

export function addCopyButtons() {
  document.querySelectorAll('.chart-panel').forEach((panel) => {
    const header = panel.querySelector('.chart-header');
    const canvas = panel.querySelector('canvas');
    if (header && canvas && !header.querySelector('.copy-btn')) {
      const btn = document.createElement('button');
      btn.className = 'copy-btn';
      btn.setAttribute('data-canvas', canvas.id);
      btn.innerHTML =
        '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg> Copy Image';
      btn.onclick = () => copyChartToClipboard(canvas.id);

      const existingControls = Array.from(header.children).find(
        (c) => c.tagName === 'DIV' && c !== header.firstElementChild
      );
      if (existingControls) {
        existingControls.appendChild(btn);
      } else {
        const newActions = document.createElement('div');
        newActions.style.display = 'flex';
        newActions.style.alignItems = 'center';
        newActions.style.gap = '10px';
        newActions.appendChild(btn);
        header.appendChild(newActions);
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'flex-start';
      }
    }
  });
}
