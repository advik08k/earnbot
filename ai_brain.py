import os
from google import genai
from google.genai import types

def get_genai_client(api_key=None):
    key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_KEY_1') or ''
    if not key:
        return None
    return genai.Client(api_key=key)

# -------------------------------------------------------------
# 1. OUTBOUND ICEBREAKER GENERATOR
# -------------------------------------------------------------
def generate_outbound_icebreaker(prospect_username: str, campaign: dict, api_key: str = None) -> str:
    """Generates a warm, authentic, non-spammy 1-2 sentence DM icebreaker based on campaign mode."""
    mode = campaign.get('mode', 'WEBSITE_DEV')
    target_handle = campaign.get('target_handle', '')
    
    fallbacks = {
        'WEBSITE_DEV': f"Hey @{prospect_username}! Loved your page and products. Quick question - do you take all your customer orders manually in DMs, or do you have an automated store link? Had an idea that could save you 2-3 hours daily 🙌",
        'REEL_HOOKS': f"Hey @{prospect_username}! Came across your content - love the consistency. Quick observation: noticed your reel hooks could easily get 2x-3x higher retention. Mind if I share 1 custom viral hook I drafted for you for free?",
        'FITNESS_PLAN': f"Hey @{prospect_username}! Saw your profile. Quick question - are you currently training for fat loss or lean muscle building? Had a quick thought about your workout split 💪",
        'CUSTOM': f"Hey @{prospect_username}! Stumbled upon your page. " + (campaign.get('custom_pitch') or "Loved what you're doing, had a quick question for you!")
    }

    client = get_genai_client(api_key)
    if not client:
        return fallbacks.get(mode, fallbacks['WEBSITE_DEV'])

    prompt = f"""
Write a 1-to-2 sentence cold Instagram Direct Message icebreaker to @{prospect_username}.
Target Competitor/Channel: @{target_handle}
Campaign Mode: {mode}
Offer Description: {campaign.get('offer_title', '')}

RULES:
1. Sound like a real, friendly, smart entrepreneur/specialist reaching out casually.
2. Under NO circumstances sound like a robotic spam sales bot. Do NOT use buzzwords like "Dear Sir/Madam", "Synergy", "Check out our services".
3. Write in friendly Hinglish or conversational English.
4. End with a simple, low-friction, open-ended question that is very easy to reply to.
5. Maximum 35 words. Return ONLY the message text.
"""
    if api_key and api_key.startswith("gsk_"):
        res = call_groq_simple(api_key, prompt, 0.7)
        if res: return res
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        res = call_jugaad_api("You are a helpful expert.", [{"role": "user", "text": prompt}], 0.7)
        if res: return res
        
    if api_key and api_key.startswith("gsk_"):
        res = call_groq_simple(api_key, prompt, 0.85)
        if res: return res
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        res = call_jugaad_api("You are a viral social media expert.", [{"role": "user", "text": prompt}], 0.85)
        if res: return res
        
    try:
        response = client.models.generate_content(
            model=get_best_model(client, 'gemini-2.0-flash'),
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.8)
        )
        msg = response.text.strip().replace('"', '')
        return msg if len(msg) > 10 else fallbacks.get(mode, fallbacks['WEBSITE_DEV'])
    except Exception as e:
        print(f"[AI Icebreaker Error] {e}")
        return fallbacks.get(mode, fallbacks['WEBSITE_DEV'])


# -------------------------------------------------------------
# 2. MODE-SPECIFIC SYSTEM PROMPT BUILDER
# -------------------------------------------------------------
def build_system_prompt(lead: dict, campaign: dict = None, upi_id: str = "confusedaryan@fam", default_price: str = "₹1,999") -> str:
    camp = campaign or {}
    mode = camp.get('mode') or lead.get('mode') or 'WEBSITE_DEV'
    price = camp.get('price') or default_price
    advance_amount = camp.get('advance_amount') or '₹499'
    upi = camp.get('upi_id') or upi_id
    custom_pitch = camp.get('custom_pitch') or ''
    
    stage = lead.get('stage', 'NEW')
    username = lead.get('username', 'Client')
    niche = lead.get('niche', '')

    if mode == 'WEBSITE_DEV':
        return f"""
You are chatting with @{username} on Instagram DMs. You are a completely normal human, a friendly dev/consultant chatting casually. 
NEVER sound like a bot, an AI, or a typical corporate customer service agent. Use extremely natural, casual language.
"Insaniyat dikhni chahiye" (Show humanity). Use short, punchy sentences. Use emojis naturally but sparsely.

YOUR GOAL (Long Term):
You help small Instagram brands build automated 1-Page E-commerce Stores (Price: {price}, Advance: {advance_amount}, UPI: `{upi}`).

CURRENT STAGE: {stage}

HOW TO BEHAVE:
1. ALWAYS read what they just said and reply to EXACTLY that. If they say "Why?", explain why normally. If they are angry, calm them down. If they ask a normal question, answer it directly.
2. DO NOT throw payment details or prices at them unless they explicitly ask to buy, or if you are deep into the conversation (PITCHED stage).
3. If they just said "Hi" or "Hey", just reply something like "Hey bro! Btao kaise help karu tumhari profile dekh kar message kiya tha" or similar.
4. DO NOT repeat the same pitch over and over.

LANGUAGE RULE:
- Talk exactly like an Indian youngster on Instagram (Hinglish). Use words like 'bhai', 'yaar', 'haan', 'sahi hai'. 
- If they speak English, reply in casual English.
"""
    else:
        return f"Be a helpful casual human. Context: {custom_pitch}"

def get_best_model(client, fallback='gemini-3.6-flash'):
    try:
        available = [m.name for m in client.models.list() if hasattr(m, 'supported_actions') and 'generateContent' in m.supported_actions]
        # Clean prefix
        available_names = [m.replace('models/', '') for m in available]
        
        # Priority list
        preferred = ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-2.5-flash']
        for p in preferred:
            if p in available_names:
                return p
                
        # Fallback to any flash that is NOT omni (omni has 0 quota on free tier often)
        flash_models = [m for m in available_names if 'flash' in m.lower() and 'omni' not in m.lower()]
        if flash_models:
            return sorted(flash_models, reverse=True)[0]
    except Exception as e:
        print(f"[Model Discovery Error] {e}")
    return fallback


import requests

def call_groq_api(api_key: str, system_prompt: str, raw_messages: list, temperature: float = 0.75) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload_messages = [{"role": "system", "content": system_prompt}]
    for msg in raw_messages:
        payload_messages.append({"role": msg["role"], "content": msg["text"]})
        
    payload = {
        "model": "llama-3.1-70b-versatile",
        "messages": payload_messages,
        "temperature": temperature
    }
    
    import time
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            print(f"[Groq Error] {e}")
            if hasattr(e, 'response') and e.response:
                print(e.response.text)
            return ""
    return ""

def generate_ai_reply(lead: dict, chat_history: list, incoming_msg: str, campaign: dict = None, upi_id: str = "confusedaryan@fam", default_price: str = "₹1,999", api_key: str = None) -> str:
    upi = (campaign.get('upi_id') if campaign else None) or upi_id
    price = (campaign.get('price') if campaign else None) or default_price
    
    system_instruction = build_system_prompt(lead, campaign, upi, price)
    
    raw_messages = []
    for msg in chat_history:
        role = "user" if msg['sender'] == 'user' else "assistant" if (api_key and api_key.startswith('gsk_')) else "model"
        raw_messages.append({"role": role, "text": msg['text']})
        
    raw_messages.append({"role": "user", "text": incoming_msg})
    
    if api_key and api_key.startswith("gsk_"):
        return call_groq_api(api_key, system_instruction, raw_messages, temperature=0.75)
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        return call_jugaad_api(system_instruction, raw_messages, temperature=0.75)
        
    # GEMINI LOGIC
    client = get_genai_client(api_key)
    if not client:
        return ""
        
    # Merge for Gemini
    merged_messages = []
    for msg in raw_messages:
        msg_copy = dict(msg)
        if msg_copy["role"] == "assistant": msg_copy["role"] = "model"
        if not merged_messages:
            merged_messages.append(msg_copy)
        else:
            if merged_messages[-1]["role"] == msg_copy["role"]:
                merged_messages[-1]["text"] += "\n\n" + msg_copy["text"]
            else:
                merged_messages.append(msg_copy)
                
    contents = []
    for msg in merged_messages:
        contents.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["text"])]))
    
    try:
        model_name = get_best_model(client, fallback='gemini-3.6-flash')
        import time
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.75)
                )
                return response.text.strip()
            except Exception as inner_e:
                if '503' in str(inner_e) and attempt == 0:
                    print(f"[AI Chat 503] Retrying after 2s...")
                    time.sleep(2)
                    continue
                raise inner_e
    except Exception as e:
        print(f"[AI Chat Error] {e}")
        return ""

# -------------------------------------------------------------
# 4. INSTANT DIGITAL FULFILLMENT / BLUEPRINT GENERATOR
# -------------------------------------------------------------
def call_groq_simple(api_key: str, prompt: str, temperature: float = 0.75) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature
    }
    import requests
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Groq Simple Error] {e}")
        return ""


def call_jugaad_api(system_prompt: str, raw_messages: list, temperature: float = 0.75) -> str:
    url = "https://text.pollinations.ai/"
    
    payload_messages = [{"role": "system", "content": system_prompt}]
    for msg in raw_messages:
        payload_messages.append({"role": msg["role"], "content": msg["text"]})
        
    payload = {
        "model": "openai",
        "messages": payload_messages,
        "temperature": temperature
    }
    
    import requests
    import time
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=25)
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            print(f"[Jugaad Error] {e}")
            return ""
    return ""

def generate_digital_product(lead: dict, campaign: dict = None, api_key: str = None) -> str:
    """Generates the comprehensive deliverable once payment/advance is confirmed."""
    client = get_genai_client(api_key)
    mode = (campaign.get('mode') if campaign else None) or lead.get('mode') or 'WEBSITE_DEV'
    username = lead.get('username', 'Valued Client')
    
    if not client:
        if mode == 'WEBSITE_DEV':
            return "🎉 Payment Confirmed! Our dev team is setting up your 1-Page E-commerce store. Please reply with: 1) Store Name, 2) Top 5 products with photos & prices, 3) WhatsApp number for order notifications."
        else:
            return "🎉 Payment Confirmed! Your custom blueprint has been queued and is being delivered right to your DM."

    if mode == 'WEBSITE_DEV':
        prompt = f"""
Create a comprehensive E-Commerce Store Architecture & Onboarding Blueprint for client @{username}.
They just paid the advance booking for their automated 1-page mobile store with UPI integration.

INCLUDE:
1. 🛍️ Store Design Concept (Clean, high-converting mobile layout with 1-click UPI checkout).
2. 📱 WhatsApp Order Notification Workflow (How they will receive automated order alerts with customer name, address, and paid amount).
3. 📋 Required Assets Intake Checklist:
   - Store Name & Brand Tagline
   - High-res Logo or Brand Photo
   - Top 5-10 Products (Title, selling price, photo, variants if any)
   - Delivery / Shipping fee rules
   - WhatsApp business number for incoming order alerts
4. ⏱️ 24-Hour Launch Timeline (Milestones from asset receipt to live domain & testing).

Format professionally with crisp emojis and clear sections. Around 350-450 words.
"""
    elif mode == 'REEL_HOOKS':
        prompt = f"""
Create a premium pack of 30 High-Retention Viral Reel Hooks tailored for client @{username}.
Niche: {lead.get('niche') or 'Content Creator / Brand'}

Categorize into:
1. 🪝 6 'Curiosity Gap' Hooks (Stops scrolling immediately)
2. 🤯 6 'Contrarian / Hot Take' Hooks (Debunks common myths)
3. 💡 6 'Step-by-Step Value' Hooks (High save rate)
4. 📈 6 'Relatability & Emotion' Hooks (High share rate)
5. 💰 6 'Direct Offer / Conversion' Hooks (Drives DMs and sales)

Format cleanly with numbers and emojis.
"""
    elif mode == 'FITNESS_PLAN':
        prompt = f"""
Create a complete 4-Week Custom Workout & Nutrition Protocol for client @{username}.
Include:
1. 🏋️ 4-Day Weekly Workout Split (Chest/Triceps, Back/Biceps, Legs/Core, Shoulders/HIIT with sets and reps).
2. 🥗 Flexible Macro Diet Blueprint (High protein meal timing, hydration, simple Indian/global grocery staples).
3. ⚡ 3 Non-Negotiable Recovery & Sleep Rules for continuous progress.

Format with clear headers and actionable bullet points.
"""
    else:
        prompt = f"""
Generate a high-value customized digital deliverable for client @{username}.
Offer: {campaign.get('offer_title', 'Agency Blueprint') if campaign else 'Agency Blueprint'}.
Make it practical, structured, and immediately useful. Around 350-450 words.
"""

    if api_key and api_key.startswith("gsk_"):
        res = call_groq_simple(api_key, prompt, 0.7)
        if res: return res
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        res = call_jugaad_api("You are a helpful expert.", [{"role": "user", "text": prompt}], 0.7)
        if res: return res
        
    if api_key and api_key.startswith("gsk_"):
        res = call_groq_simple(api_key, prompt, 0.85)
        if res: return res
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        res = call_jugaad_api("You are a viral social media expert.", [{"role": "user", "text": prompt}], 0.85)
        if res: return res
        
    try:
        response = client.models.generate_content(
            model=get_best_model(client, 'gemini-2.0-flash'),
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.7)
        )
        return response.text.strip()
    except Exception as e:
        print(f"[Product Generation Error] {e}")
        return "Thank you for your payment! Please share your brand/business details so we can finalize your customized deliverable immediately! 🚀"


# -------------------------------------------------------------
# 5. CONTENT STUDIO: AI CAPTION REWRITER
# -------------------------------------------------------------
def rewrite_caption_for_post(
    original_caption: str,
    niche: str = "",
    post_type: str = "feed",
    custom_instructions: str = "",
    api_key: str = None
) -> str:
    """
    Rewrites or generates a fresh Instagram caption for downloaded content.
    post_type: 'feed', 'reel', 'story'
    """
    client = get_genai_client(api_key)

    if not client:
        # Fallback: just clean up original a bit
        clean = original_caption[:300].strip() if original_caption else "Follow for more! 🔥"
        return clean + "\n\n#trending #viral #explore"

    niche_hint = f"Content Niche / Theme: {niche}" if niche else ""
    custom_hint = f"\nSpecial Instructions: {custom_instructions}" if custom_instructions else ""

    prompt = f"""
You are a top-tier Instagram Content Strategist & Caption Writer.
Rewrite or generate a brand-new viral Instagram caption for a {post_type} post.

Original Caption (use as inspiration / context, but completely rewrite):
\"\"\"{original_caption or 'No original caption provided.'}\"\"\"

{niche_hint}{custom_hint}

REQUIREMENTS:
1. Write a natural, engaging, human caption (NOT obviously AI-generated).
2. Hook in the first line — make it stop-scroll worthy.
3. Add 1–2 relevant emojis naturally (don't over-emoji).
4. 3–5 lines max for feed/reel. For story, 1 punchy line only.
5. End with a subtle CTA (save this, follow, comment below, link in bio, etc.).
6. Add 5–10 relevant trending hashtags at the bottom on a new line.
7. Write in English (or Hinglish if niche is Indian-focused).
8. Return ONLY the final caption text — no preamble, no explanations.
"""

    if api_key and api_key.startswith("gsk_"):
        res = call_groq_simple(api_key, prompt, 0.7)
        if res: return res
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        res = call_jugaad_api("You are a helpful expert.", [{"role": "user", "text": prompt}], 0.7)
        if res: return res
        
    if api_key and api_key.startswith("gsk_"):
        res = call_groq_simple(api_key, prompt, 0.85)
        if res: return res
        
    if api_key and api_key.strip().upper() == "JUGAAD":
        res = call_jugaad_api("You are a viral social media expert.", [{"role": "user", "text": prompt}], 0.85)
        if res: return res
        
    try:
        response = client.models.generate_content(
            model=get_best_model(client, 'gemini-2.0-flash'),
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.85)
        )
        return response.text.strip()
    except Exception as e:
        print(f"[Caption Rewrite Error] {e}")
        clean = original_caption[:250].strip() if original_caption else "Follow for more content like this!"
        return clean + "\n\n#reels #viral #explore #trending"
