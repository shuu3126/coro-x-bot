# coro_rt_bot.py

import os
import json
from datetime import datetime
from pathlib import Path

import tweepy
from dotenv import load_dotenv

# ========== 設定 ==========
# 監視するタレントの @ID（@は付けない）
TARGET_USERS = [
    "Aomishibi",     # 青海しび
    "kurin_musee",   # 來凛みゅぜ
]

# 「配信っぽいツイート」を判定するキーワード
# （どれか1つでも含まれていればOK）
KEYWORDS = [
    "配信はじまるよ",
    "http://twitch.tv/aomishibi",
    "twitch.tv/aomishibi",
    "twitch.tv/kurin_musee",
    "次の配信",
]

# 判定に使うハッシュタグ（#は付けない）
HASHTAGS = [
    "CORO配信",
    "青海しび配信",
    "來凛みゅぜ配信",
]

# RTしたツイートIDを保存しておくファイル
RETWEETED_LOG_FILE = Path("retweeted_ids.json")

# =========================


def load_env():
    """環境変数からAPIキー類を読み込む (.env or GitHub Secrets)"""
    load_dotenv()
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        raise RuntimeError("APIキーまたはトークンが環境変数に正しく設定されていません。")

    return api_key, api_secret, access_token, access_token_secret


def create_api_client():
    """ tweepy のAPIクライアント(v1.1)を作成 """
    api_key, api_secret, access_token, access_token_secret = load_env()
    auth = tweepy.OAuth1UserHandler(
        api_key,
        api_secret,
        access_token,
        access_token_secret,
    )
    api = tweepy.API(auth, wait_on_rate_limit=True)
    # 接続テスト
    me = api.verify_credentials()
    print(f"認証ユーザー: @{me.screen_name}")
    return api


def load_retweeted_ids():
    """過去にRTしたツイートIDの集合を読み込む（なければ空）"""
    if RETWEETED_LOG_FILE.exists():
        try:
            with open(RETWEETED_LOG_FILE, "r", encoding="utf-8") as f:
                ids = json.load(f)
            return set(ids)
        except Exception:
            return set()
    return set()


def save_retweeted_ids(ids):
    """RT済みツイートID集合をファイルに保存"""
    with open(RETWEETED_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, ensure_ascii=False, indent=2)


def is_streaming_tweet(status) -> bool:
    """ツイートが配信告知っぽいか判定"""

    # v1.1 で tweet_mode="extended" を使うと full_text が入る
    text = getattr(status, "full_text", status.text or "")
    lowered = text.lower()

    # ① リプライ（先頭が@）は除外
    if text.strip().startswith("@"):
        return False

    # ② 引用RTやリツイートは除外しておく
    if hasattr(status, "retweeted_status"):
        return False

    # ③ キーワード判定（どれか1つでも含まれていればOK）
    for kw in KEYWORDS:
        if kw.lower() in lowered:
            return True

    # ④ ハッシュタグ判定
    if hasattr(status, "entities"):
        hashtags = status.entities.get("hashtags", [])
        tag_texts = [h["text"] for h in hashtags]
        for tag in tag_texts:
            if tag in HASHTAGS:
                return True

    # ⑤ URLに配信サイトが含まれるか（YouTube / Twitch など）
    if hasattr(status, "entities"):
        urls = status.entities.get("urls", [])
        expanded_urls = [u.get("expanded_url", "") for u in urls]
        for u in expanded_urls:
            if any(service in u for service in ["youtube.com", "youtu.be", "twitch.tv", "nicovideo.jp"]):
                return True

    return False


def fetch_and_rt_for_user(api: tweepy.API, screen_name: str, already_rt_ids: set):
    """
    特定ユーザーの最新ツイートを取得して、
    配信告知だったら公式アカでRTする
    """
    print(f"--- @{screen_name} のタイムラインをチェック ---")
    try:
        statuses = api.user_timeline(
            screen_name=screen_name,
            count=10,             # 最新10件で十分
            tweet_mode="extended" # 140字超のツイート対応
        )
    except Exception as e:
        print(f"[ERROR] @{screen_name} の取得に失敗: {e}")
        return

    for status in statuses:
        tweet_id = status.id

        # 既にRTしたツイートはスキップ
        if tweet_id in already_rt_ids:
            continue

        if is_streaming_tweet(status):
            try:
                api.retweet(tweet_id)
                already_rt_ids.add(tweet_id)
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] RTしました: "
                    f"https://x.com/{screen_name}/status/{tweet_id}"
                )
            except Exception as e:
                # 「既にRT済み」などでエラーになることもある
                print(f"[ERROR] RT失敗 tweet_id={tweet_id}: {e}")
        else:
            # デバッグ用：どんなツイートをスキップしているか先頭だけ表示
            text = getattr(status, "full_text", status.text or "")
            print(f"[SKIP] 条件に合わないツイート: {tweet_id} | {text[:50]}")


def main():
    print("=== CORO PROJECT 配信告知 自動RTボット（1回実行モード） ===")
    api = create_api_client()
    already_rt_ids = load_retweeted_ids()
    print(f"過去ログ読み込み: {len(already_rt_ids)} 件")

    # GitHub Actions から呼ばれたら「一周だけ」チェックして終了
    for user in TARGET_USERS:
        fetch_and_rt_for_user(api, user, already_rt_ids)

    save_retweeted_ids(already_rt_ids)
    print("今回のチェックが完了しました。")


if __name__ == "__main__":
    main()
