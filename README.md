# Mini Log

写真を並べて、一日の小さな記録に。

Mini Logは、複数の写真から短い縦型Vlogを作るWindows向けデスクトップツールです。複雑なタイムラインではなく、写真・Caption・BGM・Cut Audio・Previewに絞っています。

## Features

- 画像D&D追加、カットD&D並べ替え、Ctrl+クリック複数選択
- 静止画 / 動画風、Zoom / Pan、0.1秒単位の表示時間調整
- Cut Caption（フォント、サイズ、位置、Motion）と終了Caption
- BGM、Cut Audio、Preview、H.264/AAC MP4書き出し
- Project保存 / 復元、春 / 夏 / 秋 / 冬テーマ

## Download

[GitHub Releases](../../releases) から最新版の `MiniLog-0.1.0-windows.zip` をダウンロードし、ZIPを展開して `MiniLog.exe` を起動してください。Pythonや別途FFmpegの導入は不要です。

## Usage

1. 画像を追加し、順番・表示時間・静止画 / 動画風を調整します。
2. 必要に応じてCaption、BGM、Cut Audioを設定します。
3. Previewで全体を確認し、MP4を書き出します。

## Supported Environment

Windows 10 / 11（64-bit）です。配布形式はInstallerなしのZIP展開型です。

## Notes

未署名EXEのため、Windows SmartScreen等の警告が表示される場合があります。配布フォルダ全体を保持して使用してください。

## License / Third-party

Mini Log自身のLicenseは未設定です。配布物に含まれるFFmpeg、Python runtime、Pillow、tkinterdnd2、PyInstallerなどのライセンスは、配布ZIP内の `THIRD_PARTY_NOTICES.txt` と `licenses/` に収録します。FFmpegはGPLv3系の実バイナリを同梱します。

## Development build

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
python scripts/build_windows.py
python tests/release_prep_acceptance.py
```

出力は `release/MiniLog-0.1.0/` と `release/MiniLog-0.1.0-windows.zip` です。
