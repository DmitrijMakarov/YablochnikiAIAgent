// Render actual captured file excerpts and CLI output, never a simulated IDE/chat.
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'deliverables/megafon/submission');
const data = JSON.parse(fs.readFileSync(path.join(out, 'evidence.json'), 'utf8'));
const escape = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.SUBMISSION_BROWSER || 'chrome'});
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}, deviceScaleFactor: 1.5});
  await page.route(/^https?:/, route => route.abort());
  const captures = [];
  for (const panel of data.panels) {
    const actual = panel.id === '06-resume' ? JSON.parse(data.resume.stdout) : null;
    const html = `<!doctype html><html lang="ru"><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{margin:0;background:#e9efed;color:#152d32;font-family:Arial,sans-serif}
    article{margin:20px;padding:30px 34px;background:white;border:1px solid #cddbd6;border-radius:12px}
    .label{font-size:18px;letter-spacing:1px;color:#006d5b;font-weight:700}h1{font-size:32px;margin:15px 0 12px}
    .path{font-family:Menlo,monospace;font-size:17px;color:#526662;overflow-wrap:anywhere;border-bottom:1px solid #d9e3df;padding-bottom:16px}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:Arial,sans-serif;font-size:23px;line-height:1.4;margin:22px 0}
    footer{font-size:16px;line-height:1.5;color:#526662;border-top:1px solid #d9e3df;padding-top:14px}
    </style><article><div class="label">СТРАТЕГ ФАБРИКИ ПРОДУКТОВ · МАТЕРИАЛЫ ПРОЕКТА</div>
    <h1>${escape(panel.title)}</h1><div class="path">${escape(panel.path)}${panel.first_line ? ' · с строки ' + panel.first_line : ''}</div>
    <pre>${escape(panel.id === '06-resume' ? '$ ' + data.resume.command + '\n\n' + JSON.stringify({status:actual.status,next:actual.next,pending:actual.pending},null,2) + '\n\nПоказаны поля status, next и pending из фактического stdout.\nПолный ответ сохранён в evidence.json.\nГраница проверки: ' + data.resume.scope : panel.text)}</pre><footer>Скриншот локального просмотра сохранённых артефактов и фактических результатов команд.<br>Не запись чата или интерфейса IDE. Дата захвата: ${escape(data.captured_at_utc)}.</footer></article></html>`;
    const source = path.join(out, panel.id + '.html');
    fs.writeFileSync(source, html);
    await page.goto(pathToFileURL(source).href);
    await page.locator('article').screenshot({path: path.join(out, panel.id + '.png')});
    captures.push({id:panel.id, html:panel.id+'.html', image:panel.id+'.png'});
  }
  await browser.close();
  fs.writeFileSync(path.join(out,'screenshots.json'),JSON.stringify(captures,null,2)+'\n');
  console.log('Captured ' + captures.length + ' source and command panels');
})().catch(error => { console.error(error); process.exit(1); });
