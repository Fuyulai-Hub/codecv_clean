#!/usr/bin/env python3
"""
remove_pattern_watermark.py
通用去除“平铺图案(Tiling Pattern)”类水印的工具。

适用场景
--------
很多在线简历/文档生成器(如 CodeCV 之类)会用 PDF 的 Tiling Pattern
把一张水印图片(或水印文字)平铺满整页。这类水印:
  * search_for() 搜不到(不在文字层)
  * 不是单张普通贴图(是 Pattern 引用的 XObject)
  * 页面用 `/Pattern cs  /Pxx scn  <rect> re f` 当作“填充色”铺满

本工具会扫描全 PDF 里所有 PatternType==1 的平铺图案对象,
识别出“只用来绘制水印(通常是画 image XObject / 大面积平铺)”的图案,
把它的内容流清空,使其不再渲染任何内容。正文、照片、排版均不受影响。

用法
----
    python3 remove_pattern_watermark.py input.pdf output.pdf
    # 预览将要清空哪些 pattern,不写出文件:
    python3 remove_pattern_watermark.py input.pdf --dry-run
    # 只清空指定 xref 的 pattern:
    python3 remove_pattern_watermark.py input.pdf output.pdf --only 130,153

依赖: PyMuPDF (pip install pymupdf)
"""
import sys
import re
import argparse
import fitz  # PyMuPDF


def find_pattern_xrefs(doc):
    """返回文档中所有 PatternType 1 平铺图案的 xref 列表及其信息。"""
    patterns = []
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref)
        except Exception:
            continue
        if not obj:
            continue
        if "/PatternType 1" not in obj and "/PatternType\n" not in obj:
            # 仅保留平铺图案(PatternType 1);渐变(2)不动
            if "/PatternType" not in obj or "/PatternType 1" not in obj.replace("\n", " "):
                continue
        try:
            stream = doc.xref_stream(xref) or b""
        except Exception:
            stream = b""
        stext = stream.decode("latin-1", "replace")
        # 该 pattern 是否绘制了图片 XObject(典型水印) 或含文字绘制
        draws_xobject = bool(re.search(r"/\w+\s+Do", stext))
        draws_text = "Tj" in stext or "TJ" in stext
        patterns.append({
            "xref": xref,
            "draws_xobject": draws_xobject,
            "draws_text": draws_text,
            "stream": stext.strip(),
        })
    return patterns


def pattern_is_used_as_fill(doc, xref):
    """判断该 pattern 是否被页面当作填充色铺开(scn),这是水印铺满整页的标志。"""
    # 找到引用它的资源名 /Pxxx,再看是否有 `/Pxxx scn`
    for pno in range(doc.page_count):
        page = doc[pno]
        page_obj = doc.xref_object(page.xref)
        # 资源里 /Pname xref 0 R
        m = re.findall(r"/(P\w+)\s+%d\s+0\s+R" % xref, page_obj)
        if not m:
            continue
        cont = page.read_contents().decode("latin-1", "replace")
        for name in m:
            if re.search(r"/%s\s+scn" % re.escape(name), cont) or \
               re.search(r"/%s\s+SCN" % re.escape(name), cont):
                return True
    return False


def remove_watermark(input_path, output_path=None, only=None, dry_run=False):
    doc = fitz.open(input_path)
    patterns = find_pattern_xrefs(doc)

    targets = []
    for p in patterns:
        xref = p["xref"]
        if only is not None:
            if xref in only:
                targets.append(p)
            continue
        # 自动判定:平铺图案 且 (绘制了图片 或 绘制了文字) 且 被当作填充铺开
        looks_like_wm = (p["draws_xobject"] or p["draws_text"])
        used_as_fill = pattern_is_used_as_fill(doc, xref)
        if looks_like_wm and used_as_fill:
            targets.append(p)

    print(f"[i] 共发现 {len(patterns)} 个平铺图案(PatternType 1)")
    print(f"[i] 判定为水印并将清空的图案: {[p['xref'] for p in targets]}")
    for p in targets:
        preview = p["stream"].replace("\n", " ")[:80]
        print(f"    - xref {p['xref']}: {preview!r}")

    if dry_run:
        print("[i] --dry-run: 仅预览,未写出文件")
        return

    if not targets:
        print("[!] 未发现平铺图案类水印。文件未修改。")
        return

    for p in targets:
        doc.update_stream(p["xref"], b" ")  # 清空图案内容 -> 不再绘制任何东西

    out = output_path or (input_path.rsplit(".", 1)[0] + "_clean.pdf")
    doc.save(out, garbage=4, deflate=True, clean=True)
    print(f"[✓] 已保存去水印文件: {out}")


def main():
    ap = argparse.ArgumentParser(description="通用去除 PDF 平铺图案水印")
    ap.add_argument("input", help="输入 PDF")
    ap.add_argument("output", nargs="?", help="输出 PDF(默认 *_clean.pdf)")
    ap.add_argument("--only", help="只清空指定 xref,逗号分隔,如 130,153")
    ap.add_argument("--dry-run", action="store_true", help="仅预览不写出")
    args = ap.parse_args()

    only = None
    if args.only:
        only = {int(x) for x in args.only.split(",") if x.strip()}

    remove_watermark(args.input, args.output, only=only, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
