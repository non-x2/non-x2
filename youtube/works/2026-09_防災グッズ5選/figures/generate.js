/**
 * 図解を作りなおすスクリプト（【買ってはいけない防災グッズ5選】用）
 *
 * つかいかた：
 *   node youtube/works/2026-09_防災グッズ5選/figures/generate.js
 *
 * このフォルダに 1920×1080 のPNGが書き出されます。
 * 文字や数字を直したいときは、下の FIGURES の中身を書きかえてから、もう一度実行してください。
 *
 * ⚠️ 数字は 02_商品リサーチ比較シート.md で出典を確認したものだけを使っています。
 *    勝手に増やしたり丸めたりしないでください。
 */

const path = require('path');
const { chromium } = require('playwright');

const OUT_DIR = __dirname;
const W = 1920;
const H = 1080;

/* ============================ 共通のみため ============================ */
/* チャンネルの色：暗い背景 × 赤い帯 × 黄色の数字（公開済み動画と同じ） */
const CSS = `
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:${W}px; height:${H}px; overflow:hidden;
    font-family:"IPAPGothic","IPAGothic",sans-serif;
    background:linear-gradient(160deg,#0b1020 0%,#121a33 55%,#1a2340 100%);
    color:#fff; -webkit-font-smoothing:antialiased;
  }
  .frame { width:100%; height:100%; padding:64px 80px; display:flex; flex-direction:column; }
  .kicker { font-size:34px; color:#9aa7c7; letter-spacing:.04em; }
  .title { font-size:76px; font-weight:bold; line-height:1.15; margin-top:6px; }
  .title .hl { color:#ffd43b; }
  .body { flex:1; display:flex; align-items:center; gap:56px; margin-top:34px; }
  .src {
    margin-top:auto; padding-top:22px; font-size:26px; color:#7f8db0;
    border-top:2px solid rgba(255,255,255,.12);
  }
  /* 赤い帯の上の大きな数字 */
  .bignum { background:#e03131; border-radius:22px; padding:26px 40px; text-align:center;
            box-shadow:0 14px 40px rgba(224,49,49,.35); }
  .bignum .n { font-size:170px; font-weight:bold; color:#ffd43b; line-height:1; letter-spacing:-.02em; }
  .bignum .n small { font-size:76px; margin-left:8px; }
  .bignum .cap { font-size:32px; margin-top:12px; color:#fff; }
  /* 携帯トイレ1個ぶんのアイコン（袋のイメージ） */
  .pouch { width:44px; height:56px; border-radius:7px; background:#cfd8ef;
           border:2px solid #9fb0d8; position:relative; }
  .pouch::before { content:""; position:absolute; left:6px; right:6px; top:6px; height:9px;
                   background:#8fa2cd; border-radius:3px; }
  .pouch::after  { content:""; position:absolute; left:9px; right:9px; top:24px; height:4px;
                   background:#aebbdb; border-radius:2px; box-shadow:0 9px 0 #aebbdb; }
  .grid { display:grid; grid-template-columns:repeat(20,1fr); gap:10px; align-content:end; }
`;

/* 携帯トイレのアイコンを n 個ならべる */
const pouches = (n) => `<div class="grid">${'<div class="pouch"></div>'.repeat(n)}</div>`;

/* ============================ 図の中身 ============================ */
const FIGURES = [

/* ---- ① 山場：60個 → 140個（この2枚は続けて切り替えると「山が育つ」） ---- */
{
  file: '01a_携帯トイレ60個.png',
  html: `
    <div class="frame">
      <div class="kicker">4人家族に必要な携帯トイレ</div>
      <div class="title">まずは <span class="hl">3日分</span></div>
      <div class="body">
        <div style="flex:1;height:470px;display:flex;align-items:flex-end;">${pouches(60)}</div>
        <div class="bignum"><div class="n">60<small>個</small></div><div class="cap">最低限（3日分）</div></div>
      </div>
      <div class="src">出典：東京都「広報東京都 2025年9月号」／1日5個 × 3日分 × 4人 ＝ 60個</div>
    </div>`,
},
{
  file: '01b_携帯トイレ140個.png',
  html: `
    <div class="frame">
      <div class="kicker">4人家族に必要な携帯トイレ</div>
      <div class="title">都の“おすすめ”は <span class="hl">1週間分</span></div>
      <div class="body">
        <div style="flex:1;height:470px;display:flex;align-items:flex-end;">${pouches(140)}</div>
        <div class="bignum"><div class="n">140<small>個</small></div><div class="cap">おすすめ（1週間分）</div></div>
      </div>
      <div class="src">出典：東京都「広報東京都 2025年9月号」／1日5個 × 7日分 × 4人 ＝ 140個</div>
    </div>`,
},

/* ---- ② 判決一覧（まとめで使う） ---- */
{
  file: '02_判決一覧.png',
  html: (() => {
    const rows = [
      ['①', '激安の手回し充電ラジオライト', 'gray',  '条件付きシロ', '明かりとラジオは優秀。充電は“おまけ”'],
      ['②', '完成品の防災リュック',        'gray',  '条件付きシロ', '開けていないなら実質クロ'],
      ['③', '激安ポータブル電源',          'black', 'クロ',        '確認できない相手は家に置けない'],
      ['④', '「水と食料だけ」の備え',      'black', 'クロ',        'トイレが抜けている（4人で60個）'],
      ['⑤', 'カイロ・ボンベの買いだめ',    'white', 'シロ',        '買うより「入れ替える」'],
    ].map(([no, name, kind, verdict, why]) => {
      const style = kind === 'black'
        ? 'background:#e03131;color:#fff;'
        : kind === 'white'
          ? 'background:#f1f4fb;color:#12203f;'
          : 'background:#f1f4fb;color:#12203f;border:4px solid #f59f00;';
      return `
        <div style="display:flex;align-items:center;gap:26px;padding:17px 26px;border-radius:16px;
                    background:rgba(255,255,255,.055);">
          <div style="font-size:40px;color:#ffd43b;width:44px;">${no}</div>
          <div style="font-size:38px;flex:1;">${name}</div>
          <div style="${style}font-size:33px;font-weight:bold;padding:9px 22px;border-radius:11px;
                      width:290px;text-align:center;">${verdict}</div>
          <div style="font-size:27px;color:#9aa7c7;width:520px;">${why}</div>
        </div>`;
    }).join('');
    return `
      <div class="frame">
        <div class="kicker">選び方特捜部</div>
        <div class="title">判 決 一 覧</div>
        <div style="flex:1;display:flex;flex-direction:column;gap:13px;margin-top:28px;
                    justify-content:center;">${rows}</div>
        <div class="src">買い足すなら“明かり”より先に“トイレ”。派手なグッズより、地味な消耗品が家族を救う。</div>
      </div>`;
  })(),
},

/* ---- ③ 買う前の5点確認（容疑者③） ---- */
{
  file: '03_買う前の5点確認.png',
  html: (() => {
    const items = [
      '販売事業者の<b style="color:#ffd43b">連絡先</b>が書いてあるか',
      '<b style="color:#ffd43b">製品情報</b>（定格電圧・容量・電池の種類）があるか',
      '<b style="color:#ffd43b">リコール情報</b>が出ていないか',
      '<b style="color:#ffd43b">表示マーク</b>が適切についているか',
      '<b style="color:#ffd43b">保証</b>の窓口が日本にあるか',
    ].map((t, i) => `
      <div style="display:flex;align-items:center;gap:30px;padding:20px 30px;border-radius:16px;
                  background:rgba(255,255,255,.055);">
        <div style="width:66px;height:66px;border-radius:50%;background:#e03131;color:#fff;
                    font-size:38px;font-weight:bold;display:flex;align-items:center;
                    justify-content:center;flex:none;">${i + 1}</div>
        <div style="font-size:40px;">${t}</div>
      </div>`).join('');
    return `
      <div class="frame">
        <div class="kicker">激安ポータブル電源を買う前に</div>
        <div class="title"><span class="hl">確認できない</span>なら、選ばない</div>
        <div style="flex:1;display:flex;flex-direction:column;gap:15px;margin-top:30px;
                    justify-content:center;">${items}</div>
        <div class="src">出典：NITE 独立行政法人 製品評価技術基盤機構「3つのC」より（2026年7月）</div>
      </div>`;
  })(),
},

/* ---- ④ 1人用3日分 × 4人 ＝ 4つ（容疑者②） ---- */
{
  file: '04_リュックは人数分.png',
  html: (() => {
    const bag = (s = 1) => `
      <div style="width:${104 * s}px;height:${128 * s}px;border-radius:${18 * s}px;
                  background:#cfd8ef;border:${3 * s}px solid #9fb0d8;position:relative;">
        <div style="position:absolute;left:50%;top:${-13 * s}px;transform:translateX(-50%);
                    width:${52 * s}px;height:${26 * s}px;border:${5 * s}px solid #9fb0d8;
                    border-bottom:none;border-radius:${26 * s}px ${26 * s}px 0 0;"></div>
        <div style="position:absolute;left:${16 * s}px;right:${16 * s}px;top:${44 * s}px;
                    height:${34 * s}px;background:#8fa2cd;border-radius:${7 * s}px;"></div>
      </div>`;
    const person = () => `
      <div style="display:flex;flex-direction:column;align-items:center;gap:5px;">
        <div style="width:34px;height:34px;border-radius:50%;background:#ffd43b;"></div>
        <div style="width:52px;height:56px;border-radius:16px 16px 9px 9px;background:#ffd43b;"></div>
      </div>`;
    return `
      <div class="frame">
        <div class="kicker">完成品の防災リュック</div>
        <div class="title">市販の1つは、たいてい <span class="hl">1人用・3日分</span></div>
        <div class="body" style="justify-content:center;gap:44px;">
          <div style="text-align:center;">
            ${bag(1)}
            <div style="font-size:28px;color:#9aa7c7;margin-top:22px;">1人用・3日分</div>
          </div>
          <div style="font-size:88px;color:#ffd43b;">×</div>
          <div style="text-align:center;">
            <div style="display:flex;gap:16px;">${person()}${person()}${person()}${person()}</div>
            <div style="font-size:28px;color:#9aa7c7;margin-top:22px;">家族4人</div>
          </div>
          <div style="font-size:88px;color:#ffd43b;">＝</div>
          <div style="text-align:center;">
            <div style="display:flex;gap:14px;">${bag(0.72)}${bag(0.72)}${bag(0.72)}${bag(0.72)}</div>
            <div style="font-size:36px;color:#ffd43b;margin-top:22px;font-weight:bold;">4つ必要</div>
          </div>
        </div>
        <div class="src">出典：農林水産省「災害時に備えた食品ストックガイド」／最低3日分〜1週間分 × 人数分</div>
      </div>`;
  })(),
},

/* ---- ⑤ 4つの箱：トイレだけ空（容疑者④の入口） ---- */
{
  file: '05_トイレだけ空.png',
  html: (() => {
    const box = (label, filled) => `
      <div style="text-align:center;">
        <div style="width:300px;height:280px;border-radius:22px;
                    ${filled
                      ? 'background:rgba(255,255,255,.09);border:4px solid rgba(255,255,255,.28);'
                      : 'background:rgba(224,49,49,.10);border:5px dashed #e03131;'}
                    display:flex;align-items:center;justify-content:center;">
          <div style="font-size:${filled ? 108 : 128}px;color:${filled ? '#cfd8ef' : '#e03131'};
                      font-weight:bold;">${filled ? '✓' : '×'}</div>
        </div>
        <div style="font-size:38px;margin-top:20px;color:${filled ? '#fff' : '#ff8787'};
                    font-weight:${filled ? 'normal' : 'bold'};">${label}</div>
      </div>`;
    return `
      <div class="frame">
        <div class="kicker">完璧に見える、この備え</div>
        <div class="title">大穴が空いています — <span class="hl">トイレ</span></div>
        <div class="body" style="justify-content:center;gap:40px;">
          ${box('水', true)}${box('食料', true)}${box('明かり', true)}${box('トイレ', false)}
        </div>
        <div class="src">断水・停電で、まず困るのは「食べること」ではなく「出すこと」。しかも我慢できない。</div>
      </div>`;
  })(),
},

/* ---- ⑥ 買い足す順番（まとめ） ---- */
{
  file: '06_買い足す順番.png',
  html: (() => {
    const rows = [
      ['1', '携帯トイレ',            '4人家族で 最低60個／おすすめ140個', true],
      ['2', '水・食料',              '最低3日分〜1週間分 × 人数',        false],
      ['3', '明かり（電池式）',      '—',                                false],
      ['4', '電源（ポータブル電源）','買うなら「5点確認」してから',      false],
    ].map(([no, name, note, top]) => `
      <div style="display:flex;align-items:center;gap:30px;padding:19px 30px;border-radius:16px;
                  background:${top ? 'rgba(224,49,49,.16)' : 'rgba(255,255,255,.055)'};
                  ${top ? 'border:3px solid #e03131;' : ''}">
        <div style="width:64px;height:64px;border-radius:50%;flex:none;display:flex;
                    align-items:center;justify-content:center;font-size:36px;font-weight:bold;
                    background:${top ? '#e03131' : 'rgba(255,255,255,.14)'};color:#fff;">${no}</div>
        <div style="font-size:44px;flex:1;${top ? 'color:#ffd43b;font-weight:bold;' : ''}">${name}</div>
        <div style="font-size:30px;color:#9aa7c7;width:640px;">${note}</div>
      </div>`).join('');
    return `
      <div class="frame">
        <div class="kicker">今日からの</div>
        <div class="title">買い足す <span class="hl">順番</span></div>
        <div style="flex:1;display:flex;flex-direction:column;gap:15px;margin-top:28px;
                    justify-content:center;">
          ${rows}
          <div style="display:flex;align-items:center;gap:30px;padding:19px 30px;border-radius:16px;
                      background:rgba(255,212,59,.12);border:3px solid rgba(255,212,59,.5);">
            <div style="width:64px;height:64px;border-radius:50%;flex:none;display:flex;
                        align-items:center;justify-content:center;font-size:26px;font-weight:bold;
                        background:#ffd43b;color:#12203f;">今</div>
            <div style="font-size:44px;flex:1;">期限の入れ替え</div>
            <div style="font-size:30px;color:#9aa7c7;width:640px;">ボンベ7年・こんろ本体10年</div>
          </div>
        </div>
        <div class="src">出典：東京都（トイレ）／農林水産省（水・食料）／岩谷産業（ボンベ・こんろ）</div>
      </div>`;
  })(),
},
];

/* ============================ 書き出し ============================ */
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  for (const fig of FIGURES) {
    await page.setContent(
      `<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>${CSS}</style></head>` +
      `<body>${fig.html}</body></html>`,
      { waitUntil: 'load' }
    );
    const out = path.join(OUT_DIR, fig.file);
    await page.screenshot({ path: out });
    console.log('✅ ' + fig.file);
  }
  await browser.close();
  console.log(`\n${FIGURES.length}枚を ${OUT_DIR} に書き出しました。`);
})();
