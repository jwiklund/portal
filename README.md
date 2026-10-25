# Portal

Google OAuth 2.0 protected portal.

## Quick start

### 1. Create a Google OAuth 2.0 client

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. Click **Create Credentials** → **OAuth client ID**.
3. Application type: **Web application**.
4. Add an **Authorised redirect URI**:  
   `http://127.0.0.1:8080/auth/callback`
5. Copy the **Client ID** and **Client Secret**.

### 2. Create a Spotify Application

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in.
2. Click **Create app**, give it a name (e.g. "Portal"), and accept the terms.
3. Open the app's **Settings** → **Redirect URIs** and add exactly:  
   `http://127.0.0.1:8080/spotify/callback`
4. Copy the **Client ID** and **Client Secret** into `mise.local.toml` as `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`.
5. Set `BASE_URL="http://127.0.0.1:8080"` in `mise.local.toml`.
6. While the app is in **Development mode**, add your Spotify account under **User Management** (the allowlist), otherwise playlist creation will fail.

> **Important:** the redirect URIs in the provider dashboards and the ones the app builds from `BASE_URL` must match exactly, including the host. Use `127.0.0.1`, **not** `localhost`, in both places:
>
> - Google dashboard: `http://127.0.0.1:8080/auth/callback`
> - Spotify dashboard: `http://127.0.0.1:8080/spotify/callback`
> - `mise.local.toml`: `BASE_URL="http://127.0.0.1:8080"`

### 3. Configure environment

```bash
cp mise.local.example mise.local.toml
# Edit and set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SECRET_KEY,
# SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and BASE_URL
```

Generate a strong SECRET_KEY if you don't have one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Run the app

```bash
run
```
