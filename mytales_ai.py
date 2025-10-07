from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback

# ───────────────────────────────
# 1️⃣ 환경 설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)

# ✅ Flask 인스턴스는 반드시 라우트보다 위에 있어야 함
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ───────────────────────────────
# 2️⃣ 헬스체크
# ───────────────────────────────
@app.get("/")
def root():
    return "✅ MyTales Flask API is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

# ───────────────────────────────
# 3️⃣ 동화 텍스트 생성
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    prompt = (
        f"너는 5~8세 아동을 위한 전문 동화 작가야.\n"
        f"아이 이름은 '{name}', 나이는 {age}세, 성별은 {gender}.\n"
        f"훈육 주제는 '{goal}'이야.\n"
        "이 정보를 바탕으로 6개의 문단으로 된 유아용 동화를 써줘.\n"
        "각 문단은 3~4문장으로, 장면 묘사를 포함하고 감정이 풍부해야 해.\n"
        "각 문단은 JSON 배열로 출력하고, 각 항목은 다음 구조를 따르도록:\n"
        "[{\"paragraph\": \"문단 내용\", \"image_prompt\": \"해당 문단의 장면을 요약한 삽화 묘사\"}, ...]"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 따뜻하고 상상력 풍부한 유아 동화 작가야."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1200,
        )

        content = response.choices[0].message.content.strip()
        log.info("✅ GPT Response (preview): %s", content[:300])

        try:
            story = json.loads(content)
        except Exception:
            story = re.findall(r'\{.*?\}', content, re.S)
            story = [json.loads(x) for x in story] if story else [{"paragraph": content, "image_prompt": content}]

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 4️⃣ 삽화 생성
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()
        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 🎨 1단계: GPT로 그림용 프롬프트 정제
        scene_prompt_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 유아용 그림책 삽화 디자이너야. "
                        "아래 문단을 읽고, 장면을 따뜻하게 묘사하는 한 줄 프롬프트를 만들어. "
                        "아이의 표정, 배경, 분위기를 포함하되, 금속·조각상·패턴은 절대 금지."
                    ),
                },
                {"role": "user", "content": text_prompt},
            ],
            temperature=0.7,
            max_tokens=150,
        )

        refined_prompt = scene_prompt_res.choices[0].message.content.strip()

        # 🎨 2단계: 이미지 생성
        full_prompt = (
            f"유아용 동화책 삽화 스타일로, 밝고 부드러운 파스텔톤으로 그려줘. {refined_prompt} "
            "귀엽고 따뜻한 인물, 자연 배경, 감정이 느껴지는 장면 중심."
        )

        result = client.images.generate(
            model="dall-e-2",
            prompt=full_prompt,
            size="512x512"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image returned"}), 500

        log.info("🖼️ Generated Image Prompt: %s", refined_prompt)
        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("❌ Error generating image: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 5️⃣ 앱 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
