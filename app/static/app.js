'use strict';
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', () => {
    if (!form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.dataset.original = button.textContent; button.textContent = 'Working…'; }
    const message = form.querySelector('.loading-message');
    if (message) message.hidden = false;
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('button[data-original]').forEach(button => {
    button.disabled = false; button.textContent = button.dataset.original;
  });
  document.querySelectorAll('.loading-message').forEach(el => { el.hidden = true; });
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
