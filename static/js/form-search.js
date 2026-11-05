/* Accessible, dependency-free search for long form choices. Original form inputs
   remain in the DOM so Django receives exactly the same submitted values. */
(function () {
  'use strict';
  const normalize = value => (value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim();
  function makeSearch(placeholder, target) {
    const input = document.createElement('input');
    input.type = 'search';
    input.className = 'form-choice-search';
    input.placeholder = placeholder;
    input.setAttribute('aria-label', placeholder);
    input.autocomplete = 'off';
    target.parentNode.insertBefore(input, target);
    return input;
  }
  function searchableSelect(select) {
    if (select.dataset.searchReady || select.disabled || select.options.length < 5 || select.multiple) return;
    select.dataset.searchReady = 'true';
    const input = makeSearch('Buscar ' + (select.closest('.field')?.querySelector('label')?.textContent || 'opción').replace('*', '').trim() + '…', select);
    const empty = document.createElement('p');
    empty.className = 'form-search-empty';
    empty.hidden = true;
    empty.textContent = 'No hay coincidencias.';
    select.insertAdjacentElement('afterend', empty);
    const options = Array.from(select.options).map(option => ({value: option.value, text: option.textContent, disabled: option.disabled}));
    const refresh = () => {
      const q = normalize(input.value);
      const selected = select.value;
      const matches = options.filter(option => !q || !option.value || normalize(option.text).includes(q) || option.value === selected);
      select.replaceChildren(...matches.map(option => {
        const el = new Option(option.text, option.value, false, option.value === selected);
        el.disabled = option.disabled;
        return el;
      }));
      empty.hidden = matches.some(option => option.value);
    };
    input.addEventListener('input', refresh);
    select.addEventListener('change', () => { input.value = ''; refresh(); });
  }
  function searchableChecks(group) {
    if (group.dataset.searchReady) return;
    const items = Array.from(group.querySelectorAll('label')).filter(label => label.querySelector('input[type="checkbox"], input[type="radio"]'));
    if (items.length < 5) return;
    group.dataset.searchReady = 'true';
    const input = makeSearch('Buscar productores u opciones…', group);
    const count = document.createElement('div');
    count.className = 'form-search-count';
    input.insertAdjacentElement('afterend', count);
    const refresh = () => {
      const q = normalize(input.value);
      let visible = 0;
      items.forEach(label => {
        const match = !q || normalize(label.textContent).includes(q);
        // Only hide the label, never remove its input or change checked state.
        label.hidden = !match;
        if (match) visible++;
      });
      const checked = items.filter(label => label.querySelector('input').checked).length;
      count.textContent = `${visible} visibles · ${checked} seleccionados`;
    };
    input.addEventListener('input', refresh);
    group.addEventListener('change', refresh);
    refresh();
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form select').forEach(searchableSelect);
    document.querySelectorAll('form .field > div, form .field > ul').forEach(group => {
      if (group.querySelectorAll('input[type="checkbox"], input[type="radio"]').length >= 5) searchableChecks(group);
    });
  });
})();
