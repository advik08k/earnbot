import os
import time
import random
import asyncio
from pathlib import Path
from instagrapi import Client
from instagrapi.types import StoryMention, Location
import database
from ai_brain import generate_ai_reply, generate_digital_product, generate_outbound_icebreaker, rewrite_caption_for_post

MEDIA_DIR = Path(__file__).parent / "media_downloads"
MEDIA_DIR.mkdir(exist_ok=True)


class InstagramAgencyAgent:
    def __init__(self):
        self.cl = Client()
        self.is_logged_in = False
        self.my_user_id = None
        self.my_username = None
        self.last_checked_msg_ids = set()
        self.is_polling = False
        self.last_outbound_time = 0

    def login(self, session_id: str) -> bool:
        if not session_id:
            print("[Agent] Missing session ID.")
            self.is_logged_in = False
            return False
            
        try:
            print("[Agent] Logging into Instagram via Session ID...")
            self.cl.login_by_sessionid(session_id)
            info = self.cl.account_info()
            self.my_user_id = str(info.pk)
            self.my_username = info.username
            self.is_logged_in = True
            print(f"[Agent] Successfully logged in as @{self.my_username} (ID: {self.my_user_id})")
            return True
        except Exception as e:
            print(f"[Agent Login Error] {e}")
            self.is_logged_in = False
            return False

    # -------------------------------------------------------------
    # OUTBOUND PROSPECTING ENGINE
    # -------------------------------------------------------------
    def run_outbound_for_campaign(self, campaign: dict, max_to_send: int = 1) -> dict:
        """Finds target prospects from competitor profile and sends personalized cold DM."""
        if not self.is_logged_in:
            return {"success": False, "error": "Agent not logged in"}

        if not campaign.get('is_active', 1):
            return {"success": False, "error": "Campaign is paused"}

        daily_limit = int(campaign.get('daily_limit', 20))
        dms_sent_today = int(campaign.get('dms_sent_today', 0))

        if dms_sent_today >= daily_limit:
            return {"success": False, "error": f"Daily limit ({daily_limit}) reached for this campaign"}

        target_handle = campaign.get('target_handle', '').replace('@', '').strip()
        if not target_handle:
            return {"success": False, "error": "No target handle specified"}

        settings = database.get_settings()
        api_key = settings.get('gemini_api_key', '')

        try:
            # Prevent endless looping if this errors out
            self.last_outbound_time = time.time()
            
            print(f"[Outbound] Finding target user ID for @{target_handle}...")
            target_pk = self.cl.user_id_from_username(target_handle)
            
            # Fetch followers or recent commenters
            print(f"[Outbound] Fetching prospects from @{target_handle}...")
            followers = self.cl.user_followers(target_pk, amount=25)
            
            sent_count = 0
            # followers can be a dict {pk: user_short} or list
            user_list = list(followers.values()) if isinstance(followers, dict) else list(followers)

            for user in user_list:
                username = getattr(user, 'username', '')
                pk = str(getattr(user, 'pk', ''))

                if not username or not pk or pk == str(self.my_user_id):
                    continue

                # Skip if already contacted
                if database.is_prospect_contacted(username):
                    continue

                # Generate personalized cold icebreaker
                icebreaker = generate_outbound_icebreaker(
                    prospect_username=username,
                    campaign=campaign,
                    api_key=api_key
                )

                print(f"[Outbound DM] Sending cold pitch to @{username} (Campaign: {campaign.get('offer_title')}): \"{icebreaker}\"")
                
                # Send cold direct message
                thread = self.cl.direct_send(icebreaker, user_ids=[int(pk)])
                thread_id = getattr(thread, 'id', str(pk))

                # Mark contacted
                database.mark_prospect_contacted(username, pk, campaign['id'])
                
                # Create lead record
                database.get_or_create_lead(
                    thread_id=thread_id,
                    user_id=pk,
                    username=username,
                    full_name=getattr(user, 'full_name', ''),
                    campaign_id=campaign['id'],
                    mode=campaign.get('mode', 'WEBSITE_DEV'),
                    is_outbound=1
                )
                
                # Save outgoing message in thread
                database.save_message(thread_id, 'bot', icebreaker)

                sent_count += 1
                self.last_outbound_time = time.time()

                if sent_count >= max_to_send:
                    break

                # Safety jitter between multiple sends
                time.sleep(random.uniform(4.0, 7.0))

            return {"success": True, "sent": sent_count}

        except Exception as e:
            print(f"[Outbound Error] Failed during campaign prospecting: {e}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------
    # INBOUND DM PROCESSOR & CONVERSATION HANDLER
    # -------------------------------------------------------------
    def process_thread(self, thread, settings: dict):
        if not thread.messages:
            return

        last_msg = thread.messages[0]
        msg_id = str(last_msg.id)
        sender_id = str(last_msg.user_id)
        msg_text = getattr(last_msg, 'text', '') or ''
        
        # 1. Skip if message was sent by our own bot account
        if sender_id == str(self.my_user_id):
            return

        # 2. Skip if already processed this exact message
        if msg_id in self.last_checked_msg_ids:
            return
            
        self.last_checked_msg_ids.add(msg_id)
        if len(self.last_checked_msg_ids) > 500:
            self.last_checked_msg_ids.pop()

        # Find target user details
        other_user = next((u for u in thread.users if str(u.pk) != str(self.my_user_id)), None)
        username = other_user.username if other_user else 'Client'
        full_name = other_user.full_name if other_user else ''

        print(f"[Incoming DM] @{username}: \"{msg_text}\"")

        # 3. Retrieve or create lead record
        lead = database.get_or_create_lead(
            thread_id=thread.id,
            user_id=sender_id,
            username=username,
            full_name=full_name
        )

        # Look up associated campaign if any
        campaign = None
        if lead.get('campaign_id'):
            campaign = database.get_campaign(lead['campaign_id'])
            
        # If lead has no campaign, check if there's an active campaign to link
        if not campaign:
            campaigns = database.get_campaigns()
            active_camps = [c for c in campaigns if c.get('is_active', 1)]
            if active_camps:
                campaign = active_camps[0]
                lead['campaign_id'] = campaign['id']
                lead['mode'] = campaign.get('mode', 'WEBSITE_DEV')

        # Save incoming user message
        database.save_message(thread.id, 'user', msg_text)

        # 4. Check conversation history
        history = database.get_thread_messages(thread.id, limit=10)

        # 5. Funnel Stage Transition Logic
        current_stage = lead.get('stage', 'NEW')
        msg_lower = msg_text.lower()

        is_payment_confirmation = any(w in msg_lower for w in [
            'paid', 'done', 'sent', 'bhej diya', 'advance bhej diya', 'screenshot', 'pay kar diya', 'payment ho gaya', 'advance done'
        ])

        upi_id = (campaign.get('upi_id') if campaign else None) or settings.get('upi_id', 'confusedaryan@fam')
        price = (campaign.get('price') if campaign else None) or settings.get('product_price', '₹1,999')
        api_key = settings.get('gemini_api_key', '')

        reply_text = ""

        if is_payment_confirmation and current_stage in ['PITCHED', 'DISCOVERY', 'NEW', 'IN_PROGRESS']:
            print(f"[Funnel] Payment/Advance detected from @{username}! Moving to PENDING_APPROVAL...")
            database.update_lead(thread.id, stage='PENDING_APPROVAL')
            lead['stage'] = 'PENDING_APPROVAL'
            
            reply_text = f"Got it @{username}! I am verifying your payment with our team right now. Please give me a moment... ⏳"
        
        else:
            # Normal AI consultation & pitch reply
            reply_text = generate_ai_reply(
                lead=lead,
                chat_history=history,
                incoming_msg=msg_text,
                campaign=campaign,
                upi_id=upi_id,
                default_price=price,
                api_key=api_key
            )

            # Advance funnel stage
            if current_stage == 'NEW' and len(history) >= 2:
                database.update_lead(thread.id, stage='DISCOVERY')
            elif current_stage == 'DISCOVERY' and len(history) >= 4:
                database.update_lead(thread.id, stage='PITCHED')

        if not reply_text:
            print(f"[Agent] AI returned empty (likely error). Skipping reply to @{username} to avoid spam/crashes.")
            return

        # 6. Simulate human typing delay (2.5 - 4.5 seconds)
        print(f"[Agent] Replying to @{username} in simulated typing...")
        time.sleep(random.uniform(2.5, 4.5))

        try:
            self.cl.direct_answer(thread.id, reply_text)
            database.save_message(thread.id, 'bot', reply_text)
            print(f"[Outgoing DM] Sent to @{username}: \"{reply_text[:60]}...\"")
        except Exception as e:
            print(f"[Send Error] Failed to send DM to @{username}: {e}")

    # -------------------------------------------------------------
    # INBOX POLLER & OUTBOUND TICK
    # -------------------------------------------------------------
    def poll_once(self):
        settings = database.get_settings()
        if settings.get('is_active', '1') != '1':
            return

        session_id = settings.get('session_id', '')
        if not self.is_logged_in:
            if session_id:
                self.login(session_id)
            else:
                return

        try:
            # 1. Inbound Inbox check (top 10 threads)
            threads = self.cl.direct_threads(amount=10)
            for thread in threads:
                self.process_thread(thread, settings)
        except Exception as e:
            print(f"[Poll Error] {e}")
            if 'login_required' in str(e).lower() or 'checkpoint' in str(e).lower():
                self.is_logged_in = False

        # 2. Outbound safe cycle: only trigger automatically if at least 15 minutes passed since last outbound DM
        now = time.time()
        if now - self.last_outbound_time > 900:  # 15 minutes
            active_campaigns = [c for c in database.get_campaigns() if c.get('is_active', 1)]
            for camp in active_campaigns:
                if int(camp.get('dms_sent_today', 0)) < int(camp.get('daily_limit', 20)):
                    print(f"[Auto-Outbound] Running periodic scheduled outreach for campaign: {camp.get('target_handle')}")
                    self.run_outbound_for_campaign(camp, max_to_send=1)
                    break  # Send 1 at a time to keep account completely safe

    async def run_loop(self):
        self.is_polling = True
        print("[Agent] Direct Message Polling loop started (15s interval).")
        while self.is_polling:
            try:
                self.poll_once()
            except Exception as e:
                print(f"[Loop Exception] {e}")
            await asyncio.sleep(15)

    # =============================================================
    # CONTENT STUDIO ENGINE
    # =============================================================

    def _media_to_dict(self, media, source_type: str, source_query: str) -> dict:
        """Convert instagrapi Media object to a DB-ready dict."""
        pk = str(media.pk)
        user = getattr(media, 'user', None)
        uname = getattr(user, 'username', '') if user else ''
        caption_obj = getattr(media, 'caption_text', None)
        caption = caption_obj if isinstance(caption_obj, str) else ''
        media_type_num = getattr(media, 'media_type', 1)
        # 1 = photo, 2 = video/reel, 8 = album
        media_type = 'video' if media_type_num == 2 else 'photo'
        return {
            'source_type': source_type,
            'source_query': source_query,
            'source_username': uname,
            'source_media_pk': pk,
            'media_type': media_type,
            'original_caption': caption,
            'local_path': '',
            'thumbnail_path': '',
            'post_type': 'reel' if media_type_num == 2 else 'feed'
        }

    def scrape_content(self, source_type: str, query: str, amount: int = 10) -> dict:
        """
        Scrape media from Instagram without downloading files.
        source_type: 'hashtag' | 'username' | 'url' | 'explore'
        Returns list of scraped items added to DB.
        """
        if not self.is_logged_in:
            return {"success": False, "error": "Not logged in"}

        medias = []
        try:
            if source_type == 'hashtag':
                tag = query.lstrip('#').strip()
                print(f"[Content] Fetching top posts for #{tag}...")
                medias = self.cl.hashtag_medias_top(tag, amount=amount)
                if len(medias) < amount:
                    recent = self.cl.hashtag_medias_recent(tag, amount=amount - len(medias))
                    medias.extend(recent)

            elif source_type == 'username':
                handle = query.lstrip('@').strip()
                print(f"[Content] Fetching posts from @{handle}...")
                user_pk = self.cl.user_id_from_username(handle)
                medias = self.cl.user_medias(user_pk, amount=amount)

            elif source_type == 'url':
                print(f"[Content] Fetching media from URL: {query}...")
                media_pk = self.cl.media_pk_from_url(query)
                media = self.cl.media_info(media_pk)
                medias = [media]

        except Exception as e:
            print(f"[Content Scrape Error] {e}")
            return {"success": False, "error": str(e)}

        saved = 0
        for m in medias:
            d = self._media_to_dict(m, source_type, query)
            # Skip if already in DB
            existing = database.get_content_items()
            existing_pks = {i['source_media_pk'] for i in existing}
            if d['source_media_pk'] in existing_pks:
                continue
            database.create_content_item(d)
            saved += 1

        print(f"[Content] Scraped {saved} new items from {source_type}: {query}")
        return {"success": True, "scraped": saved, "total": len(medias)}

    def download_content_item(self, item: dict) -> dict:
        """Download the actual media file for a queued content item."""
        if not self.is_logged_in:
            return {"success": False, "error": "Not logged in"}

        pk = item.get('source_media_pk')
        item_id = item.get('id')
        media_type = item.get('media_type', 'photo')

        try:
            out_dir = MEDIA_DIR / item_id
            out_dir.mkdir(exist_ok=True)

            local_path = ''
            thumb_path = ''

            if media_type == 'video':
                print(f"[Content] Downloading video/reel {pk}...")
                path = self.cl.clip_download(pk, folder=str(out_dir))
                local_path = str(path)
                # Try to get thumbnail
                try:
                    media = self.cl.media_info(pk)
                    thumb_url = getattr(media, 'thumbnail_url', None)
                    if thumb_url:
                        thumb_path = str(self.cl.photo_download_by_url(str(thumb_url), folder=str(out_dir)))
                except:
                    pass
            else:
                print(f"[Content] Downloading photo {pk}...")
                path = self.cl.photo_download(pk, folder=str(out_dir))
                local_path = str(path)
                thumb_path = local_path  # same file for photos

            database.update_content_status(item_id, 'downloaded')
            # Store local paths
            conn = database.get_connection()
            c = conn.cursor()
            c.execute('UPDATE content_items SET local_path = ?, thumbnail_path = ? WHERE id = ?',
                      (local_path, thumb_path, item_id))
            conn.commit()
            conn.close()

            print(f"[Content] Downloaded: {local_path}")
            return {"success": True, "local_path": local_path}

        except Exception as e:
            print(f"[Content Download Error] {e}")
            database.update_content_status(item_id, 'download_failed')
            return {"success": False, "error": str(e)}

    def generate_caption_for_item(self, item: dict, niche: str = '', custom_instructions: str = '') -> str:
        """Generate AI-rewritten caption for a content item and save to DB."""
        settings = database.get_settings()
        api_key = settings.get('gemini_api_key', '')

        caption = rewrite_caption_for_post(
            original_caption=item.get('original_caption', ''),
            niche=niche,
            post_type=item.get('post_type', 'feed'),
            custom_instructions=custom_instructions,
            api_key=api_key
        )
        database.update_content_status(item['id'], item.get('upload_status', 'downloaded'), ai_caption=caption)
        return caption

    def upload_content_item(self, item: dict, caption: str = None, post_type: str = None) -> dict:
        """
        Upload a downloaded content item to Instagram.
        post_type: 'feed' | 'reel' | 'story'
        """
        if not self.is_logged_in:
            return {"success": False, "error": "Not logged in"}

        local_path = item.get('local_path', '')
        if not local_path or not os.path.exists(local_path):
            return {"success": False, "error": f"Local file not found: {local_path}. Download it first."}

        media_type = item.get('media_type', 'photo')
        final_post_type = post_type or item.get('post_type', 'feed')
        final_caption = caption or item.get('ai_caption') or item.get('original_caption') or ''

        try:
            print(f"[Content] Uploading {media_type} as {final_post_type}... Path: {local_path}")

            if final_post_type == 'story':
                if media_type == 'video':
                    self.cl.video_upload_to_story(local_path)
                else:
                    self.cl.photo_upload_to_story(local_path)

            elif final_post_type == 'reel' and media_type == 'video':
                self.cl.clip_upload(local_path, caption=final_caption)

            elif media_type == 'video':
                self.cl.video_upload(local_path, caption=final_caption)

            else:
                self.cl.photo_upload(local_path, caption=final_caption)

            import time as _time
            database.update_content_status(item['id'], 'uploaded', uploaded_at=_time.time())
            print(f"[Content] Uploaded successfully!")
            return {"success": True, "post_type": final_post_type}

        except Exception as e:
            print(f"[Content Upload Error] {e}")
            database.update_content_status(item['id'], 'upload_failed')
            return {"success": False, "error": str(e)}
