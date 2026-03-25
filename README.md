# BlackSheep + Google OAuth Example

A minimal Python web app using **BlackSheep** with **Google OAuth 2.0** authentication.  
All routes are protected except `/login` and `/auth/callback`.

## Project layout

```
blacksheep-oauth/
├── app.py               # Main application
├── requirements.txt
├── .env.example         # Copy to .env and fill in secrets
└── templates/
    ├── base.html
    ├── login.html
    ├── index.html
    ├── profile.html
    └── error.html
```

## Quick start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a Google OAuth 2.0 client

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. Click **Create Credentials** → **OAuth client ID**.
3. Application type: **Web application**.
4. Add an **Authorised redirect URI**:  
   `http://localhost:8000/auth/callback`
5. Copy the **Client ID** and **Client Secret**.

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SECRET_KEY
```

Generate a strong SECRET_KEY if you don't have one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Run the app

```bash
python app.py
# or
uvicorn app:app --reload
```

Open [http://localhost:8000](http://localhost:8000) — you'll be redirected to `/login`.

---

## How auth works

| Path | Protected? | Notes |
|---|---|---|
| `GET /` | ✅ Yes | Home page |
| `GET /profile` | ✅ Yes | User profile |
| `GET /login` | ❌ No | Login page (public) |
| `GET /auth/google` | ❌ No | Starts OAuth flow |
| `GET /auth/callback` | ❌ No | Google redirect URI |
| `GET /logout` | – | Clears session |

The `@login_required` decorator checks `request.session["user"]`.  
If no user is in the session, it issues a `302` redirect to `/login`.

The OAuth flow:
1. `/auth/google` → redirect to Google with `state` token
2. Google → redirect back to `/auth/callback?code=…&state=…`
3. Server exchanges `code` for tokens, fetches userinfo, stores in session
4. Redirect to `/`
