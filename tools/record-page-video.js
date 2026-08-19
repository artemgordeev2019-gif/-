#!/usr/bin/env node
/**
 * Записывает страницу в видео через Playwright + ffmpeg.
 *
 * Встроенный экспорт падал на `executeJavaScript timed out (5s)`: он ждёт
 * ответа от страницы, а страница в этот момент держит главный поток (распаковка
 * бандла, вёрстка, первый кадр canvas). Здесь ожидания нет вовсе — браузер
 * пишет screencast сам, а мы только ведём сценарий кликами и режем результат.
 *
 * Пример:
 *   node tools/record-page-video.js \
 *     --url file:///abs/path/page.html \
 *     --width 2088 --height 1164 \
 *     --crop "#dc-root [data-dc-tpl] [data-dc-tpl]" \
 *     --click "#dc-root button" --dwell 3200 \
 *     --out out.mp4
 */
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function args(argv) {
  const o = {};
  for (let i = 0; i < argv.length; i += 2) o[argv[i].replace(/^--/, '')] = argv[i + 1];
  return o;
}

/** ffmpeg от Playwright умеет только VP8 — для mp4 нужен билд с libx264. */
function findFfmpeg() {
  try { return require('ffmpeg-static'); } catch { /* нет пакета */ }
  for (const c of ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg']) if (fs.existsSync(c)) return c;
  return null;
}

(async () => {
  const a = args(process.argv.slice(2));
  if (!a.url) { console.error('нужен --url'); process.exit(2); }

  const W = +(a.width || 1920), H = +(a.height || 1080);
  const dwell = +(a.dwell || 3200);
  const settle = +(a.settle || 2500);      // сколько дать странице на распаковку и первый кадр
  const out = path.resolve(a.out || 'page-video.mp4');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pagevid-'));

  const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--hide-scrollbars'] });
  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
    recordVideo: { dir, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();

  const t0 = Date.now();
  await page.goto(a.url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(settle);

  if (a.patch) await page.evaluate(fs.readFileSync(path.resolve(a.patch), 'utf8'));

  /* Кроп берём по реальному прямоугольнику элемента: страница может быть
     резиновой, и жёсткие числа разъедутся на другом размере окна. */
  let crop = null;
  if (a.crop) {
    crop = await page.evaluate(sel => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const even = n => Math.round(n) - (Math.round(n) % 2);
      return { x: Math.round(r.x), y: Math.round(r.y), w: even(r.width), h: even(r.height) };
    }, a.crop);
  }

  /* Клики ведём из страницы (el.click()), а не мышью: курсор не наводится на
     карточки и в кадр не попадает чужой hover. */
  let start = Date.now() - t0;
  if (a.click) {
    const els = await page.$$(a.click);
    const targets = a.limit ? els.slice(0, +a.limit) : els;
    await targets[0].evaluate(el => el.click());
    start = Date.now() - t0;
    await page.waitForTimeout(dwell);
    for (const el of targets.slice(1)) {
      await el.evaluate(e => e.click());
      await page.waitForTimeout(dwell);
    }
    await targets[0].evaluate(el => el.click());
    await page.waitForTimeout(dwell);
  } else {
    await page.waitForTimeout(+(a.seconds || 20) * 1000);
  }

  /* запись обрывается на закрытии контекста, поэтому даём ей догнать сценарий */
  await page.waitForTimeout(1200);
  await ctx.close();
  await browser.close();

  const webm = path.join(dir, fs.readdirSync(dir).find(f => f.endsWith('.webm')));
  const ff = findFfmpeg();
  if (!ff) {
    fs.copyFileSync(webm, out.replace(/\.mp4$/, '.webm'));
    console.log('ffmpeg с libx264 не найден, отдаю исходный webm');
    return;
  }

  const vf = crop ? [`crop=${crop.w}:${crop.h}:${crop.x}:${crop.y}`] : [];
  execFileSync(ff, [
    '-hide_banner', '-loglevel', 'error', '-y',
    /* screencast стартует уже после начала навигации, поэтому смещение,
       посчитанное от запуска, само по себе съедает загрузку и первый переход */
    '-ss', String((start / 1000).toFixed(2)),
    '-i', webm,
    ...(vf.length ? ['-vf', vf.join(',')] : []),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an',
    out,
  ], { stdio: 'inherit' });
  fs.rmSync(dir, { recursive: true, force: true });
  console.log(out);
})();
