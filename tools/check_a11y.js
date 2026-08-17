// 👀 見やすさ点検（色のコントラスト・押しやすさ・狭い画面のはみ出し）
//
// のんラボの公開ページが「誰にとっても見やすいか」を、実際のブラウザで測る道具です。
// 目で見ても分かりにくい3つを、数字で確かめます。
//
//   ① 色のコントラスト … 文字と背景の明るさの差。小さいと読みづらい
//        基準（WCAG 2.1 AA）：ふつうの文字 4.5:1 ／ 大きい文字 3:1
//   ② 押しやすさ       … ボタンの高さ。指で押すには 44px 以上がめやす
//   ③ はみ出し         … 画面が狭いとき、横スクロールが出てしまわないか
//
// ------------------------------------------------------------------
// 使い方（クラウドの作業部屋でもローカルでも同じ）
//
//   1) ページを配る係を動かす（リポジトリのいちばん上で）
//        python3 -m http.server 8898
//   2) 道具を動かす
//        npm install playwright          # 初回だけ。ブラウザ本体は落とさなくてOK
//        node tools/check_a11y.js
//
//   ☁️ クラウドの作業部屋には Chromium が最初から入っています。
//      その場合は自動で /opt/pw-browsers/chromium を使います（追加のダウンロード不要）。
//   ページを足したいときは、下の ALL_PAGES に1行足すだけです。
//
//   3) 1ページだけ測りたいとき（直したページだけ測り直す）
//        ONLY=world node tools/check_a11y.js     # 🌍 世界のライブカメラだけ
//        ONLY=bousai node tools/check_a11y.js    # 🛟 防災情報だけ
// ------------------------------------------------------------------

const fs = require('fs');
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://localhost:8898';
const ALL_PAGES = [
  ['🌀 台風情報', 'typhoon-app/'],
  ['🛟 防災情報', 'bousai-app/'],
  ['🚗 交通・ライブカメラ', 'traffic-app/'],
  ['🌍 世界のライブカメラ', 'world-livecam/'],
];
// 1ページだけ点検したいときは ONLY を使います。
//   例： ONLY=world node tools/check_a11y.js   → 🌍 世界のライブカメラだけ測る
// 名前か置き場所にその文字が入っているページだけを測ります（直したページだけ測り直したいときに便利）。
const PAGES = process.env.ONLY
  ? ALL_PAGES.filter(([name, path]) => `${name} ${path}`.includes(process.env.ONLY))
  : ALL_PAGES;
const NARROW = [320, 280];          // 測る画面の幅（いちばん狭いスマホを想定）
const TAP_MIN = 44;                 // 押しやすさのめやす（px）

// ---- 色の計算（WCAG 2.1 の式そのまま） ----
const luminance = (rgb) => {
  const [r, g, b] = rgb.map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const parseColor = (css) => {
  const m = String(css).match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const p = m[1].split(',').map((s) => parseFloat(s.trim()));
  return { rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1 };
};
const blend = (fg, bg) => (fg.a >= 1 ? fg.rgb : fg.rgb.map((v, i) => v * fg.a + bg[i] * (1 - fg.a)));
const contrast = (a, b) => {
  const l1 = luminance(a), l2 = luminance(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
};

// ページの中から「文字と背景の色・大きさ」を集めてくる係（ブラウザの中で動きます）
const collect = (sel) => {
  // 「実際に目に見えている背景の色」を求めます。
  //   ・半透明のときは、その下の色と混ぜます（親をさかのぼる）
  //   ・グラデーションや画像が背景のときは、場所によって色が違うので
  //     数字では測れません → unmeasurable（人の目で確かめる）
  const resolveBg = (node) => {
    if (!node) return { rgb: [255, 255, 255] };
    const cs = getComputedStyle(node);
    if (cs.backgroundImage && cs.backgroundImage !== 'none') return { unmeasurable: true };
    const m = String(cs.backgroundColor).match(/rgba?\(([^)]+)\)/);
    const p = m ? m[1].split(',').map((s) => parseFloat(s.trim())) : [0, 0, 0, 0];
    const a = p.length > 3 ? p[3] : 1;
    if (a >= 1) return { rgb: [p[0], p[1], p[2]] };
    const under = resolveBg(node.parentElement);
    if (under.unmeasurable) return under;
    return { rgb: [0, 1, 2].map((i) => p[i] * a + under.rgb[i] * (1 - a)) };
  };

  return Array.from(document.querySelectorAll(sel)).map((el) => {
    const cs = getComputedStyle(el);
    const bg = resolveBg(el);
    const r = el.getBoundingClientRect();
    return {
      label: (el.textContent || '').trim().slice(0, 24),
      color: cs.color,
      bgRgb: bg.rgb || null,
      unmeasurable: !!bg.unmeasurable,
      size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight, 10) || 400,
      h: r.height, visible: r.width > 0 && r.height > 0,
      // 押して使うもの（ボタン・タブ・一覧のリンク）だけ「押しやすさ」を測ります。
      // 文章の中のリンクは「読むためのもの」なので、大きさの対象にしません。
      tappable: el.matches('button, [role="tab"], .link-list a'),
    };
  });
};

(async () => {
  const exe = fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined;
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  let ng = 0;

  for (const [name, path] of PAGES) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    try {
      await page.goto(BASE + '/' + path, { waitUntil: 'domcontentloaded', timeout: 20000 });
    } catch (e) {
      console.log(`\n===== ${name} =====\n  ❌ ページを開けませんでした（${BASE}/${path}）`);
      console.log('     「python3 -m http.server 8898」を動かしましたか？');
      await page.close();
      ng++;
      continue;
    }
    await page.waitForTimeout(1200);
    console.log(`\n===== ${name} =====`);

    // ① 色のコントラスト＋② 押しやすさ
    const items = await page.evaluate(collect, '[role="tab"], button, .link-list a, .note a');
    let worst = null, skipped = 0;
    const small = [], thin = new Set();
    for (const it of items) {
      if (!it.visible) continue;
      if (it.tappable && it.h > 0 && it.h < TAP_MIN) small.push(`「${it.label || '(文字なし)'}」${it.h.toFixed(0)}px`);
      // 文字が入っていないもの（アイコンだけの飾りなど）は、色の読みやすさの対象外です
      if (!it.label) continue;
      // 背景がグラデーション・画像のところは、場所で色が変わるので数字では測れません
      if (it.unmeasurable || !it.bgRgb) { skipped++; continue; }
      const fg = parseColor(it.color);
      if (!fg) continue;
      const ratio = contrast(blend(fg, it.bgRgb), it.bgRgb);
      const big = it.size >= 24 || (it.size >= 18.66 && it.weight >= 700);
      const need = big ? 3 : 4.5;
      if (ratio < need) thin.add(`「${it.label}」${ratio.toFixed(2)}:1（必要 ${need}:1）`);
      if (!worst || ratio < worst.ratio) worst = { ratio, label: it.label, need };
    }
    thin.forEach((line) => { console.log(`  ❌ 色が薄い: ${line}`); ng++; });
    if (worst) {
      console.log(`  ① 色のコントラスト: いちばん低いところで ${worst.ratio.toFixed(2)}:1` +
                  `（「${worst.label}」／必要 ${worst.need}:1）${worst.ratio >= worst.need ? '✅' : '❌'}` +
                  (skipped ? `　※背景がグラデーションの ${skipped} 個は数字で測れないので目で確認を` : ''));
    }
    console.log(small.length
      ? `  ② 押しやすさ: ${TAP_MIN}px より低いものが ${small.length} 個 ⚠️ … ${small.slice(0, 4).join('、')}`
      : `  ② 押しやすさ: すべて ${TAP_MIN}px 以上 ✅`);

    // ③ 狭い画面のはみ出し
    for (const w of NARROW) {
      await page.setViewportSize({ width: w, height: 800 });
      await page.waitForTimeout(500);
      const over = await page.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth);
      console.log(`  ③ 幅${w}px のはみ出し: ${over}px ${over === 0 ? '✅' : '❌'}`);
      if (over !== 0) ng++;
    }
    await page.close();
  }

  await browser.close();
  console.log(ng === 0
    ? '\n✅ すべて基準を満たしています（⚠️ の押しやすさは「読むためのリンク」なら問題ありません）'
    : `\n❌ 気になるところが ${ng} 件ありました。上の行をご覧ください`);
})();
