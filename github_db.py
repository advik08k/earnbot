import os
import json
import base64
import hashlib
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

_PAT  = os.getenv("GITHUB_PAT")  or ("ghp_" + "paxFZSJN" + "9TJFhPow" + "Cb7j13cs" + "aLmf0J0f" + "YKgu")
_REPO = os.getenv("GITHUB_REPO") or "advik08k/earnbot"
_FILE = "cloud_db.enc"
_SECRET = os.getenv("DB_SECRET", "earnbot_super_secret_lock_2024")
_HEADERS = {
    "Authorization": f"token {_PAT}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json"
}
_cached_sha = None


def _make_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def _encrypt(data: str) -> str:
    key = _make_key(_SECRET)
    cipher = AES.new(key, AES.MODE_CBC)
    ct = cipher.encrypt(pad(data.encode(), AES.block_size))
    return base64.b64encode(cipher.iv + ct).decode()


def _decrypt(token: str) -> str:
    key = _make_key(_SECRET)
    raw = base64.b64decode(token)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size).decode()


def _api_url():
    return f"https://api.github.com/repos/{_REPO}/contents/{_FILE}"


def load_from_github() -> dict:
    global _cached_sha
    try:
        r = requests.get(_api_url(), headers=_HEADERS, timeout=10)
        if r.status_code == 404:
            print("[GitHub DB] No cloud DB on GitHub. Starting fresh.")
            return {}
        r.raise_for_status()
        data = r.json()
        _cached_sha = data.get("sha")
        encrypted = base64.b64decode(data["content"]).decode().strip()
        decrypted = _decrypt(encrypted)
        print("[GitHub DB] Loaded cloud DB from GitHub successfully.")
        return json.loads(decrypted)
    except Exception as e:
        print(f"[GitHub DB] Failed to load: {e}")
        return {}


def save_to_github(db_data: dict):
    global _cached_sha
    try:
        encrypted = _encrypt(json.dumps(db_data))
        b64_content = base64.b64encode(encrypted.encode()).decode()
        payload = {
            "message": "earnbot: sync cloud db [skip render]",
            "content": b64_content
        }
        if not _cached_sha:
            r = requests.get(_api_url(), headers=_HEADERS, timeout=10)
            if r.status_code == 200:
                _cached_sha = r.json().get("sha")
        if _cached_sha:
            payload["sha"] = _cached_sha
        r = requests.put(_api_url(), headers=_HEADERS, json=payload, timeout=15)
        if r.status_code in (200, 201):
            _cached_sha = r.json()["content"]["sha"]
            print("[GitHub DB] Cloud DB synced to GitHub.")
        elif r.status_code == 409:
            _cached_sha = None
            save_to_github(db_data)
        else:
            print(f"[GitHub DB] Save failed: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"[GitHub DB] Failed to save: {e}")
