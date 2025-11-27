# Deploying Cheap TTS to Render

This guide walks you through deploying Cheap TTS to Render's free tier.

## Prerequisites

- A [Render](https://render.com) account (free)
- A [Stripe](https://stripe.com) account with API keys
- This repository pushed to GitHub

## Deployment Steps

### 1. Create a New Web Service

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository: `Hamza750802/TTS`
4. Configure the service:
   - **Name**: `cheap-tts` (or your preferred name)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `bash start.sh`
   - **Plan**: Free

### 2. Configure Environment Variables

Add the following environment variables in the Render dashboard:

#### Required Variables

- **FLASK_SECRET_KEY**: A random secret key (click "Generate" in Render)
  ```
  Generate a secure random string
  ```

- **DEBUG_MODE**: Set to `false` for production
  ```
  false
  ```

#### Stripe Configuration

- **STRIPE_SECRET_KEY**: Your Stripe secret key
  ```
  sk_live_... (or sk_test_... for testing)
  ```

- **STRIPE_PRICE_ID**: Your Stripe subscription price ID
  ```
  price_xxxxxxxxxxxxx
  ```

- **STRIPE_WEBHOOK_SECRET**: Your Stripe webhook secret (configure after deployment)
  ```
  whsec_xxxxxxxxxxxxx
  ```

#### Admin API Key (Optional)

- **ADMIN_API_KEY**: Your personal admin API key for free access
  ```
  ctts_your_admin_key_here
  ```

### 3. Deploy

1. Click **"Create Web Service"**
2. Render will automatically build and deploy your app
3. Wait for the build to complete (~2-5 minutes)
4. Your app will be available at: `https://cheap-tts.onrender.com` (or your chosen name)

### 4. Configure Stripe Webhook

After deployment, set up the Stripe webhook to sync subscriptions:

1. Go to [Stripe Dashboard](https://dashboard.stripe.com/webhooks)
2. Click **"Add endpoint"**
3. Enter your webhook URL:
   ```
   https://your-app-name.onrender.com/stripe/webhook
   ```
4. Select events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Click **"Add endpoint"**
6. Copy the **Signing secret** (starts with `whsec_`)
7. Add it to your Render environment variables as `STRIPE_WEBHOOK_SECRET`
8. Restart your Render service to apply the change

### 5. Verify Deployment

1. Visit your deployed app: `https://your-app-name.onrender.com`
2. Test the public voice preview feature
3. Sign up for an account
4. Test the subscription flow (use Stripe test mode if testing)
5. Verify the webhook is working in Stripe dashboard

## Important Notes

### Free Tier Limitations

- **Spin down after 15 minutes of inactivity**: First request after inactivity will take ~30 seconds
- **750 hours/month**: More than enough for a personal project
- **Built-in SSL**: Automatic HTTPS

### Database

- Uses SQLite (stored in the container)
- **Warning**: On Render's free tier, the database will reset when the service restarts
- For production, upgrade to a paid plan or use an external database (PostgreSQL on Render)

### File Storage

- Generated MP3 files are stored in `webapp/output/`
- **Warning**: Files are ephemeral on Render's free tier (lost on restart)
- The app includes automatic cleanup (deletes files older than 7 days)
- For production, consider using cloud storage (S3, Cloudflare R2, etc.)

### Monitoring

- View logs in Render dashboard: **"Logs"** tab
- Monitor performance: **"Metrics"** tab
- Check deployment status: **"Events"** tab

## Troubleshooting

### Build Failed

- Check the build logs in Render dashboard
- Ensure `requirements.txt` is present in the repository
- Verify Python version compatibility

### App Won't Start

- Check the logs for errors
- Verify all required environment variables are set
- Ensure `start.sh` has correct permissions

### Database Errors

- The database is created automatically on first run
- If you see "table not found" errors, restart the service

### Stripe Webhook Not Working

- Verify the webhook URL is correct
- Check the webhook signing secret is set correctly
- Test using Stripe's webhook testing tool
- Check Render logs for webhook errors

## Upgrading to Production

For a production deployment, consider:

1. **Paid Render Plan** ($7/month):
   - Persistent storage
   - No spin-down
   - Better performance

2. **External Database**:
   - Render PostgreSQL database
   - Prevents data loss on restarts

3. **Cloud Storage**:
   - AWS S3 or Cloudflare R2
   - Persistent audio file storage

4. **Custom Domain**:
   - Configure custom domain in Render
   - Update Stripe webhook URL

5. **Monitoring**:
   - Enable Render's alerts
   - Set up uptime monitoring (UptimeRobot, etc.)

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_SECRET_KEY` | Yes | Flask session encryption key |
| `DEBUG_MODE` | No | Set to `false` for production (default: `false`) |
| `STRIPE_SECRET_KEY` | Yes | Stripe API secret key |
| `STRIPE_PRICE_ID` | Yes | Stripe subscription price ID |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret |
| `ADMIN_API_KEY` | No | Admin API key for free personal access |

## Support

If you encounter issues:
- Check Render's [documentation](https://render.com/docs)
- Review the logs in Render dashboard
- Check Stripe's webhook logs
- Verify all environment variables are set correctly
