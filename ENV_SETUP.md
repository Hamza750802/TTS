# Cheap TTS - Environment Variables Setup Guide

## Required Environment Variables

This application requires the following environment variables to be configured:

### 1. Flask Secret Key
**Variable:** `FLASK_SECRET_KEY`  
**Description:** A secret key used by Flask for session management and security.  
**How to generate:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
**Example:** `a7f3b9c2d8e1f4a6b9c2d5e8f1a4b7c0d3e6f9a2b5c8d1e4f7a0b3c6d9e2f5a8`

### 2. Stripe Secret Key
**Variable:** `STRIPE_SECRET_KEY`  
**Description:** Your Stripe API secret key for processing payments.  
**Where to find:** [Stripe Dashboard → Developers → API Keys](https://dashboard.stripe.com/apikeys)  
**Format:**
- Test mode: `sk_test_...`
- Live mode: `sk_live_...`

### 3. Stripe Price ID
**Variable:** `STRIPE_PRICE_ID`  
**Description:** The Stripe Price ID for your monthly subscription product.  
**Where to find:** [Stripe Dashboard → Products → Your Product → Pricing](https://dashboard.stripe.com/products)  
**Format:** `price_...`

**How to create:**
1. Go to [Stripe Dashboard → Products](https://dashboard.stripe.com/products)
2. Click "Add product"
3. Name: "Cheap TTS Monthly Subscription"
4. Description: "Unlimited text-to-speech generation"
5. Pricing: Recurring, $4.99/month
6. Click "Save product"
7. Copy the Price ID (starts with `price_`)

### 4. Stripe Webhook Secret
**Variable:** `STRIPE_WEBHOOK_SECRET`  
**Description:** The signing secret for verifying Stripe webhook events.  
**Where to find:** [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks)  
**Format:** `whsec_...`

**How to create:**
1. Go to [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks)
2. Click "Add endpoint"
3. Endpoint URL: `https://yourdomain.com/stripe/webhook` (or for testing: use ngrok or similar)
4. Select events to listen to:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Click "Add endpoint"
6. Copy the "Signing secret" (starts with `whsec_`)

### 5. Admin API Key (Optional - For Personal Use)
**Variable:** `ADMIN_API_KEY`  
**Description:** A special API key that gives YOU unlimited FREE access to the TTS API for your personal projects.  
**Format:** `ctts_...`

**How to generate:**
```bash
python -c "import secrets; print('ctts_' + secrets.token_urlsafe(32))"
```

**Why you need this:**
- Use the TTS API in your own projects without paying
- Bypass subscription checks
- Unlimited usage for personal use
- Keep this key SECRET - it's only for you!
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Click "Add endpoint"
6. Copy the "Signing secret" (starts with `whsec_`)

## Setup Instructions

### Step 1: Copy the example file
```bash
cp .env.example .env
```

### Step 2: Edit the .env file
Open `.env` in your text editor and fill in all the values:

```env
FLASK_SECRET_KEY=your-generated-secret-key-here
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_PRICE_ID=price_your_price_id_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
```

### Step 3: Verify the setup
The `.env` file is automatically loaded when you run the application. Make sure:
- The `.env` file is in the `edge-tts-master` directory (same level as `webapp/`)
- The `.env` file is **NOT** committed to git (it's already in `.gitignore`)

## Security Notes

⚠️ **IMPORTANT:**
- Never commit the `.env` file to version control
- Never share your secret keys publicly
- Use test mode keys for development
- Switch to live mode keys only in production
- Rotate your keys if they are ever exposed

## Testing Stripe Integration

### Using Stripe Test Mode
For development, use Stripe's test mode:
- Test card: `4242 4242 4242 4242`
- Any future expiry date (e.g., 12/34)
- Any 3-digit CVC
- Any ZIP code

### Webhook Testing
For local development, use the Stripe CLI or ngrok:

**Option 1: Stripe CLI**
```bash
stripe listen --forward-to localhost:5000/stripe/webhook
```

**Option 2: ngrok**
```bash
ngrok http 5000
# Then add the ngrok URL to Stripe webhooks: https://your-ngrok-url.ngrok.io/stripe/webhook
```

## Troubleshooting

### Application won't start
- Check that all environment variables are set in `.env`
- Verify the `.env` file is in the correct location
- Make sure `python-dotenv` is installed: `pip install python-dotenv`

### Stripe errors
- Verify your API keys are correct (test vs live mode)
- Check that the Price ID exists in your Stripe dashboard
- Ensure webhook secret matches your endpoint

### Webhook not receiving events
- Verify the webhook endpoint is publicly accessible
- Check the Stripe webhook logs in the dashboard
- Ensure the webhook secret is correct
