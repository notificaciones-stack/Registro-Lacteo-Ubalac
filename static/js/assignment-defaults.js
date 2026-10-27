document.addEventListener('DOMContentLoaded', () => {
  const find = name => document.querySelector(`[name="${name}"]`);
  const driver = find('assigned_driver') || find('driver');
  const route = find('assigned_route') || find('route');
  const vehicle = find('assigned_vehicle');
  const set = (field, value) => {
    if (field && [...field.options].some(o => o.value === value)) field.value = value;
  };
  const choose = (field, ids) => {
    if (!field) return;
    const unique = [...new Set(ids.filter(Boolean))];
    if (unique.length === 1) set(field, unique[0]);
    else if (field.value && !unique.includes(field.value)) field.value = '';
  };
  if (driver?.dataset.assignments) {
    const data = JSON.parse(driver.dataset.assignments);
    const update = source => {
      if (source === vehicle && vehicle.value) {
        const v = data.vehicles.find(v => v.id === vehicle.value);
        if (v) { set(driver, v.driver); set(route, v.route); }
      }
      if (source === route && route.value) {
        choose(driver, data.drivers.filter(d => d.routes.includes(route.value)).map(d => d.id));
      }
      const d = data.drivers.find(d => d.id === driver.value);
      if (d) {
        if (source === driver || !route.value) choose(route, d.routes);
        for (const [name, value] of [['driver_name', d.name], ['driver_document', d.document], ['driver_phone', d.phone]]) {
          if (find(name)) find(name).value = value;
        }
      }
      if (driver.value || route?.value) choose(vehicle, data.vehicles.filter(v => (!driver.value || v.driver === driver.value) && (!route?.value || v.route === route.value)).map(v => v.id));
    };
    [driver, route, vehicle].filter(Boolean).forEach(field => field.addEventListener('change', () => update(field)));
    // Keep existing explicit assignments on edit; fill only missing unique values.
    if (driver.value || route?.value || vehicle?.value) update(null);
  }
  const producer = find('producer');
  if (producer?.dataset.producers) {
    const data = JSON.parse(producer.dataset.producers);
    producer.addEventListener('change', () => {
      const p = data.find(p => p.id === producer.value);
      if (p) { set(route, p.route); set(find('vehicle'), p.vehicle); }
    });
  }
});
