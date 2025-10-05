# mytales_ai.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback

# ────────────────────────────────────────────────
# 1️⃣ 환경 설정
# ────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ────────────────────────────────────────────────
# 2️⃣ 기본 라우트
# ────────────────────────────────────────────────
@app.get("/")
def root():
    return "✅ MyTales Flask API is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

# ────────────────────────────────────────────────
# 3️⃣ /generate-story : 동화 텍스트 생성
# ────────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = data.get("name", "").strip()
    age = data.get("age", "")
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    prompt = (
        f"아이의 이름은 {name}, 나이는 {age}세, 성별은 {gender}입니다. "
        f"부모가 훈육하고 싶은 주제는 '{goal}'입니다.\n\n"
        "이 아이에게 어울리는 맞춤형 동화를 작성해주세요. "
        "6개의 문단(장면)으로 구성하고, 각 문단은 3~4문장으로 만들어주세요. "
        "각 문단에는 삽화를 위한 구체적인 장면 묘사를 포함해주세요.\n\n"
        "JSON 배열 형식으로 출력하세요:\n"
        "[\"첫 번째 문단\", \"두 번째 문단\", ..., \"여섯 번째 문단\"]"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 유아 맞춤 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        content = response.choices[0].message.content.strip()
        log.info("✅ GPT Response: %s", content[:200])

        try:
            paragraphs = json.loads(content)
        except Exception:
            paragraphs = re.findall(r'"(.*?)"', content)

        if not isinstance(paragraphs, list):
            paragraphs = [content]

        paragraphs = [p.replace("??", name) for p in paragraphs]

        return jsonify({"texts": paragraphs}), 200

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ────────────────────────────────────────────────
# 4️⃣ /generate-image : 단일 이미지 생성 (경량화)
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        result = client.images.generate(
            model="dall-e-2",        # ⬅️ 경량 모델 사용
            prompt=prompt,
            size="512x512"           # ⬅️ 메모리 절약
        )

        log.info("📦 Raw image result: %s", result)

        image_url = result.data[0].url if result.data else None

        if not image_url:
            return jsonify({"error": "No image returned by OpenAI"}), 500

        log.info("🖼️ Image generated successfully")
        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("❌ Error generating image: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ────────────────────────────────────────────────
# 5️⃣ 앱 실행 (Render 자동 포트 인식)
# ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
