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

import asyncio

import requests
from dotenv import load_dotenv
from openai import OpenAI
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent / ".env")

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ["AZURE_INFERENCE_ENDPOINT"],
            api_key=os.environ["AZURE_INFERENCE_KEY"],
        )
    return _client


def invoke_claude_json(messages: list[dict], max_tokens: int = 350) -> str:
    response = _get_client().chat.completions.create(
        model=os.environ["AZURE_INFERENCE_MODEL"],
        max_completion_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content.strip()


def invoke_claude_stream(messages: list[dict], max_tokens: int = 350) -> str:
    stream = _get_client().chat.completions.create(
        model=os.environ["AZURE_INFERENCE_MODEL"],
        max_completion_tokens=max_tokens,
        messages=messages,
        stream=True,
    )
    parts = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            parts.append(delta)
    return "".join(parts)


HISTORY_FILE = Path(__file__).parent / "tweet_history.json"
CONTEXT_FILE = Path(__file__).parent / "context.txt"
REPLIES_FILE = Path(__file__).parent / "replies.txt"
SESSION_FILE = Path(__file__).parent / "tw_session.json"

SKIP_PROBABILITY = 0.10        # 10% skip per run → ~5 posts/day across 6 daily windows
MAX_DELAY_SECONDS = 1800       # up to 30 min after cron fires (keeps posts in their window)
MAX_TWEETS_PER_DAY = 6         # hard cap so back-to-back runs can't over-post
SHORT_TWEET_PROBABILITY = 0.20 # 20% chance of a single-sentence sub-80-char tweet
THREAD_PROBABILITY = 0.20      # 20% chance of a 2-3 tweet thread instead of single tweet
HN_TAKE_PROBABILITY = 0.20     # 20% chance of a direct opinionated take on the top HN story

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

MENTION_GUIDE = """
@mentions — add ONLY when the tweet is specifically about that tool/company (never forced):
- LangGraph, LangChain, LangSmith → @LangChainAI
- Deepgram → @DeepgramAI
- AWS, Bedrock, Lambda, SageMaker → @awscloud
- Azure, Azure AI Foundry → @Azure
- LeetCode → @LeetCode
- FastAPI → @tiangolo
- OpenAI, GPT → @OpenAI
- HuggingFace → @huggingface
- Supabase → @supabase
- Redis → @Redisinc
Place @mention naturally in the tweet body or at the very end. Never start the tweet with @.
"""

HASHTAG_GUIDE = """
Hashtags — 0-2 at the end, only if they genuinely fit (do not force them):
#Python #FastAPI #asyncio #LLM #AI #MLOps #LangChain #AWS #Azure #LeetCode #DSA #RAG #BuildInPublic #AIEngineering
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

    raw = invoke_claude_json(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    return sanitize_tweet(raw.strip('"').strip("'"))


def sanitize_tweet(text: str) -> str:
    # Hard backstop: replace em/en dashes regardless of what the model outputs
    return text.replace("—", ",").replace("–", "-").strip()


def generate_tweet(
    history: list[dict],
    context: str = "",
    headlines: list[str] | None = None,
    short: bool = False,
) -> str:
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
        "- ONE sentence only, under 80 characters, no hashtags, no @mentions"
        if short else
        f"- Max 260 characters\n{MENTION_GUIDE}\n{HASHTAG_GUIDE}"
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
- Drop real metrics where relevant: latency in ms, F1 scores, cost per session, counts
- Write in first person as Adarsh
- Output ONLY the tweet text, nothing else"""

    raw = invoke_claude_stream(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=350,
    )
    return sanitize_tweet(raw.strip('"').strip("'"))


def generate_thread(
    history: list[dict],
    context: str = "",
    headlines: list[str] | None = None,
) -> list[str]:
    """Generate a 2-3 tweet thread. Returns a list of tweet strings."""
    day = datetime.now().strftime("%A")
    date_str = datetime.now().strftime("%B %d, %Y")
    content_bucket = random.choice(CONTENT_BUCKETS)
    recent = "\n".join(f"- {t['tweet'][:120]}" for t in history[-7:]) if history else "None yet."
    context_section = f"\nContext: {context}\n" if context else ""
    hn_section = (
        "\nTop HN headlines for context:\n" + "\n".join(f"- {h}" for h in headlines) + "\n"
        if headlines else ""
    )

    prompt = f"""Today is {day}, {date_str}.
{context_section}{hn_section}
{PERSONA}

Write a Twitter THREAD of 2-3 tweets for Adarsh.

Content angle: {content_bucket}

Recent tweets (avoid repeating):
{recent}

Rules:
- Tweet 1: the hook. One sharp result, observation, or number. Max 240 chars.
- Tweet 2: expand with specifics — what you did, what surprised you, a contrast. Max 260 chars.
- Tweet 3 (optional): a takeaway, a question, or something that reframes tweet 1. Max 200 chars. Only include if it genuinely adds value.
- Each tweet must read well standalone AND connect to the others as a thread.
- Do NOT number the tweets (no "1/", "2/", "🧵").
- Do NOT open with "Thread:" or any announcement.
- No em dashes (— or –).
- Real numbers, real tool names, real tradeoffs.
{MENTION_GUIDE}
{HASHTAG_GUIDE}
- Write in first person as Adarsh.

Output ONLY a JSON array of 2 or 3 tweet strings. No explanation, no markdown.
Example: ["tweet one", "tweet two", "tweet three"]"""

    raw = invoke_claude_json(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        return [sanitize_tweet(raw)]
    tweets = json.loads(match.group())
    return [sanitize_tweet(str(t).strip('"').strip("'")) for t in tweets]


def generate_hn_take(headline: str, history: list[dict]) -> str:
    """Generate a direct opinionated tweet reacting to a top HN headline."""
    recent = "\n".join(f"- {t['tweet'][:120]}" for t in history[-5:]) if history else "None yet."

    prompt = f"""You are ghostwriting a tweet for Adarsh Sahu (@adarshsahu27).

{PERSONA}

Top HackerNews story right now: "{headline}"

Write ONE tweet where Adarsh gives his genuine opinion or a sharp related insight about this topic.

Rules:
- Max 260 characters
- Must connect to Adarsh's actual experience (AI engineering, Python, LangGraph, Intervyu.io, Epistlo, LeetCode, BJJ)
- If the story isn't relevant to his background, pivot to a related real experience instead of forcing it
- Specific over vague: real numbers, real tools, real tradeoffs
- Drop real metrics where relevant: latency in ms, F1, cost/session
{MENTION_GUIDE}
{HASHTAG_GUIDE}
- No em dashes (— or –)
- No "Hot take:", no preamble
- Write in first person as Adarsh

Recent tweets (avoid repeating shape or topic):
{recent}

Output ONLY the tweet text, nothing else."""

    raw = invoke_claude_stream(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=350,
    )
    return sanitize_tweet(raw.strip('"').strip("'"))


def post_thread(tweets: list[str]) -> list[str]:
    """Post a thread. Returns list of tweet IDs."""
    ids = []
    reply_to = None
    for tweet in tweets:
        tweet_id = post_tweet(tweet, reply_to_id=reply_to)
        ids.append(tweet_id)
        reply_to = tweet_id
    return ids


async def _post_tweet_async(
    tweet_text: str,
    reply_to_id: str | None = None,
    quote_id: str | None = None,
) -> str:
    if not SESSION_FILE.exists():
        raise RuntimeError("No Twitter session found. Run: python3 tw_setup.py")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(SESSION_FILE))
        page = await context.new_page()

        tweet_id = None

        async def on_response(response):
            nonlocal tweet_id
            if "CreateTweet" in response.url and tweet_id is None:
                try:
                    body = await response.json()
                    tweet_id = body["data"]["create_tweet"]["tweet_results"]["result"]["rest_id"]
                except Exception:
                    pass

        page.on("response", on_response)

        async def type_into_composer(text: str) -> None:
            # Click the placeholder ("What is happening?!") to activate the compose box
            placeholder = page.locator('[data-testid="tweetTextarea_0placeholder"]')
            if await placeholder.count() > 0:
                await placeholder.first.click()
            textarea = page.locator('[data-testid="tweetTextarea_0"]').first
            await textarea.wait_for(state="visible", timeout=10000)
            await textarea.click()
            await page.keyboard.type(text, delay=50)
            await page.wait_for_selector(
                '[data-testid="tweetButtonInline"]:not([disabled])', timeout=10000
            )

        if reply_to_id:
            await page.goto(f"https://x.com/i/status/{reply_to_id}")
            await page.wait_for_selector('[data-testid="reply"]', timeout=15000)
            await page.click('[data-testid="reply"]')
            await type_into_composer(tweet_text)
            await page.locator('[data-testid="tweetButton"]').last.click()
        elif quote_id:
            await page.goto("https://x.com/home")
            await type_into_composer(f"{tweet_text} https://x.com/i/status/{quote_id}")
            await page.locator('[data-testid="tweetButtonInline"]').first.click()
        else:
            await page.goto("https://x.com/home")
            await type_into_composer(tweet_text)
            await page.locator('[data-testid="tweetButtonInline"]').first.click()

        await page.wait_for_timeout(4000)
        await browser.close()
        return tweet_id or "unknown"


def post_tweet(
    tweet_text: str,
    reply_to_id: str | None = None,
    quote_id: str | None = None,
) -> str:
    return asyncio.run(_post_tweet_async(tweet_text, reply_to_id, quote_id))


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
        except Exception as e:
            print(f"[ERROR] Failed to post: {e}")
            sys.exit(1)
        return

    context = load_context()
    if context:
        print(f"[{timestamp}] Using context: {context[:80]}{'...' if len(context) > 80 else ''}")

    headlines = fetch_hn_headlines()
    if headlines:
        print(f"[{timestamp}] Fetched {len(headlines)} HN headlines.")

    roll = random.random()

    # --- Thread mode (20%) ---
    if roll < THREAD_PROBABILITY:
        print(f"[{timestamp}] Thread mode.")
        tweets = generate_thread(history, context, headlines)
        for i, t in enumerate(tweets, 1):
            print(f"[{timestamp}] Thread tweet {i}/{len(tweets)} ({len(t)} chars):\n\n  {t}\n")
        if dry_run:
            print("[DRY RUN] Skipping post.")
            return
        try:
            ids = post_thread(tweets)
            for tweet_text, tweet_id in zip(tweets, ids):
                save_history(history, tweet_text)
                print(f"[{timestamp}] Posted! https://twitter.com/adarshsahu27/status/{tweet_id}")
        except Exception as e:
            print(f"[ERROR] Failed to post thread: {e}")
            sys.exit(1)

    # --- HN take mode (20%) ---
    elif roll < THREAD_PROBABILITY + HN_TAKE_PROBABILITY and headlines:
        print(f"[{timestamp}] HN take mode: {headlines[0][:60]}...")
        tweet = generate_hn_take(headlines[0], history)
        print(f"[{timestamp}] Generated tweet ({len(tweet)} chars):\n\n  {tweet}\n")
        if dry_run:
            print("[DRY RUN] Skipping post.")
            return
        try:
            tweet_id = post_tweet(tweet)
            save_history(history, tweet)
            print(f"[{timestamp}] Posted! https://twitter.com/adarshsahu27/status/{tweet_id}")
        except Exception as e:
            print(f"[ERROR] Failed to post tweet: {e}")
            sys.exit(1)

    # --- Regular single tweet (60%) ---
    else:
        short = random.random() < SHORT_TWEET_PROBABILITY
        if short:
            print(f"[{timestamp}] Short tweet mode.")
        tweet = generate_tweet(history, context, headlines, short)
        print(f"[{timestamp}] Generated tweet ({len(tweet)} chars):\n\n  {tweet}\n")
        if len(tweet) > 280:
            print(f"[WARN] Tweet is {len(tweet)} chars — over 280 limit.")
        if dry_run:
            print("[DRY RUN] Skipping post.")
            return
        try:
            tweet_id = post_tweet(tweet)
            save_history(history, tweet)
            print(f"[{timestamp}] Posted! https://twitter.com/adarshsahu27/status/{tweet_id}")
        except Exception as e:
            print(f"[ERROR] Failed to post tweet: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
