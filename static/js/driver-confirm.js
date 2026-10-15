document.querySelectorAll('form[data-confirm-driver]').forEach((form) => {
  const dialog = document.querySelector('[data-driver-dialog]');
  if (!dialog) return;
  const fields = [...form.querySelectorAll('input, select, textarea')].filter((field) => field.name && field.name !== 'csrfmiddlewaretoken');
  const initial = new Map(fields.map((field) => [field, field.type === 'checkbox' ? field.checked : field.value]));
  const labels = { routes: 'Rutas asignadas', vehicles: 'Placas asignadas', producers: 'Productores asignados' };
  const title = (field) => form.querySelector(`label[for="${field.id}"]`)?.textContent.trim() || field.name;

  form.addEventListener('submit', (event) => {
    if (form.dataset.confirmed === 'true') return;
    event.preventDefault();
    const changes = [];
    for (const [name, label] of Object.entries(labels)) {
      const changed = fields.filter((field) => field.name === name && field.type === 'checkbox' && initial.get(field) !== field.checked);
      if (changed.length) {
        const detail = changed.map((field) => `${field.checked ? 'Asignar' : 'Quitar'} ${field.closest('label')?.textContent.trim() || field.value}`).join('; ');
        changes.push(`${label}: ${detail}`);
      }
    }
    for (const field of fields) {
      if (field.type === 'checkbox' || field.name === 'password2' || Object.hasOwn(labels, field.name) || initial.get(field) === field.value) continue;
      if (field.type === 'password') changes.push('Contraseña del conductor: se establecerá una nueva clave');
      else changes.push(`${title(field)}: «${initial.get(field) || 'vacío'}» → «${field.value || 'vacío'}»`);
    }
    const list = dialog.querySelector('[data-driver-changes]');
    list.replaceChildren();
    for (const description of changes.length ? changes : ['No se detectaron cambios en los campos.']) {
      const item = document.createElement('li');
      item.textContent = description;
      list.append(item);
    }
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else if (window.confirm(`${changes.join('\n')}\n¿Deseas guardar esta configuración?`)) {
      form.dataset.confirmed = 'true';
      form.requestSubmit();
    }
  });
  dialog.querySelector('[data-driver-cancel]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-driver-accept]').addEventListener('click', () => {
    dialog.close();
    form.dataset.confirmed = 'true';
    form.requestSubmit();
  });
});
