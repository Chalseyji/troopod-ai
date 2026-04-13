from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
import requests
from bs4 import BeautifulSoup
import os
import base64
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def scrape_landing_page(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        return response.text
    except Exception as e:
        return None

def analyze_ad(image_data=None, ad_url=None):
    prompt = """Analyze this ad creative and extract:
1. Main headline
2. Key offer or value proposition
3. Call to action (CTA)
4. Tone (urgent, friendly, professional, etc.)
5. Target audience
6. Key colors or visual theme

Return as a structured summary."""

    try:
        if image_data:
            image_parts = [{"mime_type": "image/jpeg", "data": image_data}]
            response = model.generate_content([prompt, image_parts[0]])
        else:
            response = model.generate_content(f"{prompt}\nAd URL: {ad_url}")
        return response.text
    except Exception as e:
        return f"Error analyzing ad: {str(e)}"

def personalize_page(html_content, ad_analysis):
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract text elements to rewrite
    title = soup.find("title")
    h1_tags = soup.find_all("h1")
    h2_tags = soup.find_all("h2")
    cta_buttons = soup.find_all("button") + soup.find_all("a", class_=lambda x: x and "btn" in x.lower())

    original_title = title.string if title else ""
    original_h1 = h1_tags[0].get_text() if h1_tags else ""
    original_h2 = h2_tags[0].get_text() if h2_tags else ""

    prompt = f"""You are a CRO (Conversion Rate Optimization) expert.

Based on this ad analysis:
{ad_analysis}

Rewrite these landing page elements to match the ad's message and improve conversion:

1. Page title (currently: "{original_title}")
2. Main headline H1 (currently: "{original_h1}")
3. Sub-headline H2 (currently: "{original_h2}")
4. CTA button text (make it action-oriented and match the ad offer)
5. A short hero description (2 sentences max) that bridges the ad promise to the page

Rules:
- Keep the same tone as the ad
- Be specific, not generic
- Don't change the page structure, only the copy
- Return ONLY a JSON object with keys: title, h1, h2, cta, hero_description"""

    try:
        response = model.generate_content(prompt)
        import json
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return None

def inject_changes(html_content, changes, ad_analysis):
    if not changes:
        return html_content

    soup = BeautifulSoup(html_content, "html.parser")

    # Update title
    if soup.find("title") and changes.get("title"):
        soup.find("title").string = changes["title"]

    # Update H1
    h1_tags = soup.find_all("h1")
    if h1_tags and changes.get("h1"):
        h1_tags[0].string = changes["h1"]

    # Update H2
    h2_tags = soup.find_all("h2")
    if h2_tags and changes.get("h2"):
        h2_tags[0].string = changes["h2"]

    # Inject personalization banner at top of body
    if soup.body and changes.get("hero_description"):
        banner = soup.new_tag("div")
        banner["style"] = """
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 24px;
            text-align: center;
            font-family: sans-serif;
            font-size: 16px;
            font-weight: 500;
            position: relative;
            z-index: 9999;
        """
        banner.string = changes["hero_description"]
        soup.body.insert(0, banner)

    return str(soup)

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        landing_url = request.form.get("landing_url")
        ad_url = request.form.get("ad_url", "")
        ad_image = request.files.get("ad_image")

        if not landing_url:
            return jsonify({"error": "Landing page URL is required"}), 400

        # Step 1: Analyze the ad
        image_data = None
        if ad_image:
            image_data = base64.b64encode(ad_image.read()).decode("utf-8")
            ad_analysis = analyze_ad(image_data=image_data)
        else:
            ad_analysis = analyze_ad(ad_url=ad_url)

        # Step 2: Scrape landing page
        html_content = scrape_landing_page(landing_url)
        if not html_content:
            return jsonify({"error": "Could not fetch landing page"}), 400

        # Step 3: Generate personalized copy
        changes = personalize_page(html_content, ad_analysis)

        # Step 4: Inject changes into HTML
        modified_html = inject_changes(html_content, changes, ad_analysis)

        return jsonify({
            "success": True,
            "ad_analysis": ad_analysis,
            "changes": changes,
            "modified_html": modified_html
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
