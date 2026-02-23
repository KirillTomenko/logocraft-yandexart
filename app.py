import requests
import base64
import time
import os
import uuid
from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

GENERATED_DIR = os.path.join(os.path.dirname(__file__), 'static', 'generated')
os.makedirs(GENERATED_DIR, exist_ok=True)

YANDEX_CLOUD_ID = os.getenv('YANDEX_CLOUD_ID')
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')

# ──────────────────────────────────────────────
# Стили логотипов — актуальные тренды 2024-2025
# Промпты оптимизированы под YandexART 2.0
# ──────────────────────────────────────────────
STYLES = {
    "minimalist": {
        "label": "Минимализм",
        "emoji": "◻",
        "suffix": (
            "minimalist logo design, clean vector style, flat design, "
            "simple geometric shapes, white background, professional branding, "
            "negative space composition, single color palette"
        )
    },
    "3d_render": {
        "label": "3D / Объёмный",
        "emoji": "◈",
        "suffix": (
            "3D rendered logo, glossy material, soft shadows, "
            "depth and volume, studio lighting, modern product design, "
            "white background, hyperrealistic render"
        )
    },
    "gradient": {
        "label": "Градиент",
        "emoji": "◑",
        "suffix": (
            "gradient logo design, vibrant color gradient, glassmorphism style, "
            "smooth color transitions, modern ui design, "
            "luminous glow effect, clean vector shapes"
        )
    },
    "neon_cyber": {
        "label": "Неон / Кибер",
        "emoji": "◉",
        "suffix": (
            "neon logo design, cyberpunk aesthetic, glowing neon lights, "
            "dark background, electric colors, futuristic tech brand, "
            "luminous outline effect, synthwave style"
        )
    },
    "geometric": {
        "label": "Геометрия",
        "emoji": "△",
        "suffix": (
            "geometric logo design, abstract geometric shapes, "
            "symmetrical composition, bold lines and angles, "
            "modern abstract art, vector illustration, "
            "limited color palette, optical illusion"
        )
    },
    "handcraft": {
        "label": "Леттеринг",
        "emoji": "✦",
        "suffix": (
            "hand-lettered logo design, custom typography, "
            "calligraphy style, artisan branding, "
            "vintage-modern fusion, warm tones, "
            "detailed ornamental elements"
        )
    },
    "illustration": {
        "label": "Иллюстрация",
        "emoji": "⬡",
        "suffix": (
            "illustrated logo design, detailed vector illustration, "
            "character mascot style, vibrant colors, "
            "playful and friendly brand, flat illustration, "
            "sticker-like design, white background"
        )
    },
    "retro_badge": {
        "label": "Ретро / Бейдж",
        "emoji": "⬟",
        "suffix": (
            "retro badge logo design, vintage emblem style, "
            "distressed texture, shield or circle badge frame, "
            "classic americana aesthetic, aged colors, "
            "detailed ornamental border, old school branding"
        )
    },
}


def build_prompt(brand_name: str, description: str, style_key: str) -> str:
    style = STYLES.get(style_key, STYLES["minimalist"])
    parts = []
    if brand_name:
        parts.append(f'logo for brand "{brand_name}"')
    if description:
        parts.append(description)
    parts.append(style["suffix"])
    return ", ".join(parts)


def generate_logo(prompt_text: str, seed, width_ratio: str, height_ratio: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-key {YANDEX_API_KEY}"
    }

    payload = {
        "modelUri": f"art://{YANDEX_CLOUD_ID}/yandex-art/latest",
        "generationOptions": {
            "aspectRatio": {
                "widthRatio": width_ratio,
                "heightRatio": height_ratio
            }
        },
        "messages": [
            {
                "weight": "1",
                "text": prompt_text
            }
        ]
    }

    if seed is not None:
        payload["generationOptions"]["seed"] = seed

    create_resp = requests.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync",
        headers=headers,
        json=payload,
        timeout=30
    )
    create_resp.raise_for_status()
    operation_id = create_resp.json()["id"]

    for _ in range(60):
        time.sleep(5)
        poll = requests.get(
            f"https://llm.api.cloud.yandex.net/operations/{operation_id}",
            headers=headers,
            timeout=30
        )
        poll.raise_for_status()
        data = poll.json()

        if data.get("done"):
            filename = f"{uuid.uuid4().hex}.jpeg"
            filepath = os.path.join(GENERATED_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(data["response"]["image"]))
            return {"success": True, "filename": filename}

    return {"success": False, "error": "Timeout: превышено время ожидания."}


@app.route("/")
def index():
    return render_template("index.html", styles=STYLES)


@app.route("/generate", methods=["POST"])
def generate():
    if not YANDEX_CLOUD_ID or not YANDEX_API_KEY:
        return jsonify({"success": False, "error": "Не заданы API-ключи. Проверьте файл .env"}), 500

    data = request.get_json()
    brand_name  = (data.get("brand_name") or "").strip()
    description = (data.get("description") or "").strip()
    style_key   = data.get("style", "minimalist")
    ratio       = data.get("ratio", "1:1")
    seed_raw    = data.get("seed")

    if not brand_name and not description:
        return jsonify({"success": False, "error": "Введите название бренда или описание."}), 400

    seed = int(seed_raw) if seed_raw not in (None, "", 0) else None

    ratio_map = {
        "1:1":  ("1", "1"),
        "4:3":  ("4", "3"),
        "3:4":  ("3", "4"),
        "16:9": ("16", "9"),
    }
    w, h = ratio_map.get(ratio, ("1", "1"))

    prompt = build_prompt(brand_name, description, style_key)

    try:
        result = generate_logo(prompt, seed, w, h)
        result["prompt_used"] = prompt
    except requests.HTTPError as e:
        return jsonify({"success": False, "error": f"Ошибка Yandex API: {e.response.text}"}), 502
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify(result)


@app.route("/static/generated/<filename>")
def serve_image(filename):
    return send_from_directory(GENERATED_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
