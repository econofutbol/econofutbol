#!/usr/bin/env python3
"""Post a tweet thread from _tweet/thread.json.

Called by the GitHub Action after Pages deployment succeeds.
Requires env vars: TWITTER_API_KEY, TWITTER_API_SECRET,
                   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import tweepy

URL_RE = re.compile(r"https?://\S+")
TCO_LEN = 23  # Twitter counts any URL as 23 chars via t.co, regardless of its real length


def weighted_length(text):
    urls = URL_RE.findall(text)
    return len(URL_RE.sub("", text)) + len(urls) * TCO_LEN


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="en", choices=["en", "es"])
    args = parser.parse_args()

    tweet_dir = Path("_tweet") / args.lang
    thread_file = tweet_dir / "thread.json"

    if not thread_file.exists():
        print(f"No {thread_file} found — skipping.")
        sys.exit(0)

    thread = json.loads(thread_file.read_text())
    tweets = thread["tweets"]
    print(f"[{args.lang}] Posting {len(tweets)}-tweet thread: {thread['post']['title']}")

    # ── Auth ───────────────────────────────────────────────────────────────
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )

    # v1.1 API needed for media upload
    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    api = tweepy.API(auth)

    # ── Post thread ────────────────────────────────────────────────────────
    prev_id = None
    for i, tweet in enumerate(tweets):
        media_ids = []

        if tweet.get("image"):
            img_path = tweet_dir / tweet["image"]
            if img_path.exists():
                media = api.media_upload(str(img_path))
                media_ids.append(media.media_id)
                print(f"  Uploaded {tweet['image']}")

        # Append link if not already present in text
        body = tweet["text"]
        link = tweet.get("link", "")
        if link and link not in body:
            # Trim the body (never the link itself) against Twitter's *weighted* length --
            # a URL counts as a flat 23 chars via t.co regardless of its real character count,
            # so budgeting off raw len() here would risk truncating straight through the link.
            budget = 280 - 2 - TCO_LEN
            if len(body) > budget:
                body = body[: budget - 1] + "…"
            text = f"{body}\n\n{link}"
        else:
            text = body
            if weighted_length(text) > 280:
                text = text[:277] + "..."

        response = client.create_tweet(
            text=text,
            in_reply_to_tweet_id=prev_id,
            media_ids=media_ids or None,
        )
        prev_id = response.data["id"]
        print(f"  ✓ Tweet {i + 1}/{len(tweets)} posted (id={prev_id})")
        time.sleep(1)  # rate limit headroom

    print("\n✓ Thread posted successfully.")


if __name__ == "__main__":
    main()
