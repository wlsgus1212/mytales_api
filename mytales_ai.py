# mytales_ai.py
from flask import Flask, request, jsonify, Response
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

    # 🧠 개선된 프롬프트
    prompt = (
        f"너는 5~8세 아동을 위한 전문 동화 작가야.\n"
        f"아이의 이름은 '{name}', 나이는 {age}세, 성별은 {gender}야.\n"
        f"부모가 아이에게 가르치고 싶은 훈육 주제는 '{goal}'이야.\n\n"
        "이 정보를 바탕으로, 아이가 공감하고 배울 수 있는 따뜻하고 교훈적인 유아용 동화를 써줘.\n"
        "전체 이야기는 6개의 문단(장면)으로 구성해.\n"
        "각 문단은 3~4문장으로 작성하고, 이야기가 자연스럽게 이어지도록 해.\n"
        "각 문단에는 삽화를 그리기 좋은 장면 묘사를 반드시 포함해.\n"
        "예를 들어 주변 배경, 등장인물의 표정, 행동, 색감 등을 구체적으로 표현해.\n"
        "문체는 부드럽고 감정이 풍부하며, 아이의 시선에서 따뜻하게 써.\n"
        "마지막 문단에는 주제(교훈)가 자연스럽게 드러나게 마무리해.\n\n"
        "출력은 반드시 JSON 배열 형식으로 해.\n"
        "예시: [\"첫 번째 문단 내용\", \"두 번째 문단 내용\", ..., \"여섯 번째 문단 내용\"]"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 감성적이고 상상력 풍부한 유아 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.75,
            max_tokens=1000
        )

        content = response.choices[0].message.content.strip()
        log.info("✅ GPT Response (preview): %s", content[:250])

        try:
            paragraphs = json.loads(content)
        except Exception:
            paragraphs = re.findall(r'"(.*?)"', content)

        if not isinstance(paragraphs, list):
            paragraphs = [content]

        paragraphs = [p.replace("??", name).strip() for p in paragraphs if p.strip()]

        # ensure_ascii=False → 한글 깨짐 방지
        return Response(
            json.dumps({"texts": paragraphs}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ────────────────────────────────────────────────
# 4️⃣ /generate-image : 단일 이미지 생성 (삽화 프롬프트 개선)
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()

        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 🎨 삽화 프롬프트 보정
        full_prompt = (
            f"유아용 동화 삽화 스타일로, 다음 장면을 따뜻하고 밝은 색감으로 그려줘: {text_prompt}. "
            "부드러운 파스텔톤, 따뜻한 표정, 자연스러운 배경, 귀여운 인물 스타일로 묘사해."
        )

        result = client.images.generate(
            model="dall-e-2",
            prompt=full_prompt,
            size="512x512"
        )

        image_url = result.data[0].url if result.data else None

        if not image_url:
            return jsonify({"error": "No image returned by OpenAI"}), 500

        log.info("🖼️ Image generated successfully: %s", image_url)
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
