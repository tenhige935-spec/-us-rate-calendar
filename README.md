# 米金利イベントカレンダー（iPhone PWA版）

iPhone Safariで開いて「共有 → ホーム画面に追加」すると、アプリのように起動できます。

## 主な機能
- 月単位のカレンダー
- iPhone SEクラスの画面幅に対応
- 日付タップで当日のイベント詳細
- 重要度（★★★〜★★★★★）・カテゴリ絞り込み
- 金利上昇/低下につながりやすい結果の解説
- SBG・NASDAQ・半導体への影響メモ
- BLS / BEA / FRB 公式日程を毎日自動更新
- オフライン起動対応（PWA）

## 無料で自動更新させる方法（GitHub Pages）
1. このフォルダ一式をGitHubの新しいリポジトリへアップロード。
2. GitHubの `Settings > Pages` で `Deploy from a branch` を選び、`main / root` を公開。
3. `Settings > Actions > General` でActionsを許可。
4. `.github/workflows/update-events.yml` が毎日実行され、`data/events.json` を更新・コミットします。
5. iPhone Safariで公開URLを開き、「共有 → ホーム画面に追加」。

## 自動取得元
- BLS Online Calendar (ICS): CPI、雇用統計、JOLTS、PPI、輸出入物価、生産性など
- BEA Release Schedule: PCE、GDP、貿易など
- Federal Reserve FOMC Calendar: FOMC会合

※ 市場予想値・発表結果の自動取得はこの版には含めていません。公式「発表日程」の自動更新が中心です。
