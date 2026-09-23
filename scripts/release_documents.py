"""Release-facing text generated from Mini Log's single version source."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.version import __version__


APP_NAME = "Mini Log"
FFMPEG_VERSION = "7.1-essentials_build-www.gyan.dev"
FFMPEG_SHA256 = "2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3"
FFMPEG_SOURCE_COMMIT = "b08d7969c5"


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def distribution_readme() -> str:
    return f"""{APP_NAME} {__version__}

Mini Logは、複数の写真を並べて短い縦型動画を作るWindows向けツールです。

■ 主な機能
・複数画像の追加
・静止画 / 動画風表示
・Zoom / Pan
・表示時間調整
・カットごとのCaption
・Captionのフォント / サイズ / 位置 / Motion
・BGM
・カット音声
・Preview
・MP4書き出し
・Project保存 / 復元
・春 / 夏 / 秋 / 冬テーマ

■ 基本操作
1. 画像を追加
2. 順番や表示時間を調整
3. 必要に応じてCaption / BGM / カット音声を設定
4. Previewを確認
5. MP4を書き出す

■ 起動方法
ZIPを展開し、MiniLog.exeを起動してください。

■ 対応OS
Windows 10 / 11（64-bit）

■ 注意
未署名EXEのため、Windows SmartScreen等の警告が表示される場合があります。
第三者ソフトウェアとライセンスの案内は THIRD_PARTY_NOTICES.txt と licenses フォルダを確認してください。
"""


def third_party_notices() -> str:
    return f"""{APP_NAME} {__version__} - Third-party notices
=================================================

This distribution contains the following third-party components. License texts
and the FFmpeg source/build information are in the licenses directory.

FFmpeg
------
Binary: ffmpeg/ffmpeg.exe
Observed build: {FFMPEG_VERSION}
SHA-256: {FFMPEG_SHA256}
License: GNU GPL version 3 or later (this binary enables GPL and version 3)
Source/build details: licenses/ffmpeg/BUILD_INFO.txt
Corresponding-source guidance: licenses/ffmpeg/CORRESPONDING_SOURCE.txt

Python Runtime
--------------
CPython 3.10 runtime and Tcl/Tk runtime are bundled by PyInstaller.
License texts: licenses/python/LICENSE.txt and licenses/tcl-tk/LICENSE.txt

Pillow 12.3.0
---------------
License: MIT-CMU
License text: licenses/pillow/LICENSE.txt

tkinterdnd2 0.6.3 / tkdnd 2.10.2
-----------------------------------
Used for Explorer drag and drop.
License texts: licenses/tkinterdnd2/LICENSE.txt and licenses/tkdnd/LICENSE.txt

PyInstaller 6.22.3
------------------
Used to create the executable. The bundled bootloader exception permits
distribution of the resulting application.
License text: licenses/pyinstaller/COPYING.txt

imageio-ffmpeg 0.6.0
---------------------
Used during development to obtain the verified FFmpeg binary; it is not
included as a Python package in the release folder.
License: BSD 2-Clause
License text: licenses/imageio-ffmpeg/LICENSE.txt

Mini Log itself has no license selected in this release. This notice does not
grant a license to Mini Log source code or assets.
"""


def write_distribution_documents(release_root: Path) -> None:
    (release_root / "README.txt").write_text(distribution_readme(), encoding="utf-8")
    (release_root / "THIRD_PARTY_NOTICES.txt").write_text(
        third_party_notices(), encoding="utf-8"
    )
