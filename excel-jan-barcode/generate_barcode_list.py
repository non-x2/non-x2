#!/usr/bin/env python3
"""
products.csv(商品名, JANコード)から、本物のバーコード「画像」を
埋め込んだExcel(xlsx)を作るツール。

フォント方式のバーコードは、別のPCで開く/印刷すると
フォント未埋め込みで崩れて読み取れなくなることがある。
このツールは画像として貼り付けるので、どのPCで開いても・
印刷しても見た目が変わらない。

使い方:
    python3 generate_barcode_list.py [入力CSV] [出力XLSX]

    引数を省略した場合は products.csv → products_with_barcode.xlsx
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import barcode
from barcode.writer import ImageWriter
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

BASE_DIR = Path(__file__).resolve().parent

# バーコードの物理サイズ(mm)。JAN/EAN-13の規格(モジュール幅0.33mm=100%)より
# 少し大きめにして、安いスキャナーや多少の印刷劣化でも読み取りやすくしている。
MODULE_WIDTH_MM = 0.4   # 規格100%は0.33mm。約120%相当。
MODULE_HEIGHT_MM = 18.0  # バーの高さ。斜め読み取りに強くするため規格よりやや高め。
IMAGE_DPI = 300
DISPLAY_DPI = 96  # Excel/OOXMLが画像サイズ(px)を解釈する際の基準DPI

ROW_HEIGHT_PT = 92          # バーコード画像が縦に切れないよう余裕を持たせる
NAME_COL_WIDTH = 32
JAN_COL_WIDTH = 16
BARCODE_COL_WIDTH = 30


def build_ean13(raw: str):
    """12桁または13桁の文字列から、チェックデジット確定済みのEAN13バーコードを作る。

    戻り値: (barcode_object, 確定した13桁コード, 注記文字列)
    """
    digits = "".join(ch for ch in raw.strip() if ch.isdigit())
    if len(digits) not in (12, 13):
        raise ValueError(
            f"JANコードは12桁か13桁の数字にしてください(入力: '{raw}' / {len(digits)}桁でした)"
        )

    body = digits[:12]
    ean_obj = barcode.get("ean13", body, writer=ImageWriter())
    corrected = ean_obj.ean  # ライブラリがチェックデジットを再計算した13桁

    note = ""
    if len(digits) == 13 and digits[12] != corrected[12]:
        note = (
            f"チェックデジットを {digits[12]} → {corrected[12]} に自動修正"
            "(元データのチェックデジットが誤っていた可能性があります)"
        )
    return ean_obj, corrected, note


def render_barcode_png(ean_obj, out_path_no_ext: Path) -> Path:
    options = {
        "module_width": MODULE_WIDTH_MM,
        "module_height": MODULE_HEIGHT_MM,
        "dpi": IMAGE_DPI,
        "write_text": True,
    }
    saved_path = ean_obj.save(str(out_path_no_ext), options)
    return Path(saved_path)


def read_products(csv_path: Path):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            name = (row.get("商品名") or "").strip()
            raw_jan = (row.get("JANコード") or "").strip()
            if not name and not raw_jan:
                continue  # 空行はスキップ
            yield i, name, raw_jan


def main(argv: list[str]) -> int:
    input_csv = Path(argv[1]) if len(argv) > 1 else BASE_DIR / "products.csv"
    output_xlsx = Path(argv[2]) if len(argv) > 2 else BASE_DIR / "products_with_barcode.xlsx"

    if not input_csv.exists():
        print(f"[エラー] 入力ファイルが見つかりません: {input_csv}", file=sys.stderr)
        return 1

    img_dir = BASE_DIR / "_barcode_images_tmp"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True)

    entries = []  # (name, jan13, png_path, note)
    had_error = False

    for row_no, name, raw_jan in read_products(input_csv):
        if not name or not raw_jan:
            print(f"[スキップ] {row_no}行目: 商品名またはJANコードが空です", file=sys.stderr)
            continue
        try:
            ean_obj, jan13, note = build_ean13(raw_jan)
        except ValueError as e:
            print(f"[エラー] {row_no}行目「{name}」: {e}", file=sys.stderr)
            had_error = True
            continue

        png_path = render_barcode_png(ean_obj, img_dir / f"barcode_{row_no}")
        entries.append((name, jan13, png_path, note))
        if note:
            print(f"[注記] {row_no}行目「{name}」: {note}")

    if not entries:
        print("[エラー] 有効な商品データが1件もありませんでした。", file=sys.stderr)
        return 1

    wb = Workbook()
    ws = wb.active
    ws.title = "商品リスト"

    headers = ["No.", "商品名", "JANコード", "バーコード", "備考"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = NAME_COL_WIDTH
    ws.column_dimensions["C"].width = JAN_COL_WIDTH
    ws.column_dimensions["D"].width = BARCODE_COL_WIDTH
    ws.column_dimensions["E"].width = 46

    for idx, (name, jan13, png_path, note) in enumerate(entries, start=2):
        ws.cell(row=idx, column=1, value=idx - 1).alignment = Alignment(
            horizontal="center", vertical="center"
        )
        ws.cell(row=idx, column=2, value=name).alignment = Alignment(vertical="center")

        jan_cell = ws.cell(row=idx, column=3, value=jan13)
        jan_cell.number_format = "@"  # 先頭ゼロ落ち防止(文字列として保持)
        jan_cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.cell(row=idx, column=5, value=note).alignment = Alignment(vertical="center")

        ws.row_dimensions[idx].height = ROW_HEIGHT_PT

        with PILImage.open(png_path) as im:
            px_w, px_h = im.size  # IMAGE_DPIでの実ピクセル数

        xl_img = XLImage(str(png_path))
        # OOXMLは画像サイズを96DPI基準のpxとして解釈するため、
        # 実寸(mm)が変わらないよう300DPI→96DPIへ換算してから指定する。
        scale = DISPLAY_DPI / IMAGE_DPI
        xl_img.width = px_w * scale
        xl_img.height = px_h * scale

        anchor_cell = f"{get_column_letter(4)}{idx}"
        ws.add_image(xl_img, anchor_cell)

    wb.save(output_xlsx)
    shutil.rmtree(img_dir, ignore_errors=True)  # 埋め込み済みなので作業用PNGは削除
    print(f"\n作成しました: {output_xlsx}")
    print(f"{len(entries)}件のバーコードを書き出しました。")

    if had_error:
        print("一部の行はエラーのためスキップしました(上記ログ参照)。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
