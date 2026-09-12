'use strict';
// Ordinary forms still work with or without JavaScript.
document.querySelectorAll('form:not(.answer-form)').forEach(form => {
  form.addEventListener('submit', () => {
    if (!form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.dataset.original = button.textContent; button.textContent = 'Working…'; }
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('button[data-original]').forEach(button => {
    button.disabled = false; button.textContent = button.dataset.original;
  });
});
const questionType = document.getElementById('question-type');
function updateQuestionFields() {
  if (!questionType) return;
  document.getElementById('mcq-fields').hidden = questionType.value !== 'MCQ';
  document.getElementById('rubric-fields').hidden = questionType.value === 'MCQ';
}
questionType?.addEventListener('change', updateQuestionFields);
updateQuestionFields();
document.getElementById('print-report')?.addEventListener('click', () => window.print());

(() => {
  const form = document.querySelector('.answer-form');
  if (!form || typeof window.fetch !== 'function' || typeof AbortController !== 'function') return;
  const button = form.querySelector('button[type="submit"]');
  const loading = form.querySelector('.loading-message');
  const errorBox = form.querySelector('.answer-error');
  const errorText = document.getElementById('answer-error-text');
  const checkButton = document.getElementById('check-progress');
  let busy = false;
  let uncertain = false;

  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  function setBusy(value) {
    busy = value;
    button.disabled = value || uncertain;
    button.textContent = value ? 'Working…' : 'Submit & continue →';
    loading.hidden = !value;
    checkButton.disabled = value;
    document.getElementById('question-card').setAttribute('aria-busy', String(value));
    form.querySelectorAll('[name="answer"]').forEach(input => { input.disabled = value; });
  }
  function showError(message) {
    errorText.textContent = message;
    errorBox.hidden = false;
  }
  async function request(url, options = {}, timeout = 28000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options, signal: controller.signal});
      const data = await response.json();
      return {response, data};
    } finally { clearTimeout(timer); }
  }
  function render(state) {
    if (state.status === 'completed') {
      window.location.assign(form.dataset.reportUrl);
      return;
    }
    const q = state.question;
    if (!q || !['MCQ', 'Subjective'].includes(q.question_type) || typeof q.question_text !== 'string' ||
        (q.question_type === 'MCQ' && (!Array.isArray(q.options) || q.options.some(x => typeof x !== 'string')))) {
      throw new Error('Invalid assessment response');
    }
    const controls = document.getElementById('answer-controls');
    const fragment = document.createDocumentFragment();
    if (q.question_type === 'MCQ') {
      const fieldset = node('fieldset');
      fieldset.append(node('legend', 'Select one answer', 'muted'));
      q.options.forEach((option, index) => {
        const label = node('label', undefined, 'answer-option');
        const input = document.createElement('input');
        input.type = 'radio'; input.name = 'answer'; input.value = option; input.required = true;
        label.append(input, node('span', 'ABCDEFGH'[index], 'option-letter'), node('span', option));
        fieldset.append(label);
      });
      fragment.append(fieldset);
    } else {
      const label = node('label', 'Your answer', 'form-stack');
      const textarea = document.createElement('textarea');
      textarea.name = 'answer'; textarea.required = true; textarea.maxLength = 3000; textarea.rows = 9;
      textarea.placeholder = 'Explain your approach, reasoning, and trade-offs…';
      label.append(textarea);
      fragment.append(label, node('p', 'Be specific. Maximum 3,000 characters.', 'muted small'));
    }
    // All returned text is assigned as text, never parsed as HTML.
    controls.replaceChildren(fragment);
    form.elements.question_id.value = q.id;
    document.getElementById('question-title').textContent = q.question_text;
    document.getElementById('question-skill').textContent = q.skill;
    document.getElementById('question-difficulty').textContent = `Difficulty ${q.difficulty} / 5`;
    document.getElementById('question-type-label').textContent = q.question_type;
    document.getElementById('question-counter').textContent = `Question ${state.answered_count + 1} / up to ${state.max_questions}`;
    document.getElementById('answered-count').textContent = `${state.answered_count} submitted`;
    const progress = document.getElementById('assessment-progress');
    progress.max = state.max_questions; progress.value = state.answered_count;
    errorBox.hidden = true;
    uncertain = false;
    document.getElementById('question-title').focus();
  }
  async function reconcile(oldQuestionId) {
    const {response, data} = await request(form.dataset.apiUrl, {}, 8000);
    if (!response.ok) throw new Error('Progress unavailable');
    if (data.status === 'completed' || (data.question && data.question.id !== oldQuestionId)) {
      render(data); return true;
    }
    return false;
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || uncertain || !form.reportValidity()) return;
    const values = new FormData(form);
    const oldQuestionId = values.get('question_id');
    setBusy(true); errorBox.hidden = true;
    try {
      const {response, data} = await request(form.action, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': values.get('csrf_token')},
        body: JSON.stringify({question_id: oldQuestionId, answer: values.get('answer')})
      });
      if (!response.ok) {
        // A 409 may mean another tab saved this question; a 5xx may be a lost acknowledgement.
        if (response.status === 409 || response.status >= 500) {
          uncertain = true;
          if (await reconcile(oldQuestionId)) return;
          showError('The submission is not confirmed yet. Your answer is preserved. Check saved progress before retrying.');
        } else {
          showError((data.error || 'Unable to submit this answer.') + (data.reference ? ` Reference: ${data.reference}` : ''));
        }
        return;
      }
      render(data);
    } catch (_) {
      uncertain = true;
      try { if (await reconcile(oldQuestionId)) return; } catch (_) { /* Keep the current draft. */ }
      showError('Connection interrupted. Your answer is preserved. Check saved progress before retrying.');
    } finally { setBusy(false); }
  });
  checkButton.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (await reconcile(form.elements.question_id.value)) return;
      // An explicit user check unlocks a retry. Server-side duplicate checks remain authoritative.
      uncertain = false;
      showError('This question is still current. Your answer is preserved; you can retry submission.');
    } catch (_) {
      showError('Progress is unavailable. Keep this page open and check your connection.');
    } finally { setBusy(false); }
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) { uncertain = true; setBusy(false); showError('Check saved progress before continuing from browser history.'); }
  });
})();
