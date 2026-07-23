// Пример ответа quote_price (локальная эмуляция QuotePrice.js, цены = живой снимок 03.07.2026)
const fs = require('fs');
const vm = require('vm');

const PRICE_ROWS = {
  23: ['YAMAHA NMAX 155', 449, 337, '', '', '', '', 3000],
};
const DISCOUNTS = { B2: 0.15, B9: 0.15, B19: 0.25 };

const priceTab = {
  getRange: (a) => {
    if (typeof a === 'string') return { getValue: () => DISCOUNTS[a] };
    return { getValues: () => [PRICE_ROWS[a]] };
  },
};
const clientsTab = { getLastRow: () => 1, getRange: () => ({ getValues: () => [] }) };

const sandbox = {
  CONFIG: { TABS: { PRICES_ALT: 'цены альт', CLIENTS: 'клиенты' } },
  getSheet: (key, tab) => (tab === 'цены альт' ? priceTab : clientsTab),
  resolveBikeName_: () => 'NMAX 155CC GREEN-B PHUKET 4957',
  console,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('/root/turbobaby-bridge-gs/QuotePrice.js', 'utf8'), sandbox);
const r = sandbox.quotePrice({ bike: '4957', date_start: '08.07.2026', date_end: '15.07.2026' });
console.log(JSON.stringify(r, null, 2));
