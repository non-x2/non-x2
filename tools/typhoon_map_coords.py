#!/usr/bin/env python3
"""🗾 台風ページの④予備の手描き地図で使う、緯度経度→地図の座標(x,y)を計算する道具。

■ なぜ必要か
④の手書きスナップショット（typhoon-app/index.html の <svg id="map-svg"> 内、
<path class="track ...">・<circle class="now-pos ...">・<circle class="waypoint">
など）は、台風の位置（緯度・経度）をメルカトル図法の式で人が計算して
x,y に置き換え、手で書き込んでいます。この式は index.html の中の
JavaScript（LON0・KX・Y0・KY の定数と px()・py() 関数）と**同じもの**を
ここに写して使っているので、④を更新するたびに毎回同じ計算を手計算し
なくて済みます。

⚠️ index.html 側の地図（LON0・KX・Y0・KY やviewBox）を描き直したときは、
この道具の定数もあわせて直してください（ズレると座標が合わなくなります）。

■ 使い方（緯度経度 → x,y）
    python3 tools/typhoon_map_coords.py 24.5 132.0 26.0 135.4 ...
        （緯度 経度 のペアを好きなだけ並べる）

    出力例：
        24.5,132.0 → x=101.7,y=270.3
        26.0,135.4 → x=135.2,y=246.1

        SVGのpath d用: M101.7,270.3 L135.2,246.1

■ 使い方（逆方向：x,y → 緯度経度）
    python3 tools/typhoon_map_coords.py --xy 101.7 270.3 135.2 246.1 ...
        （④の地図を見ながら「ここが今どのへんか」を確かめたいときに使う）

    出力例：
        x=101.7,y=270.3 → 24.5,132.0

    ⚠️ x,y が地図のviewBox（-20〜350, -10〜365）の外を指しているときは、
       計算はするものの「⚠️ 地図の外です」と併記します（値は参考程度に）。

外部のライブラリは使いません（Python 3 の標準機能だけ）。
"""

from __future__ import annotations

import math
import sys

# typhoon-app/index.html の同名の定数と必ず一致させること
LON0 = 122.02
KX = 10.163
Y0 = 535.07
KY = 582.3

# typhoon-app/index.html の <svg id="map-svg" viewBox="..."> と必ず一致させること
VIEWBOX_X_MIN, VIEWBOX_Y_MIN = -20.0, -10.0
VIEWBOX_X_MAX, VIEWBOX_Y_MAX = VIEWBOX_X_MIN + 370.0, VIEWBOX_Y_MIN + 375.0


def lonlat_to_xy(lat: float, lon: float) -> tuple[float, float]:
    x = (lon - LON0) * KX
    y = Y0 - KY * math.log(math.tan(math.pi / 4 + lat * math.pi / 360))
    return round(x, 1), round(y, 1)


def xy_to_lonlat(x: float, y: float) -> tuple[float, float]:
    lon = x / KX + LON0
    lat = (math.atan(math.exp((Y0 - y) / KY)) - math.pi / 4) * 360 / math.pi
    return round(lat, 1), round(lon, 1)


def main(argv: list[str]) -> int:
    reverse = bool(argv) and argv[0] == "--xy"
    if reverse:
        argv = argv[1:]

    if len(argv) < 2 or len(argv) % 2 != 0:
        print(__doc__)
        return 1

    if reverse:
        for i in range(0, len(argv), 2):
            x, y = float(argv[i]), float(argv[i + 1])
            lat, lon = xy_to_lonlat(x, y)
            out_of_bounds = not (VIEWBOX_X_MIN <= x <= VIEWBOX_X_MAX and VIEWBOX_Y_MIN <= y <= VIEWBOX_Y_MAX)
            note = "　⚠️ 地図の外です（viewBoxの範囲外）" if out_of_bounds else ""
            print(f"x={x},y={y} → {lat},{lon}{note}")
        return 0

    points = []
    for i in range(0, len(argv), 2):
        lat, lon = float(argv[i]), float(argv[i + 1])
        x, y = lonlat_to_xy(lat, lon)
        points.append((lat, lon, x, y))
        print(f"{lat},{lon} → x={x},y={y}")

    path = " L".join(f"{'M' if i == 0 else ''}{x},{y}" for i, (_, _, x, y) in enumerate(points))
    print(f"\nSVGのpath d用: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
