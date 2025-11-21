# Cheap TTS Web App (with Auth + Stripe)

**Unlimited Text-to-Speech for just $4.99/month**

Modern web interface with 550+ human-like voices in 153 languages. Save hundreds of dollars compared to competitors!

## Why Cheap TTS?

- 💰 **Only $4.99/month** vs competitors charging $49-$99/month
- ♾️ **Unlimited usage** - no character, word, or time limits
- 🎭 **550+ natural voices** - human-like quality
- 🌍 **153 languages** - reach global audiences
- 🚀 **Commercial use** - use for any project

## Pricing Comparison

| Service | Monthly Cost | Usage Limit | Annual Cost |
|---------|-------------|-------------|-------------|
| **Cheap TTS** | **$4.99** | **Unlimited ∞** | **$59.88** |
| ElevenLabs | $99.00 | 100K chars | $1,188.00 |
| Play.ht | $79.00 | 500K words | $948.00 |
| Murf.ai | $49.00 | 48 hours | $588.00 |

**Save up to $1,140/year!**

## Quick Start

1) Install dependencies (inside your virtualenv):

```bash
pip install flask flask_sqlalchemy flask_login stripe edge-tts
```

2) Set environment variables (at minimum these for Stripe in production):

```bash
set FLASK_SECRET_KEY=replace-with-a-strong-secret
set STRIPE_SECRET_KEY=sk_live_or_test...
set STRIPE_PRICE_ID=price_xxx_for_4_99_plan
set STRIPE_WEBHOOK_SECRET=whsec_xxx  (optional locally, recommended)
```

3) Run the app from the `webapp` directory:

```bash
D:/edge-tts-master/.venv/Scripts/python.exe app.py
```

Open http://localhost:5000

4) For local webhook testing (optional but recommended), use the Stripe CLI:

```bash
stripe login
stripe listen --forward-to localhost:5000/stripe/webhook
```

## Features

- 🔐 **Accounts**: Sign up, sign in, logout
- 💳 **Billing**: $4.99/month subscription via Stripe Checkout + Billing Portal
- 🎤 **550+ Voices**: Natural human-like voices across 153 languages
- 🎚️ **Controls**: Adjust speed, volume, and pitch
- 🎵 **Output**: Stream MP3 in browser and download
- ♾️ **Unlimited**: No character limits, no word counts, no time restrictions

## What You Get

Unlike competitors that charge hundreds of dollars and impose strict limits:

- ✅ Generate unlimited audio
- ✅ No character or word restrictions
- ✅ All 550+ voices included
- ✅ Commercial use allowed
- ✅ Download MP3 files
- ✅ Adjust all voice parameters
- ✅ Cancel anytime

## Technical Details

- Set `STRIPE_PRICE_ID` to your Stripe Price for $4.99/month
- After successful checkout, the app marks your subscription active
- Webhook events keep subscription status in sync
- Manage or cancel via "Manage Billing" button

Enjoy affordable, unlimited text-to-speech! 🎉

