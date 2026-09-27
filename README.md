# Mini Log

写真を並べて、一日の小さな記録に。

Mini Logは、画像と短い動画からVlogを作るWindows向けデスクトップツールです。複雑なタイムラインではなく、素材・Caption・BGM・Cut Audio・Previewに絞っています。

## Features

- 画像（JPG / JPEG / PNG / WebP）と動画（MP4 / MOV）の追加、カットD&D並べ替え、Ctrl+クリック複数選択
- 静止画 / 動画風、Zoom / Pan、0.1秒単位の表示時間調整（Ctrl+Aで全Cut選択・一括変更）
- Cut Caption（フォント、サイズ、位置、Motion）と終了Caption
- カットごとの切り替え（カット / フェード / クロスフェード / ブラックを挟む、0.2 / 0.4 / 0.6秒）
- 動画全体のLOOK（内蔵プリセット5種類、ユーザー所有の `.cube` 3D LUT、強度0〜100%、オリジナルへ切替可能）
- BGM、Cut Audio、Preview、H.264/AAC MP4書き出し
- Projectの新規作成・保存 / 復元、春 / 夏 / 秋 / 冬テーマ

## Download

公開済みの配布版は [Mini Log 0.1.0 Release](https://github.com/nempro/mini-log/releases/tag/v0.1.0) です。このリポジトリの現行ソースは **0.2.0 Release Candidate** であり、0.1.0の配布ZIPには本ページ記載の新機能はまだ含まれません。0.2.0 RCのローカルビルドは `release/MiniLog-0.2.0-windows.zip` です。ZIPを展開して `MiniLog.exe` を起動してください。Pythonや別途FFmpegの導入は不要です。

## Usage

1. 画像やMP4 / MOV動画を追加し、順番・表示時間・静止画 / 動画風を調整します。動画Cutは素材の先頭から再生し、素材終端または30秒上限で終了します（ループしません）。
2. 必要に応じてCutごとの切り替え、Caption、BGM、Cut Audioを設定します。切り替えは各カットから次のカットに適用され、最後のカットでは使われません。
3. Previewで全体を確認し、MP4を書き出します。

新しいProjectでは、最初に追加した画像または動画の縦横比をPreviewとMP4の出力比率に使います。後から別の比率の素材を追加しても比率は変わりません。表示時間の直接入力はEnterまたはフォーカスを外したときに確定します。Ctrl+クリックで複数Cutを選択し、一括で表示時間を変更できます。

LOOKは「暖色」「色あせ」「レトロ」「寒色」「フィルム」から選ぶだけで使えます。手持ちの `.cube` がある場合はカスタムLUTも読み込めます。強度は0〜100%で調整でき、オリジナルへ戻せます。静止画・動画風・動画Cutと切り替え後の映像へ適用し、Cut Captionと終了Captionには適用しません。内蔵プリセットはProjectの `look_type` にIDで保存されます。カスタムLUTはファイルをProjectへコピーしないため、保存後も元の `.cube` ファイルを保持してください。

次の動画を作るときは「新しいプロジェクト」を使います。未保存の編集がある場合は確認が表示されます。季節テーマとPreviewの表示状態は維持されます。

動画Cutでは元動画音声を個別にON / OFFし、音量を調整できます。元動画音声、Cut Audio、BGMは同時に使用でき、音量はそれぞれの設定で調整します。動画CutにもCut Audioを追加できます。

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

出力は `release/MiniLog-0.2.0/` と `release/MiniLog-0.2.0-windows.zip` です。
