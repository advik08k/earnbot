import os
import time
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_ID = '1HBq2KRKj3l-yHmoGabYIjArSM6ngWo2C'

_cached_products = ""
_last_fetch_time = 0

def get_drive_products():
    global _cached_products, _last_fetch_time
    
    if time.time() - _last_fetch_time < 600 and _cached_products:
        return _cached_products

    creds_path = 'credentials.json'
    if not os.path.exists(creds_path):
        creds_path = '/etc/secrets/credentials.json'
        
    if not os.path.exists(creds_path):
        return ""

    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)

        query = f"'{FOLDER_ID}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            pageSize=50,
            fields="nextPageToken, files(id, name, webViewLink)"
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            product_str = "Available Products: No products loaded yet."
        else:
            product_str = "Available Mega Bundles (Pitch these items enthusiastically to the client):\n"
            for item in items:
                # Remove extension for cleaner name
                clean_name = os.path.splitext(item['name'])[0]
                product_str += f"- Product Name: '{clean_name}' | Delivery Link: {item['webViewLink']}\n"
                
        _cached_products = product_str
        _last_fetch_time = time.time()
        return _cached_products

    except Exception as e:
        print(f"GDrive Error: {e}")
        return ""
