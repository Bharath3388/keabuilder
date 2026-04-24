# Deployment Guide — Vercel (Frontend) + Railway (Backend)

## Architecture

```
┌───────────────────┐         ┌───────────────────────┐
│  Vercel            │  HTTPS  │  Railway               │
│  (Free Tier)       │────────▶│  (Free Tier / $5/mo)   │
│                    │         │                        │
│  Next.js Frontend  │         │  FastAPI Backend        │
│  SSR + Static      │         │  SQLite + ChromaDB      │
│  CDN Edge Network  │         │  AI Provider Calls      │
│                    │         │  File Storage            │
│  your-app.vercel   │         │  your-api.railway.app   │
│  .app              │         │                        │
└───────────────────┘         └───────────────────────┘
```

---

## Step 1: Deploy Backend to Railway

### 1a. Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub Repo"**
3. Select your `keabuilder` repository
4. Set the **Root Directory** to `backend`

### 1b. Set Environment Variables

In the Railway dashboard → **Variables** tab, add:

```
APP_ENV=production
APP_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
CORS_ORIGINS=https://your-app.vercel.app
API_KEYS=<generate a strong random key>
GROQ_API_KEY=<your groq key>
GEMINI_API_KEY=<your gemini key>
HF_API_TOKEN=<your huggingface token>
DATABASE_URL=sqlite:///./keabuilder.db
STORAGE_PROVIDER=local
```

### 1c. Verify Deployment

Railway will auto-detect the `Procfile` and deploy. Once running, check:

```
https://your-api.railway.app/api/v1/health
```

You should see `{"status": "healthy", ...}`.

### 1d. Optional: Add Redis

1. In your Railway project, click **"New"** → **"Database"** → **"Redis"**
2. Railway auto-injects `REDIS_URL` into your backend service
3. No configuration needed

---

## Step 2: Deploy Frontend to Vercel

### 2a. Create Vercel Project

1. Go to [vercel.com](https://vercel.com) and sign in with GitHub
2. Click **"Add New Project"** → Import your `keabuilder` repository
3. Set the **Root Directory** to `frontend`
4. Framework Preset will auto-detect **Next.js**

### 2b. Set Environment Variables

In Vercel dashboard → **Settings** → **Environment Variables**:

```
NEXT_PUBLIC_API_URL=https://your-api.railway.app
NEXT_PUBLIC_API_KEY=<same key you set in Railway API_KEYS>
```

### 2c. Deploy

Click **Deploy**. Vercel will:
1. Install dependencies (`npm install`)
2. Build the Next.js app (`npm run build`)
3. Deploy to the edge CDN

### 2d. Update Railway CORS

After getting your Vercel URL (e.g., `https://keabuilder.vercel.app`), go back to Railway and update:

```
CORS_ORIGINS=https://keabuilder.vercel.app
```

---

## Step 3: Verify End-to-End

1. Open your Vercel URL in a browser
2. The frontend should load and connect to the Railway backend
3. Test the health endpoint: your Vercel app should show the platform working
4. Test lead classification, image generation, etc.

---

## Custom Domain (Optional)

### Vercel
1. Dashboard → **Settings** → **Domains**
2. Add `app.yourdomain.com`
3. Add the DNS records Vercel provides

### Railway
1. Dashboard → **Settings** → **Networking** → **Custom Domain**
2. Add `api.yourdomain.com`
3. Add the CNAME record Railway provides
4. Update `CORS_ORIGINS` in Railway to include `https://app.yourdomain.com`
5. Update `NEXT_PUBLIC_API_URL` in Vercel to `https://api.yourdomain.com`

---

## Cost Summary

| Service | Free Tier | Paid |
|---------|-----------|------|
| **Vercel** | 100GB bandwidth, serverless functions | $20/mo Pro |
| **Railway** | $5 credit/month (covers ~500 hours) | $5/mo + usage |
| **Redis (Railway)** | Included in $5 credit | — |
| **Total** | **$0–$5/month** | — |

---

## Local Development

No changes needed for local dev. The defaults still work:

```bash
# Terminal 1 — Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

The frontend defaults to `http://localhost:8000` when `NEXT_PUBLIC_API_URL` is not set.

---

## Files Changed for Deployment

| File | Change |
|------|--------|
| `frontend/next.config.js` | Uses `NEXT_PUBLIC_API_URL` env var for backend URL |
| `frontend/src/lib/api.ts` | API_BASE reads from `NEXT_PUBLIC_API_URL` |
| `frontend/vercel.json` | Vercel build configuration |
| `frontend/.vercelignore` | Ignore list for Vercel |
| `frontend/.env.example` | Environment variable template |
| `backend/railway.toml` | Railway deployment configuration |
| `backend/Procfile` | Process definition for Railway |
| `backend/runtime.txt` | Python version for Railway |
| `backend/.railwayignore` | Ignore list for Railway |
| `backend/config.py` | Added `port` field (Railway injects `PORT`) |
| `backend/main.py` | Uses dynamic port |
| `backend/.env.example` | Updated with CORS and API key examples |
