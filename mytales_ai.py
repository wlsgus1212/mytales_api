# mytales_ai.py
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, logging, traceback, re

# ────────────────────────────────────────────────
# 1️⃣ 환경 설정
# ────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=API_KEY)

# 🔹 Flask 인스턴스 생성 (⚠️ 반드시 라우트보다 위에 있어야 함)
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
# 3️⃣ /generate-story : 동화 + 삽화 설명 생성
# ────────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    """유아용 동화 문단과 각 문단에 맞는 삽화 설명을 생성"""
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

    # 🧠 통합 프롬프트: 동화 + 삽화 설명 동시 생성
    prompt = (
        f"너는 5~8세 아이를 위한 전문 동화 작가이자 삽화 연출가야.\n"
        f"아이 이름은 '{name}', 나이는 {age}세, 성별은 {gender}야.\n"
        f"훈육 주제는 '{goal}'이야.\n\n"
        "아이에게 교훈이 자연스럽게 전달되는 6문단짜리 유아용 동화를 써줘.\n"
        "각 문단은 3~4문장으로 구성하고, 이야기가 자연스럽게 이어지도록 해.\n"
        "각 문단에는 따뜻하고 구체적인 장면 묘사를 포함시켜.\n"
        "또한 각 문단 옆에 그 문단을 그림으로 표현하기 좋은 삽화 설명도 함께 만들어줘.\n\n"
        "출력은 반드시 JSON 형식으로 아래 예시처럼 만들어:\n"
        "[\n"
        " {\"paragraph\": \"첫 번째 문단 내용\", \"image_prompt\": \"첫 번째 문단에 어울리는 그림 설명\"},\n"
        " {\"paragraph\": \"두 번째 문단 내용\", \"image_prompt\": \"두 번째 문단에 어울리는 그림 설명\"},\n"
        " ...\n"
        "]"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 감성적이고 상상력 풍부한 유아 동화 작가이자 삽화 연출가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.75,
            max_tokens=1500
        )

        content = res.choices[0].message.content.strip()
        log.info("✅ GPT Response (preview): %s", content[:250])

        try:
            story = json.loads(content)
        except Exception:
            # JSON 형식이 아닐 경우 수동 파싱 시도
            story = re.findall(r'"paragraph":\s*"([^"]+)"|"image_prompt":\s*"([^"]+)"', content)
            story = [{"paragraph": p, "image_prompt": i} for p, i in story if p or i]

        if not isinstance(story, list) or not story:
            return jsonify({"error": "Invalid story format"}), 500

        # 이름 대입 및 공백 제거
        for s in story:
            s["paragraph"] = s.get("paragraph", "").replace("??", name).strip()
            s["image_prompt"] = s.get("image_prompt", "").strip()

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ────────────────────────────────────────────────
# 4️⃣ /generate-image : 삽화 이미지 생성
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    """삽화 프롬프트 기반 이미지 생성"""
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()

        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 🎨 삽화 스타일 프롬프트
        full_prompt = (
            f"유아용 동화 삽화 스타일로, {text_prompt} "
            "따뜻한 파스텔톤과 부드러운 그림체, 귀여운 인물, 감정이 담긴 장면으로 표현해줘."
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
