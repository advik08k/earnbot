import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import database
from ig_agent import InstagramAgencyAgent

agent = InstagramAgencyAgent()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-login on startup if session_id is in DB
    settings = database.get_settings()
    if settings.get('session_id'):
        agent.login(settings['session_id'])
        
    # Start background polling loop
    polling_task = asyncio.create_task(agent.run_loop())
    yield
    agent.is_polling = False
    polling_task.cancel()

app = FastAPI(title="Auto-Pilot AI Agency", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SettingsUpdate(BaseModel):
    session_id: str = None
    upi_id: str = None
    product_price: str = None
    is_active: str = None
    gemini_api_key: str = None

class CampaignCreate(BaseModel):
    target_handle: str
    mode: str = "WEBSITE_DEV"
    offer_title: str = "E-commerce Website Setup"
    price: str = "₹1,999"
    advance_amount: str = "₹499"
    upi_id: str = "confusedaryan@fam"
    custom_pitch: str = ""
    daily_limit: int = 20

class CampaignToggle(BaseModel):
    is_active: int

class SendMessageRequest(BaseModel):
    text: str

class StageUpdateRequest(BaseModel):
    stage: str

@app.get("/api/status")
def get_status():
    settings = database.get_settings()
    leads = database.get_all_leads()
    campaigns = database.get_campaigns()
    active_campaigns = [c for c in campaigns if c.get("is_active", 1)]
    
    total_outbound = sum(c.get("dms_sent_today", 0) for c in campaigns)

    return {
        "is_active": settings.get("is_active", "1") == "1",
        "is_logged_in": agent.is_logged_in,
        "bot_username": agent.my_username,
        "upi_id": settings.get("upi_id", "confusedaryan@fam"),
        "total_leads": len(leads),
        "total_campaigns": len(campaigns),
        "active_campaigns": len(active_campaigns),
        "outbound_sent_today": total_outbound,
        "fulfilled_leads": len([l for l in leads if l["stage"] == "FULFILLED"])
    }

@app.get("/api/settings")
def get_settings():
    return database.get_settings()

@app.post("/api/settings")
def update_settings_endpoint(payload: SettingsUpdate):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    database.update_settings(data)
    
    # If session_id changed, re-login
    if "session_id" in data and data["session_id"]:
        agent.login(data["session_id"])
        
    return {"success": True, "settings": database.get_settings()}

# --- Campaigns Endpoints ---
@app.get("/api/campaigns")
def get_campaigns():
    return database.get_campaigns()

@app.post("/api/campaigns")
def create_campaign_endpoint(payload: CampaignCreate):
    camp_id = database.create_campaign(payload.dict())
    return {"success": True, "campaign_id": camp_id}

@app.post("/api/campaigns/{campaign_id}/toggle")
def toggle_campaign_endpoint(campaign_id: str, payload: CampaignToggle):
    database.toggle_campaign(campaign_id, payload.is_active)
    return {"success": True}

@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign_endpoint(campaign_id: str):
    database.delete_campaign(campaign_id)
    return {"success": True}

@app.post("/api/campaigns/{campaign_id}/run_outbound")
def trigger_outbound_endpoint(campaign_id: str):
    campaign = database.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    result = agent.run_outbound_for_campaign(campaign, max_to_send=1)
    return result

# --- Leads Endpoints ---
@app.get("/api/leads")
def get_leads():
    return database.get_all_leads()

@app.get("/api/leads/{thread_id}/messages")
def get_messages(thread_id: str):
    return database.get_thread_messages(thread_id, limit=30)

@app.post("/api/leads/{thread_id}/stage")
def update_stage(thread_id: str, payload: StageUpdateRequest):
    database.update_lead(thread_id, stage=payload.stage)
    return {"success": True}

@app.post("/api/leads/{thread_id}/send")
def send_manual_message(thread_id: str, payload: SendMessageRequest):
    if not agent.is_logged_in:
        raise HTTPException(status_code=400, detail="Instagram agent is not logged in.")
        
    try:
        agent.cl.direct_answer(thread_id, payload.text)
        database.save_message(thread_id, 'bot', payload.text)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/leads/{thread_id}/approve")
def approve_payment(thread_id: str, background_tasks: BackgroundTasks):
    """Manually approve a payment and deliver the digital product via AI."""
    if not agent.is_logged_in:
        raise HTTPException(status_code=400, detail="Not logged in")
    
    leads = database.get_all_leads()
    lead = next((l for l in leads if l['thread_id'] == thread_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    def deliver_product():
        try:
            campaign = database.get_campaign(lead.get('campaign_id', '')) if lead.get('campaign_id') else {}
            if not campaign:
                active = [c for c in database.get_campaigns() if c.get('is_active', 1)]
                if active: campaign = active[0]
            
            settings = database.get_settings()
            api_key = settings.get('gemini_api_key', '')
            
            from ai_brain import generate_digital_product
            deliverable = generate_digital_product(lead, campaign, api_key)
            product_msg = f"🎉 Payment Verified! Welcome aboard, @{lead.get('username')}!\n\n{deliverable}\n\nLet's get this rolling! 🚀"
            
            agent.cl.direct_answer(thread_id, product_msg)
            database.save_message(thread_id, 'bot', product_msg)
            database.update_lead(thread_id, stage='FULFILLED')
            print(f"[Approval] Product delivered to {lead.get('username')}")
        except Exception as e:
            print(f"[Approval Delivery Error] {e}")

    background_tasks.add_task(deliver_product)
    return {"success": True, "message": "Approval processing..."}

@app.post("/api/leads/{thread_id}/reject")
def reject_payment(thread_id: str):
    """Manually reject a payment and ask for screenshot."""
    if not agent.is_logged_in:
        raise HTTPException(status_code=400, detail="Not logged in")
        
    settings = database.get_settings()
    upi = settings.get('upi_id', 'confusedaryan@fam')
    reject_msg = f"Hey, we just checked but couldn't verify the payment on our end. Could you please double-check if the amount was deducted and sent to {upi}? A screenshot would really help! 🙏"
    
    try:
        agent.cl.direct_answer(thread_id, reject_msg)
        database.save_message(thread_id, 'bot', reject_msg)
        database.update_lead(thread_id, stage='IN_PROGRESS')
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Content Studio Endpoints ---
class ContentScrapeRequest(BaseModel):
    source_type: str  # 'hashtag' | 'username' | 'url'
    query: str
    amount: int = 10

class ContentCaptionRequest(BaseModel):
    niche: str = ""
    custom_instructions: str = ""

class ContentUploadRequest(BaseModel):
    post_type: str = "feed"   # 'feed' | 'reel' | 'story'
    caption: str = ""

@app.get("/api/content")
def get_content_items(status: str = None):
    return database.get_content_items(status=status or None)

@app.post("/api/content/scrape")
def scrape_content_endpoint(payload: ContentScrapeRequest):
    """Scrape media metadata from Instagram (no file downloads yet)."""
    result = agent.scrape_content(
        source_type=payload.source_type,
        query=payload.query,
        amount=payload.amount
    )
    return result

@app.post("/api/content/{item_id}/download")
def download_content_endpoint(item_id: str, background_tasks: BackgroundTasks):
    """Download the actual media file for a content item."""
    items = database.get_content_items()
    item = next((i for i in items if i['id'] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    
    # Run in background so it doesn't block FastAPI
    background_tasks.add_task(agent.download_content_item, item)
    return {"success": True, "message": "Download started in background"}

@app.post("/api/content/{item_id}/caption")
def generate_caption_endpoint(item_id: str, payload: ContentCaptionRequest):
    """Generate AI caption for a content item."""
    items = database.get_content_items()
    item = next((i for i in items if i['id'] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    caption = agent.generate_caption_for_item(
        item,
        niche=payload.niche,
        custom_instructions=payload.custom_instructions
    )
    return {"success": True, "caption": caption}

@app.post("/api/content/{item_id}/upload")
def upload_content_endpoint(item_id: str, payload: ContentUploadRequest, background_tasks: BackgroundTasks):
    """Upload a downloaded content item to your Instagram account."""
    items = database.get_content_items()
    item = next((i for i in items if i['id'] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    caption = payload.caption or item.get('ai_caption') or item.get('original_caption') or ''
    
    # Run in background so it doesn't block FastAPI
    background_tasks.add_task(agent.upload_content_item, item, caption=caption, post_type=payload.post_type)
    return {"success": True, "message": "Upload started in background"}

@app.delete("/api/content/{item_id}")
def delete_content_endpoint(item_id: str):
    database.delete_content_item(item_id)
    return {"success": True}

@app.get("/media_serve/{item_id}/thumb")
def serve_thumbnail(item_id: str):
    """Serve thumbnail/preview image for a content item."""
    items = database.get_content_items()
    item = next((i for i in items if i['id'] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    path = item.get('thumbnail_path') or item.get('local_path', '')
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not downloaded yet")
    return FileResponse(path)

# Mount frontend public static directory
public_dir = os.path.join(os.path.dirname(__file__), "public")
if not os.path.exists(public_dir):
    os.makedirs(public_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)


