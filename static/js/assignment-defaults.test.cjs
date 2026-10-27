// Run with: node --test static/js/assignment-defaults.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('unique assignment fills fields; multiple choices remain selectable', () => {
  const fields = {};
  function select(name, ids) {
    const field = { value: '', options: ['', ...ids].map(value => ({ value })), dataset: {}, events: {}, addEventListener(event, fn) { this.events[event] = fn; } };
    fields[name] = field;
    return field;
  }
  const driver = select('assigned_driver', ['d1', 'd2']);
  const route = select('assigned_route', ['r1', 'r2']);
  const vehicle = select('assigned_vehicle', ['v1', 'v2']);
  driver.dataset.assignments = JSON.stringify({ drivers: [{ id: 'd1', routes: ['r1'] }, { id: 'd2', routes: ['r1', 'r2'] }], vehicles: [{ id: 'v1', driver: 'd1', route: 'r1' }, { id: 'v2', driver: 'd2', route: 'r2' }] });
  vm.runInNewContext(fs.readFileSync(__dirname + '/assignment-defaults.js', 'utf8'), { document: { addEventListener: (_, fn) => fn(), querySelector: s => fields[s.match(/name="(.*?)"/)[1]] || null } });
  driver.value = 'd1'; driver.events.change();
  assert.equal(route.value, 'r1'); assert.equal(vehicle.value, 'v1');
  route.value = ''; vehicle.value = ''; driver.value = 'd2'; driver.events.change();
  assert.equal(route.value, '', 'multiple routes are not chosen arbitrarily');
  route.value = 'r2'; route.events.change();
  assert.equal(driver.value, 'd2'); assert.equal(vehicle.value, 'v2');
});
