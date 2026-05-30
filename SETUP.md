# Twitter Agent — Setup Guide

## 1. Get Twitter API Credentials (Free)

1. Go to [developer.twitter.com](https://developer.twitter.com) and sign in with your **@adarshsahu27** account.
2. Click **"Sign up for Free Account"** → fill in the use-case form.
   - Use case: *"Posting automated tweets from my personal account to share engineering insights."*
3. After approval, go to the **Developer Portal → Projects & Apps → Create App**.
4. Under your app → **Settings → User authentication settings**:
   - Enable **OAuth 1.0a**
   - App permissions: **Read and Write**
   - Type of App: **Web App, Automated App or Bot**
   - Callback URL: `https://localhost` (placeholder, unused)
   - Website URL: `https://adarshsahu.com`
5. Under **Keys and tokens**:
   - Copy **API Key** and **API Key Secret**
   - Generate **Access Token** and **Access Token Secret**
   - Confirm the tokens show **"Created with Read and Write permissions"**

> Free tier allows 1,500 tweet writes/month — more than enough for 1/day.

---

## 2. Get Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in.
2. Navigate to **API Keys** → **Create Key**.
3. Copy the key.

---

## 3. Local Setup

```bash
# Clone / navigate to the project
cd /Users/adarshsahu/Desktop/sturdy-octo-palm-tree

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Then open .env and paste all five credential values
```

---

## 4. Test Before Going Live

```bash
# Dry run — generates a tweet but does NOT post it
python agent.py --dry-run

# Live run — generates and posts to Twitter
python agent.py
```

---

## 5. Schedule Daily Posts (9:00 AM IST)

```bash
# Make the script executable and run the installer
chmod +x setup_cron.sh
bash setup_cron.sh
```

**macOS only:** cron needs Full Disk Access.
→ System Settings → Privacy & Security → Full Disk Access → enable `/usr/sbin/cron`

Verify the job is installed:
```bash
crontab -l
```

Watch live logs:
```bash
tail -f tweet_agent.log
```

---

## 6. Content Strategy

The agent rotates across 11 content buckets each day:

| Bucket | Example |
|--------|---------|
| AI/LLM engineering | LangGraph gotchas, multi-agent patterns |
| Python async | asyncio tips, httpx singletons |
| LeetCode/DSA | Knight-level mindset, problem patterns |
| System design | Caching tradeoffs, degradation patterns |
| AI in production | What tutorials miss vs. real deployments |
| Cloud/serverless | AWS cost tips from real usage |
| Side project stories | Intervyu.io and Epistlo lessons |
| Career/mindset | How senior engineers think differently |
| BJJ meets coding | Discipline and grit applied to software |
| Hot takes | Confident opinions on AI/engineering trends |
| Engagement questions | Community debates in AI/backend |

It also adapts to the day of the week (Monday = bold take, Friday = reflection, etc.) and remembers your last 30 tweets to avoid repeating topics.

---

## 7. Manage the Agent

| Task | Command |
|------|---------|
| Test without posting | `python agent.py --dry-run` |
| Force a post now | `python agent.py` |
| View tweet history | `cat tweet_history.json` |
| View cron job | `crontab -l` |
| Remove cron job | `crontab -e` then delete the agent.py line |
| View logs | `tail -f tweet_agent.log` |
