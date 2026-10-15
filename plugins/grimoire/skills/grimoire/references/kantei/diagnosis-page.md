# 診断ページを作る（完全版）

「質問8問・結果4タイプ・それぞれの解説文とLINEへのボタン」の診断ページを、1つの HTML ファイルで作る。

## 手順

1. 設計シート（`ティルナノーグ_マイナレッジ/鑑定/導線.md`）のタイプ分けの軸・キーワード・LINEの友だち追加URLを確認する。URLが無ければ空けたまま進め、最後に差し替え方を伝える
2. `.grimoire/assets/kantei/diagnosis-config-sample.json` を `ティルナノーグ_制作物/鑑定/診断/設定.json` に写し、中身を利用者の内容に書き換える
   - `title`: 診断の名前（例：「あなたの金運の癖 診断」）。結果を約束する名前にしない
   - `lead`: 1〜2文。何が分かるか・何分で終わるか
   - `questions`: 8問。各問に選択肢4つ、選択肢ごとに当たるタイプ（A〜D）。どのタイプも同じくらい選ばれるように、各問に全タイプの選択肢を1つずつ置く
   - 質問は日常の場面で書く（「お金を使った日の夜、どんな気持ちになりますか？」）。答えにくい個人情報は聞かない
   - `types`: 各タイプの `name`（結果の名前）・`keyword`（LINEで送る言葉。タイプごとに違う短い言葉）・`summary`（1〜2文）・`detail`（3〜5文。持ち味を先に、つまずきやすい所は責めずに）・`tip`（今日できる一歩）
   - `line_url`: LINEの友だち追加URL（https:// で始まる）
   - `tracking_url`: 数字を受け取る先（下の§測る）。まだ無ければ空
   - `disclaimer`: 「占いによる診断で、結果を約束するものではありません」
3. 点検して書き出す

```
python3 .grimoire/scripts/kantei/build_diagnosis_page.py ティルナノーグ_制作物/鑑定/診断/設定.json --check
python3 .grimoire/scripts/kantei/build_diagnosis_page.py ティルナノーグ_制作物/鑑定/診断/設定.json ティルナノーグ_制作物/鑑定/診断/index.html
```

道具は、質問数・タイプ数・選択肢のタイプ・キーワードの重なり・URLの形・安全ルールの言葉を点検し、問題があれば直す所を出す。

4. 利用者に、ブラウザで `index.html` を開いて最後まで1回通してもらう（結果・キーワードのコピー・LINEボタンが動くか）

## 置き場所（公開は利用者が行う）

HTML 1ファイルで、外部の読み込みを使っていないので、次のどれにも置ける。どれを使うかは利用者に選んでもらい、手順を案内する。
- UTAGE などのページ作成機能に、HTML を貼れる欄があればそこに貼る
- 無料の静的ホスティング（ファイルを置くだけで公開できるサービス）
- 自分のサイトのサーバー

## 測る（診断を始めた人・終えた人・LINEを押した人）

ページは、`start`（始めた）・`finish`（終えた）・`line_click`（LINEボタン）・`keyword_copy`（キーワードをコピー）の4つを、`tracking_url` に送る。受け取り先の一番簡単な作り方は、Google スプレッドシートに次の Apps Script を付けて「ウェブアプリ」として公開し、その URL を `tracking_url` に入れる方法。

```javascript
function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  var d = JSON.parse(e.postData.contents);
  sheet.appendRow([new Date(), d.event, d.type || '', d.session, d.page]);
  return ContentService.createTextOutput('ok');
}
```

公開の設定（アクセスできるユーザー）は、利用者が自分のアカウントで確認して行う。受け取り先が無い間は数字は送られない（ページは普通に動く）。週に1回、スプレッドシートの件数を数えて `weekly-review.md` の表に入れる。
