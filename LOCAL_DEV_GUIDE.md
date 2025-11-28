# ==============================================
# LOCAL DEVELOPMENT WORKFLOW (Branch-Based)
# ==============================================

## Branch Strategy

```
master (production) ←── Only merged after testing
    │
    └── develop ←── All new work happens here
```

- **master** = Production (auto-deploys to Railway)
- **develop** = Development branch (safe to experiment)

---

## Quick Start

### 1. Switch to Development Branch
```cmd
git checkout develop
```

### 2. Run Locally (Test Your Changes)
Double-click `run_local.bat` or run in terminal:
```cmd
run_local.bat
```

This will:
- Create a virtual environment (if needed)
- Install dependencies
- Start the app at **http://localhost:5000**

### 3. Test Your Changes
- Open http://localhost:5000 in your browser
- Test all features you modified
- The local version uses:
  - **SQLite database** (not your production PostgreSQL)
  - **Billing disabled** (free access for testing)
  - **Debug mode enabled** (shows detailed errors)

### 4. Commit to Development Branch
```cmd
git add .
git commit -m "Your descriptive commit message"
git push origin develop
```

### 5. Merge to Production (When Ready)
Only after thorough testing:
```cmd
git checkout master
git merge develop
git push origin master
```

Railway will automatically detect the push and redeploy.

---

## Key Files

| File | Purpose |
|------|---------|
| `.env` | **LOCAL config** - Never committed, your local settings |
| `.env.example` | Template for environment variables |
| `run_local.bat` | **Windows script** to run locally |
| `start.sh` | **Production script** used by Railway/Render |
| `railway.json` | Railway deployment configuration |

---

## Environment Separation

### Local Development (`.env`)
```
FLASK_DEBUG=True
DATABASE_URL=          # Empty = uses local SQLite
STRIPE_SECRET_KEY=     # Empty = billing disabled
```

### Production (Railway Environment Variables)
Set these in Railway dashboard:
- `DATABASE_URL` - PostgreSQL connection string (auto-set by Railway)
- `FLASK_SECRET_KEY` - Strong random key
- `STRIPE_SECRET_KEY` - Your live Stripe key
- `STRIPE_PRICE_ID` - Your subscription price ID
- etc.

---

## Safe Workflow Summary

```
┌─────────────────────┐
│  git checkout       │
│  develop            │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Make Changes       │
│  in VS Code         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  run_local.bat      │
│  Test at            │
│  localhost:5000     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  git add .          │
│  git commit         │
│  git push develop   │
└──────────┬──────────┘
           │
           ▼ (when ready)
┌─────────────────────┐
│  git checkout       │
│  master             │
│  git merge develop  │
│  git push master    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Railway auto       │
│  deploys to         │
│  production         │
└─────────────────────┘
```

---

## Testing Tips

1. **Create a test user locally:**
   - Sign up at http://localhost:5000/signup
   - Subscription is automatically "active" (billing disabled)

2. **Use admin bypass:**
   - The local admin key is: `ctts_local_dev_admin_key`
   - You can use this for API testing

3. **View local database:**
   - SQLite file at: `webapp/users.db`
   - Use any SQLite browser to inspect

4. **Check for errors:**
   - Console shows detailed Flask debug output
   - Check the terminal for any Python errors
