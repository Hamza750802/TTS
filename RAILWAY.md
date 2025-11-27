# Deploying Cheap TTS to Railway

Railway is perfect for Flask apps and works seamlessly with private repositories!

## Why Railway?

✅ Works with private GitHub repos out of the box  
✅ Free $5/month credit (enough for hobby projects)  
✅ Automatic HTTPS  
✅ Easy environment variables  
✅ One-click deploy  
✅ Persistent storage available  

## Deployment Steps

### 1. Create Railway Account

1. Go to [Railway.app](https://railway.app)
2. Click **"Login"** and sign in with GitHub
3. Railway will automatically have access to your repos

### 2. Deploy Your App

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your **`TTS`** repository (private repos are shown!)
4. Railway will auto-detect Python and start building

### 3. Configure Environment Variables

After deployment starts, click on your service and go to **"Variables"** tab:

Add these environment variables:

```
FLASK_SECRET_KEY=<click "Generate" or paste a random string>
DEBUG_MODE=false
STRIPE_SECRET_KEY=sk_live_... (or sk_test_...)
STRIPE_PRICE_ID=price_xxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx (add after setting up webhook)
ADMIN_API_KEY=ctts_your_admin_key_here
```

### 4. Set Up Custom Domain (Optional)

1. Go to **"Settings"** tab
2. Click **"Generate Domain"** for a free Railway subdomain
3. Or add your own custom domain

Your app will be at: `https://your-app.up.railway.app`

### 5. Configure Stripe Webhook

1. Go to [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks)
2. Click **"Add endpoint"**
3. Enter your Railway URL:
   ```
   https://your-app.up.railway.app/stripe/webhook
   ```
4. Select these events:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Copy the **Signing secret** (starts with `whsec_`)
6. Add it to Railway as `STRIPE_WEBHOOK_SECRET`
7. Railway will auto-redeploy with the new variable

### 6. Verify Deployment

1. Visit your Railway URL
2. Test the voice preview
3. Sign up and test subscription flow
4. Check Railway logs for any errors

## Railway Features

### Automatic Deploys
- Every `git push` automatically redeploys
- View deployment logs in real-time
- Easy rollbacks to previous versions

### Monitoring
- **Metrics**: CPU, Memory, Network usage
- **Logs**: Real-time application logs
- **Deployments**: History of all deployments

### Database (Upgrade Option)
SQLite works fine for starting, but for production:
1. Click **"New"** → **"Database"** → **"PostgreSQL"**
2. Railway provides connection URL automatically
3. Update `app.py` to use PostgreSQL instead of SQLite

### Pricing

**Hobby Plan** (Free):
- $5 free credit per month
- ~100 hours of uptime
- Perfect for testing/personal use

**Pro Plan** ($20/month):
- $20 credit included
- Pay only for what you use
- ~500 hours for typical Flask app

## Important Notes

### File Storage
- Generated MP3s are stored in `webapp/output/`
- Files persist between deploys (unlike Render free tier!)
- Auto-cleanup runs on startup (7-day retention)

### Database
- SQLite persists on Railway (stored in volume)
- For production, upgrade to PostgreSQL
- Database survives redeploys ✅

### Environment Variables
- Automatically injected at runtime
- Changes trigger auto-redeploy
- Encrypted and secure

## Troubleshooting

### Build Failed
- Check **"Deployments"** → **"Build Logs"**
- Verify `requirements.txt` is correct
- Python version: 3.11+ (Railway auto-detects)

### App Crashed
- Check **"Deployments"** → **"Deploy Logs"**
- Verify all environment variables are set
- Check for port binding issues (Railway sets `$PORT` automatically)

### Database Issues
- SQLite file: `webapp/users.db`
- Check file permissions
- Consider upgrading to PostgreSQL for production

### Stripe Webhook Not Working
- Verify webhook URL matches your Railway domain
- Check webhook signing secret is correct
- View webhook events in Stripe dashboard
- Check Railway logs for incoming webhook requests

## Upgrading to Production

For serious production use:

1. **Add PostgreSQL Database**:
   ```bash
   # In Railway dashboard: New → Database → PostgreSQL
   # Update app.py to use DATABASE_URL
   ```

2. **Enable Volume for Persistent Storage**:
   - Mount volume at `/app/webapp/output`
   - Prevents MP3 cleanup on redeploy

3. **Custom Domain**:
   - Add your domain in Railway settings
   - Update DNS records
   - Railway handles SSL automatically

4. **Monitoring**:
   - Railway Pro includes better metrics
   - Add external monitoring (BetterStack, etc.)

5. **Scaling**:
   - Railway auto-scales based on usage
   - Adjust resource limits in settings

## Railway vs Render

| Feature | Railway | Render Free |
|---------|---------|-------------|
| Private Repos | ✅ Easy | ✅ Requires permission |
| Free Tier | $5 credit/month | 750 hrs/month |
| Persistent Storage | ✅ Yes | ❌ No |
| Auto-sleep | ❌ No | ✅ After 15 min |
| Database Persistence | ✅ Yes | ❌ Resets on restart |
| Setup Complexity | ⭐⭐⭐⭐⭐ Easy | ⭐⭐⭐⭐ Easy |

## Support

- [Railway Documentation](https://docs.railway.app)
- [Railway Discord](https://discord.gg/railway)
- [Railway Help Center](https://help.railway.app)

## Quick Commands

View logs:
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link

# View logs
railway logs

# Open in browser
railway open
```

That's it! Your app should be live in ~2-3 minutes. 🚀
