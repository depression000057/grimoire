# 環境ごとの動き方

- 役割: 受講生がどの AI・どの画面で使っていても、同じ品質で動くように、環境を見分けて動き方を切り替える
- いつ読むか: 毎回の最初／保存先や道具の使い方に迷った時
- 目次: §1 見分ける2つ §2 環境ごとの動き方 §3 保存先と本体の置き場所 §4 ファイルが書けない時（半自動） §5 Python が動かない時 §6 大量の素材を受け取る時 §7 環境の仕様の確かめ先 §8 受講生への伝え方

## §1 見分ける2つ

| 見分けること | 確かめ方 |
|---|---|
| ファイルを読み書きできるか | Claude Code なら読み書きできる。作業フォルダに `ティルナノーグ_マイナレッジ/` があるかを見る |
| Python が動くか | コマンドを実行する道具・コードを実行する道具があるか。あれば `python3 --version`（Windows は `python --version`）を1回だけ試す |

確かめた結果は、受講生に長々と説明しない。困る時（ファイルが書けない等）だけ1行で伝える。

## §2 環境ごとの動き方

| 環境 | ファイル | Python | マイナレッジの育ち方 |
|---|---|---|---|
| **Claude Code（標準）**。Claude デスクトップアプリの Code タブ・黒い画面の claude・エディタの拡張機能 | 作業フォルダを読み書きできる | 入っていれば動く（無い時は §5） | 自動（作業フォルダに保存） |
| Claude ブラウザ版・スマホアプリ・Cowork・ChatGPT | 環境による | 環境による | 講座の標準ではない。動くところまで動いたうえで、「覚えたことを自動で貯めるには、Claude デスクトップアプリの Code タブでグリモワールのフォルダを開いてください」と1回だけ伝える |

## §3 保存先と本体の置き場所

- 作業フォルダ: 受講生がグリモワール用に Claude Code で開いたフォルダ（`${CLAUDE_PROJECT_DIR}`）。この直下に2つのフォルダを使う
  - `ティルナノーグ_マイナレッジ/`: 設定・カード・原文・実績・取り込み状況（育つもの）
  - `ティルナノーグ_制作物/`: 作った投稿・note・計画（毎回の成果物）
- 本体（このスキル）: Claude Code のプラグインとして、講座の配布元（git の置き場）から入っている。置き場所は Claude Code が管理し、講座が新しい版を出すと自動で入れ替わる。本体のフォルダの中には保存しない（入れ替えの時に消えるため）
- 登録: 作業フォルダの設定だけでは、本体は初めて開いた会話でしか読み込まれない。その会話の最初の入力で、フックがこのパソコンのこの作業フォルダに登録する（`scripts/register.sh` が `plugin install grimoire@tirnanog --scope local` を実行する）。フックで登録できなかった時は `sh .grimoire/scripts/register.sh` を Claude が実行する。フォルダを別の場所へ移した時は、作業フォルダの `CLAUDE.md` の手順で登録する
- 道具の呼び方: 作業フォルダで `python3 .grimoire/scripts/tn_kb.py …`。`.grimoire` は、フックが作り直す本体への近道（ふだんは会話の最初、初めての会話では最初の入力の時）で、版が変わっても同じ形で呼べる。symlink が作れない環境（Windows の既定の設定など）では、目印ファイル `.grimoire-copy-of` の入った本体のコピーになり、版が変わるとフックが作り直す。受講生が同じ名前の物を置いていたら、フックは触らずに知らせてくる。作業フォルダの設定（`.claude/settings.local.json`）で、この形の道具と、マイナレッジ・制作物への書き込み、グリモワールを呼ぶことだけを、確認なしで動かせるように許可してある

## §4 ファイルが書けない時（半自動）

保存が残らない環境では、マイナレッジ全体を1つのファイル「マイナレッジ_まとめ.md」にして持ち歩く。

1. 受講生に、プロジェクトを1つ作ってもらい、その資料（Claude は「プロジェクトの知識」、ChatGPT は「ファイル」）に「マイナレッジ_まとめ.md」を入れてもらう。初めての時はまだ無いので、「0 はじめて設定」の最後に作って渡す
2. 会話の中で、まとめを読む。まとめは区切り行 `<!-- tirnanog:file <相対パス> -->` でファイルごとに分かれている（設定・索引・育成ログ・カード・原文・実績）
3. 取り込み（`references/modes/4_grow.md`）や振り返りでカードが増えたら、会話の最後に、**更新した新しいまとめを丸ごと1つ**出す
   - コード実行が使える: まとめを一時フォルダに戻し（`python3 <スキルのフォルダ>/scripts/tn_kb.py import マイナレッジ_まとめ.md ./tmp_kb`）、`tn_kb.py add-card` などで更新し、`tn_kb.py export ./tmp_kb --out マイナレッジ_まとめ.md` でまとめ直して、ダウンロードできる形で渡す
   - コード実行が使えない: 元のまとめに新しいカードと更新を書き足した全文を、区切り行の形を守って出す
4. 受講生への案内の例:

> 今日の取り込みで覚えたことを入れた、新しい「マイナレッジ_まとめ.md」です。ダウンロードして、プロジェクトの古いまとめと入れ替えてください。次の会話から、ここで覚えたことを使って書きます。

古いまとめを残したまま新しいまとめを足すと、2つのまとめの内容が食い違うので、必ず入れ替えてもらう。

## §5 Python が動かない時

**入れ方を1回だけ伝える**（受講生が入れたら、次から道具が動く）:

- Mac: 初めて `python3` を動かした時に「"python3" コマンドを実行するには、コマンドライン・デベロッパ・ツールが必要です」と出る。「インストール」を押してもらう（数分かかる）。終わったら、もう一度話しかけてもらう
- Windows: Microsoft Store で「Python」を入れてもらう（`python3` の名前で動くため）。入れた後、Claude デスクトップアプリを開き直してもらう

入るまでは、スクリプトを使わずに手作業で進める。すべての手順は手作業でも進められる（遅くなるだけ）。

| スクリプト | 代わりにやること |
|---|---|
| `tn_kb.py init` | `assets/my-knowledge-template/` と同じ構成を作る |
| `tn_kb.py add-card` | `assets/card-template.md` を写して埋める。id は `C-日付-3桁の通し番号` |
| `tn_kb.py similar` | `索引.md` の同じ stage の見出しを読んで、タイトルで探す |
| `tn_kb.py index` | `索引.md` の該当の見出しの下に1行足す |
| `tn_check.py` | 各モードのチェックリストと `references/knowledge/threads-posting.md` §8 を当てる |
| `tn_paste.py` | HTML コメントを消し、有料ラインで2つに分ける。本人が埋める枠は一覧にして伝える |
| `tn_kb.py export`・`import` | まとめファイルは、区切り行 `<!-- tirnanog:file <相対パス> -->` と `<!-- tirnanog:end -->` の形を守って、手で書き足す・読み分ける |

## §6 大量の素材を受け取る時

受講生は、ファイルを添付するか、場所を書くか、長い文を貼るだけでよい。決まったフォルダに移してもらう必要はない。受け取り方は `references/modes/4_grow.md` §11。

- 長い文が貼られると、フック（プラグインに入っている小さな仕組み）が原文を `ティルナノーグ_マイナレッジ/_受け取り/` に保存し、その場所を伝えてくる
- 受け取れる形: 文字のファイル（`.txt`・`.md`・字幕の `.srt`・`.vtt`）と、チャットに貼られた文。動画・音声そのもの、Word・PDF は、文字起こしや「テキストで書き出し」をしてから渡してもらう

## §7 環境の仕様の確かめ先（2026-09-26 に確認）

画面の名前や上限は変わることがある。受講生の画面が下の説明と違う時は、ここを確かめてから案内する。

| 事実 | 確かめ先 |
|---|---|
| グリモワールの本体は Claude Code のプラグインとして配る。講座の配布元の自動更新をオンにしておくと、最初の入力から最大10分のうちに新しい版が届き、次の会話から新しい版が使われる（受講生の操作は要らない） | Claude Code Docs「Install and manage plugins」 https://code.claude.com/docs/en/plugins/install ・「Plugin loading reference」の「When auto-update runs」 https://code.claude.com/docs/en/plugins/loading |
| 作業フォルダに最初から入っていた設定で有効にしたプラグインは、配布元の外からは取ってこない。配布元の中に相対パスで置いた本体は、配布元を初めて取ってきた会話で読み込まれる。次の会話からも読み込むには、インストールの記録（登録）が要る | Claude Code Docs「Plugin loading reference」の「Enabled in project settings but not installed」 https://code.claude.com/docs/en/plugins/loading ・「Marketplace reference」の「Relative path plugin source」 https://code.claude.com/docs/en/plugins/marketplace-reference |
| Claude Code は Pro・Max・Team・Enterprise・Console のアカウントで使える。無料プランには含まれない | Claude Code Docs「Advanced setup」 https://code.claude.com/docs/en/setup （「The free claude.ai plan does not include Claude Code access.」） |
| Claude デスクトップアプリの Code タブは、選んだフォルダで Claude Code を動かす | Claude Code Docs「Desktop」 https://code.claude.com/docs/en/desktop （「Project folder: select the folder or repository Claude works in.」） |
| Claude のスキルは Free を含む全プランで使え、コード実行をオンにして zip を入れる。description は200文字まで | Claude Help Center「Use skills in Claude」 https://support.claude.com/en/articles/12512180-using-skills-in-claude ・「Creating custom skills」 https://support.claude.com/en/articles/12512198-creating-custom-skills |
| Claude のプラグインは有料プラン。同じアカウントの Claude Code にも同期される | Claude Help Center「Use plugins in Claude」 https://support.claude.com/en/articles/13837440-use-plugins-in-claude |

## §8 受講生への伝え方

- 環境の違いで受講生を責めない（「その環境では使えません」で終わらせず、半自動の手順を示す）
- 技術の言葉（Python・スクリプト など）は、受講生が聞いてきた時だけ説明する。普段は「保存」「読み込み」などの言葉で伝える
