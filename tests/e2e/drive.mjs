// 실사용 점검: 회원처럼 화면을 누르며 끝까지 간다. 실제 유튜브 데이터. 사파리 엔진(webkit).
import { webkit } from 'playwright';
import fs from 'fs';
const OUT = 'e2e_out'; fs.mkdirSync(OUT, { recursive: true });
const rep = { steps: [], errors: [], badRequests: [] };
const t0 = Date.now(); const T = () => Math.round((Date.now() - t0) / 1000);
const b = await webkit.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 820 } });
p.on('pageerror', e => rep.errors.push('JS ' + e.message));
p.on('response', r => { if (r.status() >= 400 && !r.url().includes('ytimg')) rep.badRequests.push(r.status() + ' ' + r.url()); });
await p.addInitScript(() => {
  const call = (n) => async (...a) => { const r = await (await fetch('/api/' + n, { method: 'POST', body: JSON.stringify(a) })).json(); if (!r.ok) throw new Error(r.err); return r.res; };
  window.pywebview = { api: new Proxy({}, { get: (_, n) => call(n) }) };
  window.addEventListener('DOMContentLoaded', () => setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 50));
});
const save = () => fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(rep, null, 2));
const shot = async (n) => { await p.screenshot({ path: `${OUT}/${n}.png`, fullPage: true }); rep.steps.push([T(), n]); save(); };
const step = async (n, fn) => { try { await fn(); } catch (e) { rep.errors.push(n + ': ' + e.message.split('\n')[0]); await shot('ERR_' + n); } };
for (let i = 0; i < 30; i++) { try { await p.goto('http://127.0.0.1:8765/index.html'); break; } catch (e) { rep.errors.push('goto ' + i + ': ' + e.message.split('\n')[0]); await new Promise(r => setTimeout(r, 2000)); } } await p.waitForTimeout(1500); await shot('01_start');
await step('setup', async () => {
  await p.fill('#myCh', 'https://www.youtube.com/@유튜브-잡스');
  const models = ['https://www.youtube.com/@ThinkMediaPodcast', 'https://www.youtube.com/@vidIQ', 'https://www.youtube.com/@ColinandSamir', 'https://www.youtube.com/@DanHenry'];
  for (let i = 0; i < models.length; i++) { let ins = await p.$$('#models input'); if (!ins[i]) { await p.click('#addModel'); ins = await p.$$('#models input'); } await ins[i].fill(models[i]); }
  await p.fill('#intro', '회사 다니며 유튜브를 시작해 6개월 동안 수익 0원이었다. 사장님·창업가 인터뷰 채널을 30만 규모로 운영했다. 지금은 유튜브 운영 대행·컨설팅을 하고 유료 커뮤니티에서 강의를 판다.');
  await p.fill('#aud', '유튜브로 지식 상품을 팔고 싶은 30~50대 / 유튜브 운영 강의');
  for (const f of ['해외 유튜브 성공 사례 가져오기', '유튜브 수익화']) { await p.fill('#fmtEdit .tgin', f); await p.press('#fmtEdit .tgin', 'Enter'); }
  await shot('02_setup_filled');
  await p.click('#runBtn'); await p.waitForTimeout(4000); await shot('03_progress');
});
await step('analysis', async () => {
  for (let i = 0; i < 1200; i++) { await p.waitForTimeout(1000); if (await p.isVisible('#s-bench') || await p.isVisible('#perr')) break; if (i % 60 === 0) await shot('03_progress_' + i); }
  rep.analysisSeconds = T();
  if (await p.isVisible('#perr')) { rep.errors.push('분석 실패: ' + await p.textContent('#perrMsg')); await shot('ERR_analysis'); return; }
  await p.waitForTimeout(2500); await shot('04_bench');
  rep.keywords = await p.$$eval('#kwEdit .tg', e => e.map(x => x.textContent.replace('×', '').trim()));
  rep.roles = await p.$$eval('#rlist .ych b', e => e.map(x => x.textContent));
  rep.bench = await p.$$eval('#blist .ych', e => e.map(x => x.innerText.split('\n').slice(0, 3).join(' | ')));
});
await step('refs', async () => {
  await p.click('.nav[data-nav="refs"]'); await p.waitForTimeout(3000); await shot('05_refs');
  rep.refCount = await p.textContent('#refN'); rep.refs = await p.$$eval('.card', e => e.map(x => x.innerText.replace(/\n/g, ' | ')));
});
await step('plan', async () => {
  if (!(await p.$('.card'))) { rep.errors.push('레퍼런스 0편이라 기획하기를 못 눌렀어요'); return; }
  await p.hover('.card .tw'); await p.waitForTimeout(500); await shot('06_hover');
  await p.click('.card [data-plan]'); await p.waitForTimeout(1500); await shot('07_plan');
  await p.fill('#story', '이 영상에서 말하는 핵심에 동의한다. 나도 처음 6개월은 수익이 0원이었고, 조회수보다 내 상품을 사는 사람을 모으는 게 중요하다는 걸 늦게 알았다. 우리 시청자에게는 첫 영상부터 상품과 연결되는 주제를 고르라고 말해 주고 싶다.');
  await p.click('#mkMat');
  for (let i = 0; i < 120; i++) { await p.waitForTimeout(1000); const m = await p.textContent('#matMsg'); if (m && !m.includes('가져오는 중')) break; }
  rep.materialMsg = await p.textContent('#matMsg'); await shot('08_material');
  if (fs.existsSync(`${OUT}/copied.md`)) { const c = fs.readFileSync(`${OUT}/copied.md`, 'utf8'); rep.materialChars = c.length;
    rep.materialHas = { 경험노트: c.includes('## 내 경험 노트'), 내이야기: c.includes('내 이야기'), 자막: c.includes('### 자막'), 댓글: c.includes('### 댓글') };
    rep.experienceLines = (c.split('## 내 경험 노트')[1] || '').split('##')[0].trim().split('\n').slice(0, 12); }
  await p.fill('#paste', '# 점검용 기획안\n\n## 대본 (그대로 읽는 용)\n### 훅 · 0:00\n점검용 문장입니다. **내 이야기 문장**\n\n| 항목 | 내용 |\n|---|---|\n| 포맷 | 점검 |\n');
  await p.click('#savePlan'); await p.waitForTimeout(1500); await shot('09_plan_saved');
});
await step('settings', async () => { await p.click('.nav[data-nav="settings"]'); await p.waitForTimeout(800); await shot('10_settings'); });
await step('plans', async () => { await p.click('.nav[data-nav="plans"]'); await p.waitForTimeout(1000); await shot('11_plans'); });
rep.totalSeconds = T(); fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(rep, null, 2)); console.log(JSON.stringify(rep, null, 2));
await b.close();
