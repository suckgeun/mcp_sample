# Google検索AIエージェント

このプロジェクトは、Google検索APIを使用したAIエージェントのサンプルコードです。uvというPythonパッケージマネージャーを使って実行します。

## プロジェクトの構成

### ホスト（AIエージェント）

1. **agent_chat_with_google_search.py**
   * mcpサーバのfetchと、google searchを基に回答するcli基盤のチャット

2. **agent_company_analyze.py**
   * 日本の企業を分析するAIエージェント。必要情報が揃うまでにループするので注意が必要。少しバグあり

### MCPサーバー

1. **server_google_search.py**
   * 公式google apiを使ったgoogle検索サーバ。google 検索の上位5個を返す

## 準備するもの

1. Python 3.12以上
2. uvパッケージマネージャー
3. Google検索APIのキー
4. OpenAI APIキー

## 環境構築の手順

### 1. uvのインストール

uvはPythonのパッケージマネージャーで、依存関係を簡単に管理できます。

```bash
# curlを使ってuvをインストール
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Google APIの設定

1. [Google Cloud Console](https://console.cloud.google.com)にアクセスし、プロジェクトを作成または選択
2. 「APIとサービス」→「ライブラリ」から「Custom Search API」を有効化
3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「APIキー」でAPIキーを作成（これが`GOOGLE_CSE_API_KEY`）
4. [Programmable Search Engine](https://programmablesearchengine.google.com/about/)にアクセスし、検索エンジンを作成
5. 検索エンジンの設定ページから検索エンジンID（cx値）をコピー（これが`GOOGLE_CSE_ID`）

※ Google APIは1日100クエリまで無料、それ以上は1,000リクエストあたり5ドルの料金がかかります（1日最大10,000リクエストまで）

### 3. OpenAI APIキーの取得

1. [OpenAIのウェブサイト](https://platform.openai.com/)でアカウントを作成
2. APIキーを発行（有料サービスなので注意）

### 4. 環境変数の設定

プロジェクトのルートディレクトリに`.env.sample`ファイルを参考に`.env`ファイルを作成し、以下の内容を設定します：

```env
OPENAI_API_KEY=あなたのOpenAI APIキー
GOOGLE_CSE_API_KEY=あなたのGoogle APIキー
GOOGLE_CSE_ID=あなたの検索エンジンID
```

## MCPサーバーの設定

エージェントファイル内では、MCPサーバーの設定が以下のように定義されています：

```python
RAW_CONFIG: Dict[str, dict] = {
    "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
    "google_search": {
        "command": "uv",
        "args": ["--directory", "/path/to/your/project/servers/src", "run", "server_google_search.py"],
    },
}
```

**注意**: 実際に使用する際は、`/path/to/your/project/servers/src`の部分を、あなたの環境に合わせたパスに変更する必要があります。

## 実行方法

プロジェクトのルートディレクトリで以下のコマンドを実行します：

### Google検索チャットボットの実行

```bash
uv --directory "/path/to/your/project/host/src" run agent_chat_with_google_search.py
```

### 企業分析エージェントの実行

```bash
uv --directory "/path/to/your/project/host/src" run agent_company_analyze.py
```

**重要**: 上記のコマンドを実行する前に、エージェントファイル内のMCPサーバー設定パス（RAW_CONFIG内の`--directory`引数）を、あなたの環境に合わせて修正してください。

## よくある問題と解決方法

### APIキーが認識されない場合

- `.env`ファイルがプロジェクトのルートディレクトリに正しく配置されているか確認
- ファイル内のAPIキーに余分な空白や引用符がないか確認

### Google APIのクォータ制限に達した場合

- 1日の無料クォータ（100リクエスト）を超えると料金が発生
- Google Cloud Consoleでクォータと使用状況を確認
