# PRIME PHYSICS — Setup & Hosting Guide

---

## What Was Fixed

### Backend (`App.py`)
1. **PDF not found** — Added `PDF_FOLDER` env variable so Flask can find your existing PDFs on disk (`E:\Claude code\PDF`). It searches `uploads/` first, then `PDF_FOLDER`.
2. **Wrong MIME type** — `send_from_directory` now passes `mimetype="application/pdf"` and `download_name=safe` so the browser always recognises it as a PDF.
3. **View vs Download** — Added `?download=1` query param. Without it, the PDF opens inline in a new tab. With it, the browser shows the Save dialog.
4. **Filename sanitisation** — The old regex stripped spaces and parentheses, breaking filenames like `55(B) Physics (For Blind Candidates).pdf`. Fixed to allow spaces `( )`.
5. **CORS headers** — Added `expose_headers` for `Content-Disposition` so the browser can read the attachment header and `Content-Length` for progress bars.

### Frontend (`prime_physics_dashboard.html`)
1. **Download errors** — `dlFile()` now reads the JSON error body from the server and shows the real error message instead of a generic one.
2. **Two buttons per card** — Each PDF card now has an 👁 **View** button (opens in new tab) and a ⬇ **Download** button (saves to disk).
3. **Filename quoting** — Apostrophes in filenames are escaped to prevent JS injection in `onclick`.

---

## Running Locally (Windows)

### Step 1 — Set up the environment

```cmd
cd "E:\Claude code"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Point Flask at your PDF folder

**Option A — Set env variable before running (recommended)**
```cmd
set PDF_FOLDER=E:\Claude code\PDF
python App.py
```

**Option B — Create a `.env` file** (needs `python-dotenv` added to requirements):
```
PDF_FOLDER=E:\Claude code\PDF
SECRET_KEY=change-me-in-production
JWT_SECRET=change-me-in-production
```

### Step 3 — Open the dashboard

1. Open `prime_physics_dashboard.html` directly in your browser — **or** serve it via Flask.
2. The API talks to `http://localhost:5000/api` (already set in the HTML).
3. Log in with the seeded mentor: `mentor_jairam` / `Mentor@Prime2025`

---

## Do PDFs Work When Hosted?

**Short answer: PDFs work IF you upload them to the server too.**

When you deploy to a cloud host (Render, Railway, Vercel + Railway, etc.):

| Scenario | Does it work? |
|---|---|
| Running locally + `PDF_FOLDER` set | ✅ Yes — Flask reads straight from your disk |
| Deployed to cloud + PDFs uploaded via the app | ✅ Yes — stored in `uploads/` on server |
| Deployed to cloud, PDFs NOT uploaded | ❌ No — the server has no access to your local disk |

### What to do for hosting

**Option 1 — Upload PDFs through the app (easiest)**
1. Log in as mentor
2. Go to "Upload PDF" in the sidebar
3. Upload each PDF via the form — they're saved to `uploads/` on the server

**Option 2 — Use cloud storage (best for many files)**
Store your PDFs on **Cloudflare R2** (free tier), **AWS S3**, or **Backblaze B2**, then change the download route in `App.py` to redirect to a signed URL. Contact me if you want that code.

---

## Deployment on Render (Free Tier)

1. Push your project to GitHub (include `App.py`, `requirements.txt`, and the HTML file).
2. Go to [render.com](https://render.com) → New → Web Service → connect your repo.
3. Set:
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `python App.py`
4. Add environment variables in Render dashboard:
   - `SECRET_KEY` = (a long random string)
   - `JWT_SECRET` = (another long random string)
   - `PDF_FOLDER` = leave blank (Render can't access your local disk — upload PDFs via the app instead)
5. In the HTML, change line 856:
   ```js
   const API_BASE = 'https://YOUR-RENDER-APP-NAME.onrender.com/api';
   ```

> ⚠️ Render's free tier spins down after 15 min of inactivity. Use the paid tier or Railway for always-on.

---

## File Structure

```
E:\Claude code\
├── App.py                  ← Flask backend (fixed)
├── requirements.txt
├── prime_physics_dashboard.html   ← Frontend (fixed)
├── uploads/                ← Mentor-uploaded PDFs go here
└── PDF/                    ← Your existing PDFs (pointed to by PDF_FOLDER)
    ├── 55-1-1 Physics.pdf
    ├── 55(B) Physics (For Blind Candidates).pdf
    └── ...
```

---

## Quick Test Checklist

After starting the server:

- [ ] `GET http://localhost:5000/api/health` returns `{"success": true}`
- [ ] Login with mentor credentials works
- [ ] CBSE/NEET/JEE tabs show PDF cards
- [ ] Clicking 👁 View opens PDF in a new tab
- [ ] Clicking ⬇ Download saves PDF to disk
- [ ] Upload new PDF as mentor → appears in the grid
