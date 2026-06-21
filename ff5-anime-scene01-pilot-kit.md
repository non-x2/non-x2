# FF5 アニメ 試作 ─ 第1話アバン「封印の暁」PVシーン制作キット

> ※ファンメイドの「もしアニメ化したら」企画の試作素材。公式企画ではありません。原作 © SQUARE ENIX を尊重した非営利の創作メモです。
> 関連：[TVシリーズ企画書](./ff5-anime-adaptation.md) ／ [劇場版＆設定資料集](./ff5-anime-movie-and-worldbook.md)
>
> 🎨 **ビジュアル絵コンテ（AI静止画つき・Gamma）**：https://gamma.app/docs/cc93a9blitvt2x1
> ※10カットのキーフレームを2Dセルアニメ調で可視化した試作ビジュアル。本キットの§1絵コンテと対応。

---

## 0. このキットについて

「アニメ映像＋音声」を実際に作るための**1シーン分の試作設計図**。  
本リポジトリ環境では映像レンダリング／音声合成そのものは行えないため、**外部の生成AIに流し込めば完成する形**まで作り込んでいます。

- 対象シーン：**第1話 冒頭アバン「封印の暁」**（30年前、暁の4戦士がエクスデスを封じる回想）
- 尺：**約70秒**（10カット）
- 用途：PVのオープニング／本編アバンの試作

### 想定パイプライン
1. **静止画（キーフレーム）生成** … Midjourney / Stable Diffusion / NanoBanana 等で各カットの1枚絵を生成（§2のプロンプト）
2. **静止画→動画（i2v）** … Runway Gen-3 / Kling / Luma / Pika / Sora 等でカットごとに数秒の動きを付ける（§3のプロンプト）
3. **音声合成** … ElevenLabs / VOICEVOX / にじボイス 等でセリフ・ナレーションを生成（§4の台本）
4. **編集** … 動画＋音声＋BGMをDaVinci Resolve / CapCut 等で結合・尺合わせ

---

## 1. シーン絵コンテ（カット割り）

BGM：荘厳な弦＋低い合唱（「メインテーマ」の重厚アレンジ）。全体トーンは黄昏〜暗闇。

| # | 秒数 | 画（ショット） | カメラ/動き | 音（SE/セリフ） |
| --- | --- | --- | --- | --- |
| C1 | 0:00–0:08 | 荒野の上空、割れた空。隕石が尾を引いて落ちる | 超ロング。ゆっくり下降パン | 風鳴り、低い地鳴り。ナレーションIN |
| C2 | 0:08–0:16 | 巨大な邪悪の大樹＝エクスデスのシルエットが大地から隆起 | ローアングル煽り、迫り上がり | 不協和音の合唱、樹の軋み |
| C3 | 0:16–0:24 | 4つのクリスタル（風青/水翠/火赤/土琥珀）が宙に浮き輝く | 円環状にトラッキング | クリスタルの澄んだ共鳴音 |
| C4 | 0:24–0:32 | 暁の4戦士、横並びのシルエットで対峙（ドルガン/ガラフ/ゼザ/ケルガー） | 背後ローアングル、風になびくマント | ガラフ「ゆくぞ……皆の者！」 |
| C5 | 0:32–0:40 | 4人が一斉に駆け出す。剣・魔法の光が交差 | 横スクロール追走、速度線 | 疾走音、剣戟、詠唱の重なり |
| C6 | 0:40–0:48 | エクスデスの巨腕が振り下ろされ、大地が爆ぜる | 衝撃のシェイク、閃光 | 轟音、ドルガン「させるか……！」 |
| C7 | 0:48–0:54 | 4戦士が手をかざし、光の封印陣が展開 | 真俯瞰→あおりへ切替 | 高鳴る封印の和音 |
| C8 | 0:54–1:00 | 光がエクスデスを呑み、世界が真っ二つに裂ける | 画面全体が白へブリードアウト | 空間が裂ける轟音→無音の予兆 |
| C9 | 1:00–1:06 | 静寂。引き裂かれた世界が2つに分かれて漂う | 超ロング、ゆっくり後退 | 余韻のピアノ単音。ナレーション |
| C10 | 1:06–1:12 | タイトルロゴ「FINAL FANTASY V」浮かび上がる | 黒背景にロゴIN、微発光 | 一陣の風→主題のワンフレーズ |

---

## 2. キーフレーム静止画 生成プロンプト（カット別）

> 共通スタイル接頭辞（全カットの先頭に付ける）：
> `2D cel anime, painterly JRPG fantasy key frame, Amano-inspired ethereal design, cinematic dramatic lighting, high detail, film grain, 16:9 --ar 16:9`

| # | Prompt（共通接頭辞に続けて） |
| --- | --- |
| C1 | `a vast twilight wasteland under a cracked sky, a meteor streaking down with a glowing tail, ominous wide establishing shot, muted blue-grey palette` |
| C2 | `a colossal evil tree monster silhouette rising from the earth, gnarled roots, foreboding low-angle, purple-green eerie glow` |
| C3 | `four elemental crystals floating in a circle (blue wind, teal water, red fire, amber earth), radiant light, sacred atmosphere` |
| C4 | `four heroic warriors standing in a row seen from behind, capes in the wind, facing a giant dark wizard tree, dusk backlight, epic` |
| C5 | `four warriors charging forward, crossing trails of sword light and magic, motion energy, dynamic side-scrolling composition` |
| C6 | `a giant dark arm smashing down, ground exploding, shockwave and debris, blinding flash, intense impact frame` |
| C7 | `four warriors raising hands as a glowing magic sealing circle expands, runic light, top-down to low-angle drama` |
| C8 | `a flood of light swallowing the evil tree as the whole world splits in two, white bleed-out, apocalyptic transformation` |
| C9 | `two halves of a fractured world drifting apart in silence, vast empty space, melancholic stillness, soft starlight` |
| C10 | `pure black background with a faint glowing emblem space for a logo, minimal, a single gust of wind particles` |

---

## 3. 静止画→動画（i2v）プロンプト＆カメラ指示

> Runway / Kling / Luma 等の image-to-video 入力欄に貼る想定。動きは「3〜5秒・控えめ」を基本に。

| # | i2v Motion Prompt | カメラ |
| --- | --- | --- |
| C1 | `the meteor slowly descends, dust drifts, subtle parallax in the clouds` | 緩やかな下降パン、ごく弱いズームイン |
| C2 | `the tree silhouette rises slowly, roots writhing, eerie glow pulsing` | ローアングル固定＋微上昇 |
| C3 | `crystals gently rotate and pulse with light, particles float` | 円弧トラッキング |
| C4 | `capes and hair flutter in the wind, faint breathing motion, embers drift` | 超スローのドリーイン |
| C5 | `warriors run forward, light trails streak, fast camera follow, speed lines` | 横移動の追走、ブラー強め |
| C6 | `the dark arm slams down, screen shake, debris bursts toward camera, white flash` | 強いカメラシェイク |
| C7 | `the sealing circle expands outward, runes glow brighter, light rises` | 真俯瞰→あおりへスイッシュ |
| C8 | `light overwhelms the frame, the world cracks and splits, bleed to white` | 全画面ブリードアウト |
| C9 | `the two world-halves drift apart very slowly, gentle starlight twinkle` | 超スローの後退ドリー |
| C10 | `the emblem softly glows into view, wind particles cross the frame` | 固定、微発光フェードイン |

---

## 4. 音声台本＆ボイスディレクション

> ElevenLabs / VOICEVOX / にじボイス等のTTS向け。日本語セリフ＋演技指定＋（英語版用）対訳。
> 各キャラの声設計は [設定資料集](./ff5-anime-movie-and-worldbook.md) と [TV企画書 §15](./ff5-anime-adaptation.md) に準拠。

### ナレーション（N）／落ち着いた低めの語り、荘厳で静か
- **C1（0:02〜）** N：「世界は、4つのクリスタルの力で均衡を保っていた。」  
  *Dir: ゆっくり、低音、神話を語るように。* / EN: "The world held its balance through the power of four crystals."
- **C9（1:01〜）** N：「だが、その日──ひとつの世界は、ふたつに引き裂かれた。」  
  *Dir: 一拍おいて「ふたつに」を強調。余韻。* / EN: "But on that day, one world was torn in two."

### ガラフ（暁の4戦士・老騎士）／渋く力強い、腹から出す声
- **C4（0:28〜）** ガラフ：「ゆくぞ……皆の者！」  
  *Dir: 覚悟を込めて低く、語尾で張り上げる。* / EN: "Now... everyone!"

### ドルガン（暁の4戦士・バッツの父）／芯のある青年〜壮年の声
- **C6（0:44〜）** ドルガン：「させるか……！」  
  *Dir: 食いしばりながら、押し出すように。* / EN: "I won't let you!"

### 合唱/SEメモ
- C2・C7・C8 はセリフを置かず、合唱と効果音で圧を作る（セリフと音楽の交通整理）。

---

## 5. 尺・テンポ設計メモ
- 1カット平均6〜7秒。アクションのC5〜C8は短めに畳みかけ、C9で一気に“静寂”へ落とす緩急。
- BGMは C1〜C7 で漸増、C8 の爆発でピーク、C9 で無音寸前まで引く。
- セリフは全体で3つだけ（語りすぎない）。映像と音楽で語る方針。

---

## 6. 次の試作候補
- このアバンに続く **第1話本編アタマ（バッツ＆ボコ登場）** を同フォーマットで。
- 看板シーン **「ガラフの最期」** を感情演技重視のボイス試作として。

---

*Document by のんラボ / non-x2 — 「個人が AI で何ができるか」の実証実験の一環として作成。*
