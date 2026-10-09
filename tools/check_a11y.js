// 👀 見やすさ点検（色のコントラスト・押しやすさ・狭い画面のはみ出し）
//
// のんラボの公開ページが「誰にとっても見やすいか」を、実際のブラウザで測る道具です。
// 目で見ても分かりにくい3つを、数字で確かめます。
//
//   ① 色のコントラスト … 文字と背景の明るさの差。小さいと読みづらい
//        基準（WCAG 2.1 AA）：ふつうの文字 4.5:1 ／ 大きい文字 3:1
//   ② 押しやすさ       … ボタンの大きさ（縦と横の短いほう）。指で押すには 44px 以上がめやす
//   ③ はみ出し         … 画面が狭いとき、横スクロールが出てしまわないか
//
// ------------------------------------------------------------------
// 使い方（クラウドの作業部屋でもローカルでも同じ）
//
//   npm install playwright          # 初回だけ。ブラウザ本体は落とさなくてOK
//   npm run check:a11y              # これだけ（= node tools/check_a11y.js）
//
//   🚚 **ページを配る係は、この道具が自分で立てて、終わったら片づけます**。
//      以前は先に「python3 -m http.server 8898」を手で動かしておく必要があり、
//      忘れると4ページとも「開けませんでした」で全部❌になりました（2026-10-03 に実際に発生）。
//      いまは何も要りません。もし自分で配る係を動かしていたら、そちらをそのまま使います
//      （番号が使用中なら立てずに相乗りする＝GitHub Actions もこの形で動いています）。
//
//   ☁️ クラウドの作業部屋には Chromium が最初から入っています。
//      その場合は自動で /opt/pw-browsers/chromium を使います（追加のダウンロード不要）。
//   ページを足したいときは、下の ALL_PAGES に1行足すだけです。
//
//   1ページだけ測りたいとき（直したページだけ測り直す）
//        ONLY=world npm run check:a11y     # 🌍 世界のライブカメラだけ
//        ONLY=bousai npm run check:a11y    # 🛟 防災情報だけ
//
//   別の場所に配ってあるものを測りたいとき（めったに使いません）
//        BASE=http://localhost:9999 npm run check:a11y   # 自分で立てた係を使う
//        PORT=9000 npm run check:a11y                    # 立てる番号だけ変える
// ------------------------------------------------------------------

const fs = require('fs');
const http = require('http');
const nodePath = require('path');
const { chromium } = require('playwright');

const PORT = Number(process.env.PORT) || 8898;
// BASE を自分で指定したときは、その場所を測ります（配る係は立てません）。
const BASE = process.env.BASE || `http://localhost:${PORT}`;
const ROOT = nodePath.resolve(__dirname, '..');   // リポジトリのいちばん上

// ---- 🚚 ページを配る小さな係（この道具の中だけで使う簡易サーバー） ----
// 役目は「リポジトリの中のファイルを、ブラウザから見えるようにする」だけです。
// 外には出さず（127.0.0.1 = この機械の中だけ）、点検が終わったら片づけます。
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
};
const startServer = () => new Promise((resolve) => {
  const server = http.createServer((req, res) => {
    let rel;
    try {
      rel = decodeURIComponent(String(req.url).split('?')[0]);
    } catch (e) {
      res.writeHead(400); res.end(); return;
    }
    if (rel.endsWith('/')) rel += 'index.html';          // 「/typhoon-app/」→ index.html
    const file = nodePath.join(ROOT, nodePath.normalize(rel));
    if (file !== ROOT && !file.startsWith(ROOT + nodePath.sep)) {  // リポジトリの外は出さない
      res.writeHead(403); res.end(); return;
    }
    fs.readFile(file, (err, buf) => {
      if (err) { res.writeHead(404); res.end('not found'); return; }
      res.writeHead(200, {
        'Content-Type': MIME[nodePath.extname(file).toLowerCase()] || 'application/octet-stream',
      });
      res.end(buf);
    });
  });
  // すでに同じ番号で誰かが配っているとき（手で動かした・GitHub Actions が動かした）は、
  // 立てずにそちらへ相乗りします。昔からの使い方をこわさないための気配りです。
  server.on('error', () => resolve(null));
  server.listen(PORT, '127.0.0.1', () => {
    server.unref();      // この係のせいでプログラムが終われなくならないように
    resolve(server);
  });
});
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

  // 「実際に指で押せる大きさ」を、縦と横の両方で測ります。
  //
  // のんラボには、見た目を1ドットも変えずに“透明な当たり判定だけ”を広げている場所が
  // あります（出典の行内リンク＝ ::before / ::after を使う手法）。
  // 見た目の大きさだけで判定すると、こうした工夫を「押しにくい」と誤って報告してしまうので、
  // 「その位置を押したらこの部品に当たるか」を上下・左右に1pxずつ実際に試して確かめます。
  //
  // 縦と横を**両方**測るのが大事です。指は丸いので、細長い部品は押しにくいからです。
  //   例）横200px・縦20pxのボタンは、横は十分でも指では押しにくい
  //       丸いボタンは、縦だけ測ると本当の押しやすさが分からない
  // そこで「縦と横の**短いほう**」を、その部品の押しやすさとして扱います。
  // 測れないとき（画面の外・何かに隠れている）は null を返し、見た目の大きさで判定します。
  const tapSize = (el) => {
    el.scrollIntoView({ block: 'center' });   // 押せるか試すため、いったん画面の中央へ
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return null;
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    if (cx < 0 || cx > innerWidth - 1) return null;
    const hits = (x, y) => {
      if (x < 0 || x > innerWidth - 1 || y < 0 || y > innerHeight - 1) return false;
      const e = document.elementFromPoint(x, y);
      return e === el || (!!e && el.contains(e));   // 自分か、自分の中身に当たればOK
    };
    if (!hits(cx, cy)) return null;   // 真ん中すら当たらない＝何かに隠れている
    // 中心から外へ1pxずつ、当たらなくなるまで伸ばして「はみ出しぶん」を数えます
    const grow = (at) => {
      let n = 0;
      for (let d = 1; d <= 24; d++) { const p = at(d); if (hits(p.x, p.y)) n = d; else break; }
      return n;
    };
    const up    = grow((d) => ({ x: cx, y: r.top - d }));
    const down  = grow((d) => ({ x: cx, y: r.bottom + d }));
    const left  = grow((d) => ({ x: r.left - d, y: cy }));
    const right = grow((d) => ({ x: r.right + d, y: cy }));
    return { h: r.height + up + down, w: r.width + left + right };
  };

  return Array.from(document.querySelectorAll(sel)).map((el) => {
    const cs = getComputedStyle(el);
    const bg = resolveBg(el);
    const r = el.getBoundingClientRect();
    // 押して使うもの（ボタン・タブ・一覧のリンク）だけ「押しやすさ」を測ります。
    // 文章の中のリンクは「読むためのもの」なので、大きさの対象にしません。
    const tappable = el.matches('button, [role="tab"], .link-list a');
    return {
      label: (el.textContent || '').trim().slice(0, 24),
      color: cs.color,
      bgRgb: bg.rgb || null,
      unmeasurable: !!bg.unmeasurable,
      size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight, 10) || 400,
      h: r.height, w: r.width, visible: r.width > 0 && r.height > 0,
      tappable,
      tap: tappable && r.width > 0 && r.height > 0 ? tapSize(el) : null,
    };
  });
};

(async () => {
  // 🚚 まずページを配る係を用意します（BASE 指定のときは何もしません）
  const server = process.env.BASE ? null : await startServer();
  console.log(server
    ? `🚚 ページを配る係を立てました（${BASE}／点検が終わったら片づけます）`
    : `🚚 すでに動いている配る係を使います（${BASE}）`);

  const exe = fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined;
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  let ng = 0;

  for (const [name, path] of PAGES) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    try {
      await page.goto(BASE + '/' + path, { waitUntil: 'domcontentloaded', timeout: 20000 });
    } catch (e) {
      console.log(`\n===== ${name} =====\n  ❌ ページを開けませんでした（${BASE}/${path}）`);
      console.log(server
        ? '     配る係は立っているので、ページのファイルが見つからないのかもしれません。'
        : `     ${PORT} 番は別のものが使っているようです。PORT=9000 npm run check:a11y で番号を変えられます。`);
      await page.close();
      ng++;
      continue;
    }
    await page.waitForTimeout(1200);
    console.log(`\n===== ${name} =====`);

    // ① 色のコントラスト＋② 押しやすさ
    const items = await page.evaluate(collect, '[role="tab"], button, .link-list a, .note a');
    let worst = null, skipped = 0, widened = 0;
    const small = [], thin = new Set();
    for (const it of items) {
      if (!it.visible) continue;
      if (it.tappable && it.h > 0) {
        // 透明な当たり判定を広げているものは、その「実際に押せる大きさ」で判定します
        const effH = it.tap ? it.tap.h : it.h;
        const effW = it.tap ? it.tap.w : it.w;
        const eff = Math.min(effH, effW);   // 細長いと押しにくいので、短いほうで見る
        const isWide = !!it.tap && (it.tap.h > it.h + 0.5 || it.tap.w > it.w + 0.5);
        if (isWide) widened++;
        if (eff < TAP_MIN) {
          small.push(`「${it.label || '(文字なし)'}」${eff.toFixed(0)}px` +
                     `（横${effW.toFixed(0)}×縦${effH.toFixed(0)}）` +
                     (isWide ? `（見た目 ${it.w.toFixed(0)}×${it.h.toFixed(0)}px）` : ''));
        }
      }
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
    const widenNote = widened ? `　※うち ${widened} 個は透明な当たり判定で広げてあります` : '';
    console.log(small.length
      ? `  ② 押しやすさ: ${TAP_MIN}px より低いものが ${small.length} 個 ⚠️ … ${small.slice(0, 4).join('、')}${widenNote}`
      : `  ② 押しやすさ: すべて ${TAP_MIN}px 以上 ✅${widenNote}`);
    if (small.length) {
      // ⚠️ を見て慌てて「直そう」としないための注意書きです（過去に一度、直す必要のない
      // ものを直しかけました）。押した先を別の層で振り分けている部品は、この測り方
      // （その1点を押したら何に当たるか）では本当の押しやすさが分かりません。
      console.log('     ↑ 交通ページの「交通量の丸」は、押した場所からいちばん近い丸へ' +
                  '開く先を振り分ける方式（PR #79）なので、実際はこの数字より押しやすいです。');
    }

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
  if (server) { server.closeAllConnections?.(); server.close(); }   // 🚚 配る係を片づける
  console.log(ng === 0
    ? '\n✅ すべて基準を満たしています（⚠️ の押しやすさは「読むためのリンク」なら問題ありません）'
    : `\n❌ 気になるところが ${ng} 件ありました。上の行をご覧ください`);

  // 🤖 自動で回すとき（GitHub Actions）に、❌ を「失敗」として拾えるようにします。
  //    数えているのは ①色が薄い ③はみ出し ＋ ページにつながらなかった場合だけ。
  //    ②押しやすさは、上の注意書きのとおり「直す必要のないもの」が混じるので
  //    ⚠️ の表示だけにとどめ、失敗にはしません（この方針は変えないこと）。
  process.exitCode = ng === 0 ? 0 : 1;
})();
