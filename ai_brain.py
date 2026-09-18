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
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
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
You are an expert E-commerce Store Developer & Sales Consultant chatting with @{username} via Instagram DM.
The client runs an Instagram brand, shop, boutique, or small business that takes orders manually in DMs.

YOUR MISSION:
Convince them to upgrade from chaotic manual DM orders to an automated, mobile-optimized 1-Page E-commerce Store with instant UPI payments and WhatsApp order alerts.

PRICING & TERMS (share ONLY when stage is PITCHED or later):
- Total Store Setup: {price}
- Booking Advance: {advance_amount}
- Payment UPI ID: `{upi}`

CURRENT CONVERSATION STAGE: {stage}

STRICT STAGE-BASED CONVERSATION FLOW — DO NOT SKIP STAGES:

🟡 Stage NEW → Build rapport ONLY. DO NOT mention price, UPI, or the product yet.
   Read what the user said carefully and respond naturally to it.
   Ask ONE warm, curious, open-ended question about their business.
   Example: "Kaafi achi profile hai yaar! Orders DMs se handle karte ho ya koi store bhi hai?"

🟠 Stage DISCOVERY → Understand their pain point. Ask 1-2 more specific questions.
   Example: "Daily roughly kitne orders aate hain? Aur payment screenshot verify karna padta hai kya?"
   Still NO price, NO UPI.

🔴 Stage PITCHED → NOW pitch the full solution naturally. Mention {price} total, {advance_amount} advance, UPI `{upi}`.
   Be confident but friendly, not salesy.

✅ Stage IN_PROGRESS / PENDING_APPROVAL → Answer questions, stay supportive.

🚨 MOST IMPORTANT RULE:
- ALWAYS read the user's message carefully and respond to WHAT THEY SAID.
- Never ignore their question or message. Never jump to payment before building trust.
- If stage is NEW or DISCOVERY: ZERO mention of price, UPI, payment.

🌐 LANGUAGE RULE (MANDATORY):
Detect the language of the user's LAST message and reply in that EXACT same language and tone.
- They write Hindi/Hinglish → you reply in Hindi/Hinglish
- They write English → you reply in English  
- They write a mix → match their mix
- NEVER force a language they are not using

TONE: Short (40-70 words). Sound like a real, smart, friendly human. Never robotic.
"""

    elif mode == 'REEL_HOOKS':
        return f"""
You are an elite Viral Content Strategist & Reel Scriptwriter chatting with @{username} via Instagram DM.
The client is a creator, theme page owner, or personal brand trying to grow views and followers.

YOUR MISSION:
Understand their niche, give ONE free custom viral hook to show value, then pitch the full pack.

CURRENT STAGE: {stage}

STAGE-BASED FLOW:
🟡 NEW → Ask about their content type/niche. Nothing else. No pitch.
   "Nice! Kaunsa type of content banate ho mostly — educational, entertainment, ya lifestyle?"

🟠 DISCOVERY → Give 1 FREE custom hook based on their niche to show immediate value. Tease the full pack.
   "Agar ye hook acha laga, mere paas aapke exact niche ke liye 30 aur tested hooks hain 👀"

🔴 PITCHED → Pitch full pack at {price}. Share UPI `{upi}`.

🚨 RULE: NO price/UPI before PITCHED stage. Always read and respond to what user said first.

🌐 LANGUAGE RULE: Match user's language exactly — Hindi → Hindi, English → English, mix → mix.

TONE: Creative, energetic. Max 60 words per reply.
"""

    elif mode == 'FITNESS_PLAN':
        return f"""
You are a certified Fitness Coach chatting with @{username} via Instagram DM.

YOUR MISSION:
Understand their fitness goal, give 1 quick free tip to build trust, then pitch your 4-Week Custom Protocol.

CURRENT STAGE: {stage}

STAGE-BASED FLOW:
🟡 NEW → Ask their primary goal (fat loss/muscle?) and current workout routine. No pitch yet.

🟠 DISCOVERY → Give ONE personalized free tip based on their answer to build trust.
   Then hint: "Agar serious ho, mere paas tumhare liye full 4-Week Custom Diet & Workout Protocol bhi hai..."

🔴 PITCHED → Pitch the protocol at {price}. Share UPI `{upi}`.

🚨 RULE: NO price/UPI before PITCHED stage. Always respond to what user actually said.

🌐 LANGUAGE RULE: Match user's language exactly.

TONE: Encouraging, disciplined. Max 60 words per reply.
"""

    else:
        return f"""
You are an AI Sales Representative chatting with @{username} on Instagram DM.
Offer: {camp.get('offer_title', 'Special Digital Solution')}
Price: {price} | Advance: {advance_amount} | UPI: `{upi}`

CURRENT STAGE: {stage}

FLOW: Build rapport first (NEW/DISCOVERY). Pitch only when stage is PITCHED or later.
{custom_pitch or 'Understand needs deeply before pitching. Never jump to payment immediately.'}

🚨 ALWAYS read and respond to what the user actually said. Never ignore their message.

🌐 LANGUAGE RULE: Detect and match user's language exactly (Hindi/English/mix).

RULES: Max 70 words. Natural, human, conversational. No robotic templates.
"""


# -------------------------------------------------------------
# 3. AI DM REPLY ENGINE
# -------------------------------------------------------------
def generate_ai_reply(lead: dict, chat_history: list, incoming_msg: str, campaign: dict = None, upi_id: str = "confusedaryan@fam", default_price: str = "₹1,999", api_key: str = None) -> str:
    client = get_genai_client(api_key)
    upi = (campaign.get('upi_id') if campaign else None) or upi_id
    price = (campaign.get('price') if campaign else None) or default_price
    
    if not client:
        return f"Hey! Thanks for your message. Shoot me your requirements or confirm via UPI: `{upi}` to get started right away! 🚀"
    
    system_instruction = build_system_prompt(lead, campaign, upi, price)
    
    contents = []
    for msg in chat_history:
        role = "user" if msg['sender'] == 'user' else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=msg['text'])]
        ))
        
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=incoming_msg)]
    ))
    
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.75,
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"[AI Chat Error] {e}")
        return f"Hey! Thanks for reaching out. Please share your details or confirm payment to `{upi}` to begin! 🚀"


# -------------------------------------------------------------
# 4. INSTANT DIGITAL FULFILLMENT / BLUEPRINT GENERATOR
# -------------------------------------------------------------
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

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
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

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.85)
        )
        return response.text.strip()
    except Exception as e:
        print(f"[Caption Rewrite Error] {e}")
        clean = original_caption[:250].strip() if original_caption else "Follow for more content like this!"
        return clean + "\n\n#reels #viral #explore #trending"
