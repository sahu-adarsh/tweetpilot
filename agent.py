#!/usr/bin/env python3
"""
Daily Twitter agent for Adarsh Sahu (@adarshsahu27).
Generates and posts one engaging tweet per day using Claude Haiku.

Usage:
    python agent.py            # Generate and post
    python agent.py --dry-run  # Generate only, do not post
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
import requests
import tweepy
from dotenv import load_dotenv

load_dotenv()

HISTORY_FILE = Path(__file__).parent / "tweet_history.json"
CONTEXT_FILE = Path(__file__).parent / "context.txt"
REPLIES_FILE = Path(__file__).parent / "replies.txt"

SKIP_PROBABILITY = 0.25        # 25% skip per run → ~10.5 posts/week across 2 daily windows
MAX_DELAY_SECONDS = 5400       # up to 90 min after cron fires
MAX_TWEETS_PER_DAY = 2         # hard cap so back-to-back runs can't over-post
SHORT_TWEET_PROBABILITY = 0.30 # 30% chance of a single-sentence sub-80-char tweet

PERSONA = """
You are ghostwriting a tweet for Adarsh Sahu (@adarshsahu27), a 23-year-old Senior Software Engineer at HCLTech in Bangalore.

Who he is:
- Builds production AI/ML systems at HCLTech: LangGraph multi-agent pipelines, regulatory content ingestion
  at 1,000+ articles/day, an agentic KYC platform with 89.9% F1 on AML/PEP risk classification
- Creator of Intervyu.io: AI voice interview platform using Deepgram STT + Claude Haiku 4.5 (AWS Bedrock) +
  Azure TTS. Cut first-audio latency from ~6s to ~1.7s, $0.76 vs $3.15/session vs competitors.
- Creator of Epistlo: custom RFC-compliant SMTP/IMAP mail server with real @epistlo.com mailboxes,
  asyncio-based, with three-tier graceful degradation (Elasticsearch → Supabase, Redis → DB, S3 → disk).
- LeetCode Knight (rating 2035, 1000+ problems solved)
- Brazilian Jiu-Jitsu National Gold Medalist
- AWS Certified Data Engineer + ML Engineer Associate, Google Cloud Professional Data Engineer
- NITK IT'24 graduate; based in Bangalore
- Stack: Python, FastAPI, LangGraph, LangChain, CrewAI, asyncio, AWS, Azure, PostgreSQL, Redis

HOW HE ACTUALLY WRITES:
He tweets like a developer talking to another developer, not like someone writing content.
Contractions, short sentences, incomplete thoughts when it fits. He doesn't always have a lesson.
Sometimes he just drops an observation or a number and lets it sit.
He uses lowercase sometimes. He doesn't over-explain.

GOOD tweet examples (notice: casual, specific, no formula):
- "replaced an httpx client with a singleton and deepgram latency went from 3726ms to 620ms. just one line."
- "built an SMTP server from scratch last year. RFC 5321 is surprisingly readable once you stop being scared of it."
- "people underestimate how much of 'AI engineering' is just data cleaning and retry logic"
- "1000 leetcode problems in. still get humbled by DP."
- "BJJ and debugging have the same lesson: if you're using too much force, you're doing it wrong"

BAD tweet examples (avoid these patterns entirely):
- "Here's what I learned after 6 months of building X: [perfectly structured list]"
- "Hot take: [opinion]. Here's why: [explanation]. What do you think?"
- "Most developers don't realize that [insight]. This is why [lesson]."
- "Excited to share that I've been working on [project]! Key learnings: 1) ... 2) ... 3) ..."
- Anything with em dashes (— or –)
- Anything that sounds like a LinkedIn post
"""

CONTENT_BUCKETS = [
    "AI/LLM engineering: something real from building multi-agent pipelines, RAG, or LLM systems in production",
    "Python async/performance: a concrete observation about asyncio, FastAPI, httpx, or concurrency",
    "LeetCode/DSA: a thought from a Knight-level (2035 rating, 1000+ solved) perspective",
    "System design: a specific tradeoff or architectural decision from real experience",
    "AI in production: something that surprised you vs. what tutorials show",
    "Cloud/serverless: an AWS or Azure observation from actual usage",
    "Building Intervyu.io or Epistlo: something specific that happened, a number, a mistake, a win",
    "Career/engineering: a sharp observation about how senior engineers think vs. juniors",
    "BJJ and coding: a principle from martial arts that maps onto software or learning",
    "Honest opinion: something you actually believe about AI tools, LLMs, or engineering culture",
    "A genuine question you're curious about, aimed at other engineers",
]

TWEET_FORMATS = [
    "One or two sentences. Drop a specific observation and stop.",
    "Lead with a number or a result, then one line of context.",
    "Short personal story: what happened, what you noticed. No explicit lesson.",
    "A question you actually want answered. Not rhetorical.",
    "A take stated plainly. No preamble, no 'here's why'.",
    "Two contrasting things. Let the reader connect them.",
]

DAY_CONTEXT = {
    "Monday": "energy is high, good for a motivational insight or a bold hot take",
    "Tuesday": "midweek grind, good for a technical tip or deep system insight",
    "Wednesday": "hump day, good for a relatable engineering observation or career reflection",
    "Thursday": "momentum building, good for a project highlight or specific achievement with numbers",
    "Friday": "end of week, good for a reflection, lesson learned, or engaging community question",
    "Saturday": "weekend mode, good for a mindset/BJJ parallel or side-project story",
    "Sunday": "rest day vibe, good for a philosophical take on building or learning",
}


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []


def save_history(history: list[dict], tweet_text: str) -> None:
    history.append({
        "date": datetime.now().isoformat(),
        "tweet": tweet_text,
    })
    HISTORY_FILE.write_text(json.dumps(history[-30:], indent=2))


def tweets_today(history: list[dict]) -> int:
    today = datetime.now().date().isoformat()
    return sum(1 for t in history if t["date"].startswith(today))


def load_context() -> str:
    """Read non-comment lines from context.txt, clear them, keep the comment template."""
    if not CONTEXT_FILE.exists():
        return ""
    lines = CONTEXT_FILE.read_text().splitlines()
    comments = [l for l in lines if l.startswith("#") or l.strip() == ""]
    content_lines = [l for l in lines if not l.startswith("#") and l.strip()]
    if content_lines:
        CONTEXT_FILE.write_text("\n".join(comments) + "\n")
    return " ".join(content_lines)


def fetch_hn_headlines(n: int = 5) -> list[str]:
    """Fetch top HN story titles. Returns empty list on any network failure."""
    try:
        ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=5,
        ).json()[:20]
        titles = []
        for story_id in ids:
            if len(titles) >= n:
                break
            item = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                timeout=5,
            ).json()
            if item.get("type") == "story" and item.get("title"):
                titles.append(item["title"])
        return titles
    except Exception:
        return []


def load_reply_target() -> tuple[str | None, str, bool]:
    """
    Parse replies.txt for a pending reply or quote-tweet.
    Line format:
      <tweet_url_or_id> :: <what the tweet says / your angle>     → reply
      QT <tweet_url_or_id> :: <what the tweet says / your angle>  → quote-tweet
    Returns (tweet_id, context, is_quote). Removes only the consumed line, keeps comments.
    """
    if not REPLIES_FILE.exists():
        return None, "", False

    lines = REPLIES_FILE.read_text().splitlines()
    comments = [l for l in lines if l.startswith("#") or l.strip() == ""]
    entries = [l for l in lines if not l.startswith("#") and l.strip()]

    for entry in entries:
        raw = entry.strip()
        is_quote = raw.upper().startswith("QT ")
        if is_quote:
            raw = raw[3:].strip()
        if "::" not in raw:
            continue  # skip malformed lines, don't remove them

        url_part, context = raw.split("::", 1)
        url_part = url_part.strip()
        context = context.strip()
        match = re.search(r"/status/(\d+)", url_part)
        tweet_id = match.group(1) if match else re.sub(r"\D", "", url_part)

        if not tweet_id:
            continue

        # Remove only this entry
        remaining = [e for e in entries if e != entry]
        REPLIES_FILE.write_text("\n".join(comments + remaining) + "\n")
        return tweet_id, context, is_quote

    return None, "", False


def generate_reply(tweet_context: str, is_quote: bool) -> str:
    """Generate a reply or quote-tweet given a plain-text summary of the original tweet."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    mode = "quote-tweet" if is_quote else "reply"
    prompt = f"""You are ghostwriting a {mode} for Adarsh Sahu (@adarshsahu27).

{PERSONA}

The tweet Adarsh is responding to:
"{tweet_context}"

Write ONE {mode} from Adarsh.

Rules:
- Max 240 characters (leave room for the quoted URL if it's a QT)
- Do NOT start with "@" — Twitter adds the handle automatically for replies
- Add something: a personal angle, a number from his own experience, a counterpoint, or a specific detail that makes the reply worth reading
- Do not just agree or just say "this" — add actual signal
- No em dashes (— or –). Use comma or colon instead.
- No automated-sounding openers
- Write in first person as Adarsh
- Output ONLY the tweet text, nothing else"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip().strip('"').strip("'")
    return sanitize_tweet(raw)


def sanitize_tweet(text: str) -> str:
    # Hard backstop: replace em/en dashes regardless of what the model outputs
    return text.replace("—", ",").replace("–", "-").strip()


def generate_tweet(
    history: list[dict],
    context: str = "",
    headlines: list[str] | None = None,
    short: bool = False,
) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    day = datetime.now().strftime("%A")
    date_str = datetime.now().strftime("%B %d, %Y")
    day_hint = DAY_CONTEXT.get(day, "")
    content_bucket = random.choice(CONTENT_BUCKETS)
    tweet_format = random.choice(TWEET_FORMATS)

    recent = "\n".join(
        f"- {t['tweet'][:120]}" for t in history[-7:]
    ) if history else "None yet."

    context_section = (
        f"\nWhat Adarsh is actually doing / thinking today (use this as the seed):\n{context}\n"
        if context else ""
    )

    hn_section = ""
    if headlines:
        hn_section = (
            "\nToday's top HackerNews headlines — use one as a jumping-off point ONLY if it"
            " genuinely connects to your stack or interests. If none fit, ignore them all:\n"
            + "\n".join(f"- {h}" for h in headlines)
            + "\n"
        )

    length_rule = (
        "- ONE sentence only, under 80 characters, no hashtags"
        if short else
        "- Max 260 characters\n- 0-1 hashtags, only if it genuinely fits, at the end"
    )

    prompt = f"""Today is {day}, {date_str}. Day context: {day_hint}.
{context_section}{hn_section}
{PERSONA}

Write ONE tweet for Adarsh to post today.

Content angle: {content_bucket}
Shape: {tweet_format}

Recent tweets (avoid repeating the same topic or shape):
{recent}

Rules:
{length_rule}
- NO em dashes (— or –). Use a comma, period, or colon instead.
- NO automated-sounding openers or closers of any kind
- NO perfect 3-part structure (hook / detail / takeaway)
- NO "What do you think?", "Let me know", "Drop a comment"
- Specific over vague: real tech names, real numbers, real tradeoffs
- Write in first person as Adarsh
- Output ONLY the tweet text, nothing else"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip().strip('"').strip("'")
    return sanitize_tweet(raw)


def post_tweet(
    tweet_text: str,
    reply_to_id: str | None = None,
    quote_id: str | None = None,
) -> str:
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    kwargs: dict = {"text": tweet_text}
    if reply_to_id:
        kwargs["in_reply_to_tweet_id"] = reply_to_id
    if quote_id:
        kwargs["quote_tweet_id"] = quote_id
    response = client.create_tweet(**kwargs)
    return response.data["id"]


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    history = load_history()

    # Hard daily cap — prevents double-posting if cron windows overlap
    if not dry_run and tweets_today(history) >= MAX_TWEETS_PER_DAY:
        print(f"[{timestamp}] Already hit {MAX_TWEETS_PER_DAY} tweets today. Skipping.")
        return

    # Random skip (~25% per run) — keeps weekly cadence feeling organic
    if not dry_run and random.random() < SKIP_PROBABILITY:
        print(f"[{timestamp}] Skipping this window.")
        return

    # Random delay so posts don't land at the exact cron-fire time
    if not dry_run:
        delay = random.randint(0, MAX_DELAY_SECONDS)
        print(f"[{timestamp}] Waiting {delay // 60}m {delay % 60}s before posting...")
        time.sleep(delay)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Reply / quote-tweet takes priority over original tweet for this window
    reply_id, reply_context, is_quote = load_reply_target()
    if reply_id:
        mode = "Quote-tweet" if is_quote else "Reply"
        print(f"[{timestamp}] {mode} target: {reply_id} — {reply_context[:60]}...")
        tweet = generate_reply(reply_context, is_quote)
        char_count = len(tweet)
        print(f"[{timestamp}] Generated {mode.lower()} ({char_count} chars):\n\n  {tweet}\n")
        if dry_run:
            print("[DRY RUN] Skipping post.")
            return
        try:
            tweet_id = post_tweet(
                tweet,
                reply_to_id=None if is_quote else reply_id,
                quote_id=reply_id if is_quote else None,
            )
            save_history(history, tweet)
            print(f"[{timestamp}] Posted! https://twitter.com/adarshsahu27/status/{tweet_id}")
        except tweepy.errors.TweepyException as e:
            print(f"[ERROR] Failed to post: {e}")
            sys.exit(1)
        return

    context = load_context()
    if context:
        print(f"[{timestamp}] Using context: {context[:80]}{'...' if len(context) > 80 else ''}")

    headlines = fetch_hn_headlines()
    if headlines:
        print(f"[{timestamp}] Fetched {len(headlines)} HN headlines.")

    short = random.random() < SHORT_TWEET_PROBABILITY
    if short:
        print(f"[{timestamp}] Short tweet mode.")

    tweet = generate_tweet(history, context, headlines, short)

    char_count = len(tweet)
    print(f"[{timestamp}] Generated tweet ({char_count} chars):\n\n  {tweet}\n")

    if char_count > 280:
        print(f"[WARN] Tweet is {char_count} chars — Twitter limit is 280. Truncating risk.")

    if dry_run:
        print("[DRY RUN] Skipping post. Remove --dry-run to go live.")
        return

    try:
        tweet_id = post_tweet(tweet)
        save_history(history, tweet)
        print(f"[{timestamp}] Posted! https://twitter.com/adarshsahu27/status/{tweet_id}")
    except tweepy.errors.TweepyException as e:
        print(f"[ERROR] Failed to post tweet: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
