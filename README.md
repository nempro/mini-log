# Mini Log

写真を並べて、一日の小さな記録に。

Mini Logは、画像と短い動画を組み合わせて一本の映像を作るWindows向けデスクトップツールです。複雑なタイムラインではなく、素材・Caption・音・LOOK・Previewに絞った軽量Studioです。

Vlogのほか、ツール紹介、簡易プレゼン、電子紙芝居のような映像作りにも使えます。

## Features

- 画像（JPG / JPEG / PNG / WebP）と動画（MP4 / MOV）の追加
- Cutカードのドラッグ＆ドロップ並べ替えと、Ctrl+クリックによる複数選択
- 静止画 / 動画風、Zoom / Pan、表示時間の調整
- Cut Caption（フォント、サイズ、位置、Motion、スタイル）と終了Caption
- CutごとのTransition（なし / フェード / クロスフェード / ブラックを挟む）
- 動画Cutの元音声ON / OFFと音量調整
- BGM、Cut Audio、音源の試聴
- 動画全体のLOOK（内蔵プリセット5種類、ユーザー所有の `.cube` 3D LUT、強度調整）
- Previewの作成と再生
- Projectの新規作成・保存・復元
- H.264 / AAC形式のMP4書き出し
- 春 / 夏 / 秋 / 冬のアプリテーマ

## Download

[Mini Log 0.2.0のWindows版をダウンロード](https://github.com/nempro/mini-log/releases/tag/v0.2.0)

Windowsで利用する場合は、Releaseページの **`MiniLog-0.2.0-windows.zip`** をダウンロードしてください。GitHubが自動生成する「Source code」は、配布用アプリ本体ではありません。

ZIPを展開し、フォルダー内の `MiniLog.exe` を起動してください。PythonやFFmpegを別途インストールする必要はありません。展開したフォルダー全体を保持して使用してください。

## Usage

1. `MiniLog-0.2.0-windows.zip` をダウンロードして展開し、`MiniLog.exe` を起動します。
2. 写真やMP4 / MOV動画をドラッグ＆ドロップするか、「画像 / 動画を追加」から素材を選びます。
3. Cutカードを並べ替え、表示時間、静止画 / 動画風、動き、Transitionを調整します。
4. 必要に応じてCut Caption、BGM、Cut Audio、LOOKを設定します。
5. 「プレビューを作成」で動画全体の流れを確認します。
6. 「MP4を書き出す」で完成動画を保存します。

新しいProjectでは、最初に追加した画像または動画の縦横比をPreviewとMP4の出力比率に使います。異なる比率の素材を後から追加しても、Projectの比率は変わりません。

Durationは入力後にEnterを押すか、入力欄からフォーカスを外すと確定します。Ctrl+クリックでCutを複数選択し、表示時間をまとめて変更できます。Ctrl+Aでは全Cutを選択できます。

動画Cutは素材の先頭から再生し、元動画の終端まで使用します。動画はループしません。長い動画ではPreview生成や書き出しに時間がかかる場合があります。

LOOKは「暖色」「色あせ」「レトロ」「寒色」「フィルム」から選べます。手持ちの `.cube` 3D LUTも読み込めます。強度は0〜100%で調整でき、オリジナルへ戻せます。LOOKは素材映像へ適用され、Cut Captionと終了Captionには適用されません。

Cut Audioはカット開始と同時に再生します。動画元音声、Cut Audio、BGMはそれぞれ個別に設定でき、同時に使用できます。

Projectファイルは保存して、後から再読込できます。Custom LUTはProjectへコピーされないため、保存後も元の `.cube` ファイルを保持してください。次の動画を作るときは「新しいプロジェクト」を使います。

## Supported Environment

Windows 10 / 11（64-bit）に対応しています。配布形式はインストーラー不要のZIP展開型です。

## Notes

未署名EXEのため、Windows SmartScreenなどの警告が表示される場合があります。

## License / Third-party

Mini Log自身のLicenseは未設定です。配布物に含まれるFFmpeg、Python runtime、Pillow、tkinterdnd2、PyInstallerなどのライセンス情報は、配布ZIP内の `THIRD_PARTY_NOTICES.txt` と `licenses/` に収録しています。FFmpegはGPLv3系の実バイナリを同梱しています。

## Development build

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
python scripts/build_windows.py
python tests/release_prep_acceptance.py
