# Portal

Google OAuth 2.0 protected portal.

## Quick start

### 1. Create a Google OAuth 2.0 client

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. Click **Create Credentials** → **OAuth client ID**.
3. Application type: **Web application**.
4. Add an **Authorised redirect URI**:  
   `http://localhost:8080/auth/callback`
5. Copy the **Client ID** and **Client Secret**.

### 2. Configure environment

```bash
cp mise.local.example mise.local.toml
# Edit and set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SECRET_KEY
```

Generate a strong SECRET_KEY if you don't have one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Run the app

```bash
run
```
