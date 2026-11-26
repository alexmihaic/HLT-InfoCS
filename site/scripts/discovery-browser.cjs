// Run against a locally served build. Pass a Playwright module path if not installed locally.
// node scripts/discovery-browser.cjs [playwright-module] [base-url]
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(__dirname, '../../docs/evidence/discovery-01');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.DISCOVERY_BROWSER_CHANNEL === 'chromium' ? {} : { channel: process.env.DISCOVERY_BROWSER_CHANNEL || 'msedge' }) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    const base = process.argv[3] || 'http://127.0.0.1:8031';
    const visit = query => page.goto(`${base}/registros/${query || ''}`);
    const visible = () => page.locator('[data-record-list] > li:visible').count();
    await visit();
    const total = await visible();
    assert.ok(total > 0);
    await page.locator('#filter-organismo').selectOption('nombre:ALMASSORA');
    const almassora = await visible();
    assert.ok(almassora > 0);
    await page.locator('#filter-fuente').selectOption('bdns');
    assert.equal(await visible(), almassora);
    await page.reload();
    assert.equal(await visible(), almassora);
    assert.equal(await page.locator('#filter-organismo').inputValue(), 'nombre:ALMASSORA');
    // Every displayed count equals the result of substituting only its own filter.
    const facetChecks = await page.evaluate(() => {
      const mapping = { tipo: 'category', convocatoria: 'calltype', municipio: 'municipality', organismo: 'authority', fuente: 'source' };
      const selects = [...document.querySelectorAll('[data-record-filters] select')];
      const items = [...document.querySelectorAll('[data-record-list] > li')];
      return selects.every(select => [...select.options].every(option => {
        const count = items.filter(item => selects.every(other => {
          const value = other === select ? option.value : other.value;
          return !value || item.dataset[mapping[other.name]] === value;
        })).length;
        return option.textContent.endsWith(`(${count})`);
      }));
    });
    assert.ok(facetChecks);
    await page.locator('#filter-fuente').selectOption('boe');
    assert.equal(await visible(), 0);
    assert.ok(await page.locator('[data-filter-empty]').isVisible());
    await page.goBack();
    assert.equal(await visible(), almassora);
    await page.goForward();
    assert.equal(await visible(), 0);
    await page.locator('[data-filter-reset]').click();
    assert.equal(await visible(), total);
    assert.equal(await page.locator('#filter-tipo').evaluate(el => el === document.activeElement), true);
    await visit('?organismo=%3Cscript%3E&fuente=bogus&desde=2026-02-30&hasta=garbage&tipo=employment&tipo=grants.call');
    assert.equal(await visible(), total);
    assert.equal(new URL(page.url()).search, '');
    await visit('?desde=2026-10-29&hasta=2026-10-01');
    assert.equal(await visible(), 0);
    assert.ok(await page.locator('#filter-date-error').isVisible());
    await page.screenshot({ path: path.join(output, 'intervalo-invalido.png'), fullPage: true });
    await visit('?fuente=boe&desde=2026-10-01&hasta=2026-10-28');
    const boe = await visible();
    assert.ok(boe > 0);
    await page.locator('#filter-tipo').focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'filter-convocatoria');
    assert.notEqual(await page.locator('#filter-tipo').inputValue(), '');
    await visit('?organismo=nombre%3AALMASSORA&fuente=bdns');
    await page.evaluate(() => document.documentElement.dataset.theme = 'light');
    await page.screenshot({ path: path.join(output, 'escritorio-claro.png'), fullPage: true });
    await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
    await page.screenshot({ path: path.join(output, 'escritorio-oscuro.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, `movil-${theme}.png`), fullPage: true });
    }
    const detail = await page.locator('[data-record-list] > li:visible h2 a').first().getAttribute('href');
    for (const route of ['/', '/organismos/', '/organismos/almassora/', detail]) {
      const response = await page.goto(`${base}${route}`);
      assert.equal(response.status(), 200);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    await page.goto(`${base}/buscar/?q=Almassora`);
    await page.waitForFunction(() => document.querySelectorAll('#search-results li').length > 0);
    const searchResults = await page.locator('#search-results li').count();
    await page.screenshot({ path: path.join(output, 'pagefind-movil.png'), fullPage: true });
    assert.deepEqual(errors, []);
    const result = { total, almassora, boeOctober: boe, pagefindAlmassora: searchResults, consoleErrors: errors, checks: ['AND', 'facet counts', 'reload', 'back/forward', 'reset focus', 'invalid and duplicate URL', 'reversed dates', 'keyboard', '390px no overflow', 'light/dark', 'directory', 'detail', 'Pagefind'] };
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify(result, null, 2));
    console.log(result);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
