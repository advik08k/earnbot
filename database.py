import sqlite3
import os
import time
import threading
import github_db

DB_PATH = os.path.join(os.path.dirname(__file__), 'agency.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Campaigns / Target Profiles Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            target_handle TEXT,
            mode TEXT,
            offer_title TEXT,
            price TEXT,
            advance_amount TEXT,
            upi_id TEXT,
            custom_pitch TEXT,
            daily_limit INTEGER DEFAULT 20,
            dms_sent_today INTEGER DEFAULT 0,
            last_reset_date TEXT,
            is_active INTEGER DEFAULT 1,
            created_at REAL
        )
    ''')
    
    # Leads table
    c.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            thread_id TEXT PRIMARY KEY,
            user_id TEXT,
            username TEXT,
            full_name TEXT,
            campaign_id TEXT,
            mode TEXT DEFAULT 'WEBSITE_DEV',
            stage TEXT DEFAULT 'NEW',
            niche TEXT,
            goals TEXT,
            is_outbound INTEGER DEFAULT 0,
            created_at REAL,
            updated_at REAL
        )
    ''')
    
    # Messages table
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            sender TEXT,
            text TEXT,
            timestamp REAL
        )
    ''')

    # Contacted Prospects Table (to prevent re-messaging same user)
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacted_prospects (
            username TEXT PRIMARY KEY,
            user_id TEXT,
            campaign_id TEXT,
            contacted_at REAL
        )
    ''')

    # Content Studio: Downloaded media & upload queue
    c.execute('''
        CREATE TABLE IF NOT EXISTS content_items (
            id TEXT PRIMARY KEY,
            source_type TEXT,
            source_query TEXT,
            source_username TEXT,
            source_media_pk TEXT,
            media_type TEXT,
            local_path TEXT,
            thumbnail_path TEXT,
            original_caption TEXT,
            ai_caption TEXT,
            upload_status TEXT DEFAULT 'queued',
            post_type TEXT DEFAULT 'feed',
            scheduled_at REAL,
            uploaded_at REAL,
            created_at REAL
        )
    ''')
    
    # Defaults
    defaults = {
        'session_id': os.getenv('INSTA_SESSION_ID', ''),
        'upi_id': os.getenv('UPI_ID', 'confusedaryan@fam'),
        'gemini_api_key': os.getenv('GEMINI_API_KEY', ''),
        'global_bot_active': '1'
    }
    
    for key, val in defaults.items():
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
        
    conn.commit()
    conn.close()

    # Load cloud DB from GitHub and override local defaults
    cloud = github_db.load_from_github()
    if cloud:
        if 'settings' in cloud:
            update_settings(cloud['settings'])
        if 'campaigns' in cloud:
            _restore_campaigns(cloud['campaigns'])
        if 'leads' in cloud:
            _restore_data('leads', cloud['leads'])
        if 'messages' in cloud:
            _restore_data('messages', cloud['messages'])
        if 'content_items' in cloud:
            _restore_data('content_items', cloud['content_items'])


# --- Settings Helpers ---
def get_settings():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT key, value FROM settings')
    rows = c.fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}

def update_settings(data: dict):
    conn = get_connection()
    c = conn.cursor()
    for key, value in data.items():
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()
    # Sync to GitHub in background so it doesn't block the request
    threading.Thread(target=_sync_to_github, daemon=True).start()


def _sync_to_github():
    """Collect all data and push to GitHub."""
    try:
        settings = get_settings()
        campaigns = get_campaigns()
        
        # Backup leads and messages too
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM leads')
        leads = [dict(r) for r in c.fetchall()]
        
        c.execute('SELECT * FROM messages')
        messages = [dict(r) for r in c.fetchall()]
        
        c.execute('SELECT * FROM content_items')
        content_items = [dict(r) for r in c.fetchall()]
        conn.close()
        
        github_db.save_to_github({
            'settings': settings, 
            'campaigns': campaigns,
            'leads': leads,
            'messages': messages,
            'content_items': content_items
        })
    except Exception as e:
        print(f"[GitHub DB Sync Error] {e}")



def _restore_data(table, data_list):
    if not data_list: return
    conn = get_connection()
    c = conn.cursor()
    # Get columns dynamically
    columns = data_list[0].keys()
    cols_str = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    
    for row in data_list:
        values = tuple(row[col] for col in columns)
        try:
            c.execute(f"INSERT OR IGNORE INTO {table} ({cols_str}) VALUES ({placeholders})", values)
        except Exception as e:
            print(f"[Restore Error {table}] {e}")
    conn.commit()
    conn.close()

def _restore_campaigns(campaigns: list):
    """Restore campaigns from GitHub cloud DB into local SQLite."""
    if not campaigns:
        return
    conn = get_connection()
    c = conn.cursor()
    for camp in campaigns:
        c.execute('''
            INSERT OR REPLACE INTO campaigns
            (id, target_handle, mode, offer_title, price, advance_amount, upi_id, custom_pitch, daily_limit, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            camp.get('id'), camp.get('target_handle'), camp.get('mode'),
            camp.get('offer_title'), camp.get('price'), camp.get('advance_amount'),
            camp.get('upi_id'), camp.get('custom_pitch'), camp.get('daily_limit', 20),
            camp.get('is_active', 1), camp.get('created_at', time.time())
        ))
    conn.commit()
    conn.close()
    print(f"[GitHub DB] Restored {len(campaigns)} campaigns from cloud.")


# --- Campaigns Helpers ---
def create_campaign(data: dict):
    conn = get_connection()
    c = conn.cursor()
    camp_id = f"camp_{int(time.time()*1000)}"
    c.execute('''
        INSERT INTO campaigns (id, target_handle, mode, offer_title, price, advance_amount, upi_id, custom_pitch, daily_limit, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        camp_id,
        data.get('target_handle', '').replace('@', '').strip(),
        data.get('mode', 'WEBSITE_DEV'),
        data.get('offer_title', 'E-commerce Website Setup'),
        data.get('price', '₹1,999'),
        data.get('advance_amount', '₹499'),
        data.get('upi_id', 'confusedaryan@fam'),
        data.get('custom_pitch', ''),
        int(data.get('daily_limit', 20)),
        1,
        time.time()
    ))
    conn.commit()
    conn.close()
    return camp_id

def get_campaigns():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM campaigns ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_campaign(campaign_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_campaign(campaign_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM campaigns WHERE id = ?', (campaign_id,))
    conn.commit()
    conn.close()

def toggle_campaign(campaign_id: str, is_active: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE campaigns SET is_active = ? WHERE id = ?', (is_active, campaign_id))
    conn.commit()
    conn.close()

# --- Prospects & Contact History ---
def is_prospect_contacted(username: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM contacted_prospects WHERE username = ?', (username.lower(),))
    res = c.fetchone()
    conn.close()
    return bool(res)

def mark_prospect_contacted(username: str, user_id: str, campaign_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO contacted_prospects (username, user_id, campaign_id, contacted_at)
        VALUES (?, ?, ?, ?)
    ''', (username.lower(), str(user_id), campaign_id, time.time()))
    
    # Increment campaign counter
    c.execute('UPDATE campaigns SET dms_sent_today = dms_sent_today + 1 WHERE id = ?', (campaign_id,))
    conn.commit()
    conn.close()

# --- Leads Helpers ---
def get_or_create_lead(thread_id, user_id='', username='', full_name='', campaign_id=None, mode='WEBSITE_DEV', is_outbound=0):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM leads WHERE thread_id = ?', (str(thread_id),))
    row = c.fetchone()
    now = time.time()
    
    if not row:
        c.execute('''
            INSERT INTO leads (thread_id, user_id, username, full_name, campaign_id, mode, stage, is_outbound, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'NEW', ?, ?, ?)
        ''', (str(thread_id), str(user_id), username, full_name, campaign_id, mode, is_outbound, now, now))
        conn.commit()
        c.execute('SELECT * FROM leads WHERE thread_id = ?', (str(thread_id),))
        row = c.fetchone()
    else:
        if username and not row['username']:
            c.execute('UPDATE leads SET username = ?, full_name = ? WHERE thread_id = ?', (username, full_name, str(thread_id)))
            conn.commit()
            
    conn.close()
    return dict(row)

def update_lead(thread_id, stage=None, niche=None, goals=None):
    conn = get_connection()
    c = conn.cursor()
    updates = ['updated_at = ?']
    params = [time.time()]
    
    if stage is not None:
        updates.append('stage = ?')
        params.append(stage)
    if niche is not None:
        updates.append('niche = ?')
        params.append(niche)
    if goals is not None:
        updates.append('goals = ?')
        params.append(goals)
        
    params.append(str(thread_id))
    query = f"UPDATE leads SET {', '.join(updates)} WHERE thread_id = ?"
    c.execute(query, params)
    conn.commit()
    conn.close()

def save_message(thread_id, sender, text):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (thread_id, sender, text, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (str(thread_id), sender, text, time.time()))
    conn.commit()
    conn.close()

def get_thread_messages(thread_id, limit=12):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM messages WHERE thread_id = ? ORDER BY id DESC LIMIT ?
    ''', (str(thread_id), limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def get_all_leads():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM leads ORDER BY updated_at DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Content Studio Helpers ---
def create_content_item(data: dict):
    conn = get_connection()
    c = conn.cursor()
    item_id = f"cnt_{int(time.time()*1000)}_{data.get('source_media_pk', '')[:8]}"
    c.execute('''
        INSERT OR IGNORE INTO content_items
        (id, source_type, source_query, source_username, source_media_pk,
         media_type, local_path, thumbnail_path, original_caption, ai_caption,
         upload_status, post_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
    ''', (
        item_id,
        data.get('source_type', 'hashtag'),
        data.get('source_query', ''),
        data.get('source_username', ''),
        data.get('source_media_pk', ''),
        data.get('media_type', 'photo'),
        data.get('local_path', ''),
        data.get('thumbnail_path', ''),
        data.get('original_caption', ''),
        data.get('ai_caption', ''),
        data.get('post_type', 'feed'),
        time.time()
    ))
    conn.commit()
    conn.close()
    return item_id

def get_content_items(status=None, limit=50):
    conn = get_connection()
    c = conn.cursor()
    if status:
        c.execute('SELECT * FROM content_items WHERE upload_status = ? ORDER BY created_at DESC LIMIT ?', (status, limit))
    else:
        c.execute('SELECT * FROM content_items ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_content_status(item_id: str, status: str, uploaded_at: float = None, ai_caption: str = None):
    conn = get_connection()
    c = conn.cursor()
    updates = ['upload_status = ?']
    params = [status]
    if uploaded_at:
        updates.append('uploaded_at = ?')
        params.append(uploaded_at)
    if ai_caption is not None:
        updates.append('ai_caption = ?')
        params.append(ai_caption)
    params.append(item_id)
    c.execute(f"UPDATE content_items SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

def delete_content_item(item_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT local_path, thumbnail_path FROM content_items WHERE id = ?', (item_id,))
    row = c.fetchone()
    c.execute('DELETE FROM content_items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    # Also remove local files if they exist
    if row:
        for path in [row['local_path'], row['thumbnail_path']]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

init_db()

