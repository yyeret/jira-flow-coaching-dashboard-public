/** Escape untrusted text for HTML text and quoted attribute contexts. */
export function escapeHtml(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character]
  );
}

/** Model responses and API errors are untrusted text, never executable markup. */
export function renderUntrustedText(element, value) {
  element.textContent = String(value ?? '');
  element.style.whiteSpace = 'pre-wrap';
}

/** Require explicit informed consent for each external AI request. */
export function confirmAiTransfer() {
  return window.confirm(
    'Send these dashboard metrics to Google Gemini? The request includes aggregate flow metrics and may include workflow stage names, sprint names, and blocker categories. Your Gemini API key is sent to Google to authenticate the request. Only proceed if you are authorized to share this information.'
  );
}

/** Clear every dashboard cache before discarding in-memory data by reloading. */
export function bindClearSavedData() {
  const button = document.getElementById('clearSavedDataBtn');
  if (!button) return;
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      if (typeof localforage !== 'undefined') await localforage.clear();
      localStorage.removeItem('geminiApiKey');
      window.location.reload();
    } catch {
      button.disabled = false;
      button.textContent = 'Could not clear saved data. Try again.';
    }
  });
}
