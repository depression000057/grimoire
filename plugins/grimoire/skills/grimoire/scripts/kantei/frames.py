#!/usr/bin/env python3
"""画面収録（スマホで Threads をスクロールした動画）から、読むための静止画を切り出す。

ffmpeg が入っている時だけ動く。切り出した画像をスキルが1枚ずつ読んで、投稿の文字と
いいね・コメント数を書き起こす。ffmpeg が無い時は、スクリーンショットを直接渡してもらう。

使い方:
  python3 frames.py 画面収録.mp4 出力フォルダ
  python3 frames.py 画面収録.mp4 出力フォルダ --every 1.5   # 1.5秒ごと（既定2秒）
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="画面収録から静止画を切り出す")
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--every", type=float, default=2.0, help="何秒ごとに1枚切り出すか（既定2秒）")
    args = ap.parse_args(argv)
    if shutil.which("ffmpeg") is None:
        print("ffmpeg が見つかりません。動画の代わりに、スクリーンショットを直接渡してください。", file=sys.stderr)
        return 3
    video = Path(args.video)
    if not video.exists():
        print(f"エラー: 動画が見つかりません: {video}", file=sys.stderr)
        return 2
    out = Path(args.outdir)
    if out.exists() and any(out.glob("frame_*.png")):
        print(f"エラー: {out} には前に切り出した画像が残っています。混ざらないように、別の空のフォルダを指定してください。",
              file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
           "-vf", f"fps=1/{args.every},scale=720:-2", str(out / "frame_%04d.png")]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("切り出しに失敗しました。スクリーンショットを直接渡してください。", file=sys.stderr)
        return r.returncode
    n = len(list(out.glob("frame_*.png")))
    print(f"{n}枚を切り出しました: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
