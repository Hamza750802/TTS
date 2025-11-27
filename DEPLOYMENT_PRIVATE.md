# Deploying Private Repository to Render

Since your repository is private, follow these steps:

## Method 1: Grant Render Access (Easiest)

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Click **"Connect GitHub"** or **"Configure GitHub App"**
4. In the GitHub permissions page:
   - Select **"Only select repositories"**
   - Choose your `TTS` repository from the dropdown
   - Click **"Save"**
5. Return to Render and select your `TTS` repository
6. Continue with normal deployment configuration

**Note**: Render only gets READ access to deploy your code. This is safe and standard practice.

## Method 2: Manual Deploy (No GitHub Connection)

If you prefer not to connect GitHub at all:

1. Clone your repo locally (you already have this)
2. Install Render CLI:
   ```bash
   npm install -g render
   ```
3. Login to Render:
   ```bash
   render login
   ```
4. Deploy directly:
   ```bash
   render deploy
   ```

## Method 3: Deploy via Docker (Advanced)

1. Create a `Dockerfile` in your project root
2. Use Render's Docker deployment option
3. This doesn't require GitHub access at all

## Recommended: Method 1

Method 1 is the easiest and most reliable. Render's GitHub integration:
- ✅ Only gets READ access (cannot modify your code)
- ✅ Automatic deployments on git push
- ✅ Easy rollbacks
- ✅ Build logs and previews
- ✅ Follows industry standard security practices

Thousands of companies use this - it's completely safe!

## Still Prefer Privacy?

Alternative hosting platforms that work well with private repos:
- **Railway** - Similar to Render, easy private repo support
- **Fly.io** - Deploy via CLI (no GitHub needed)
- **Heroku** - Classic platform, supports private repos
- **DigitalOcean App Platform** - Docker-based deployment

All of these support the same Flask + gunicorn setup we've configured.
