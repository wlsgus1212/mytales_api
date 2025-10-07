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

# ✅ Flask 인스턴스
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
# 3️⃣ 동화 텍스트 생성 (한글)
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
        f"아이의 이름은 '{name}', 나이는 {age}세, 성별은 {gender}야.\n"
        f"부모가 아이에게 가르치고 싶은 훈육 주제는 '{goal}'이야.\n\n"
        "이 정보를 바탕으로 아이가 공감하고 배울 수 있는 따뜻하고 교훈적인 유아용 동화를 써줘.\n"
        "전체 이야기는 6개의 문단(장면)으로 구성해.\n"
        "각 문단은 3~4문장으로 작성하고, 이야기가 자연스럽게 이어지도록 해.\n"
        "각 문단에는 삽화를 그리기 좋은 장면 묘사를 포함해.\n"
        "문체는 부드럽고 감정이 풍부하며, 아이의 시선에서 따뜻하게 써.\n"
        "마지막 문단에는 주제(교훈)가 자연스럽게 드러나게 마무리해.\n\n"
        "출력은 반드시 JSON 배열 형식으로 해.\n"
        "예시:\n"
        "[{\"paragraph\": \"첫 번째 문단 내용\", \"image_prompt\": \"해당 문단 삽화 설명\"}, ...]"
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
        log.info("✅ GPT Story Response (preview): %s", content[:300])

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
# 4️⃣ 삽화 생성 (영문 프롬프트 변환 → DALL·E-2)
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()
        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 🎨 GPT: 한국어 문단 → 영어 삽화 프롬프트 변환
        prompt_for_gpt = (
            "You are a professional children's storybook illustrator.\n"
            "Read the following Korean paragraph carefully and write ONE short English sentence "
            "that describes the scene vividly for DALL·E.\n"
            "Include: the child’s name and age, the setting, main action, facial expression, "
            "emotion, and color tone.\n"
            "Use a gentle, warm, pastel storybook style. "
            "Avoid realism, metal, statues, logos, or text.\n"
            "Output only one English sentence.\n\n"
            f"Paragraph:\n{text_prompt}"
        )

        gpt_scene = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You convert Korean story text into vivid English illustration prompts."},
                {"role": "user", "content": prompt_for_gpt}
            ],
            temperature=0.6,
            max_tokens=120
        )

        refined_prompt = gpt_scene.choices[0].message.content.strip()
        log.info("🖋️ English scene prompt for DALL·E: %s", refined_prompt)

        # 🎨 DALL·E-2로 이미지 생성
        full_prompt = (
            f"{refined_prompt}. "
            "Children’s storybook illustration, soft pastel colors, warm lighting, cute expressive characters."
        )

        result = client.images.generate(
            model="dall-e-2",
            prompt=full_prompt,
            size="512x512"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image returned"}), 500

        return jsonify({"image_url": image_url, "used_prompt": refined_prompt}), 200

    except Exception as e:
        log.error("❌ Error generating image: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 5️⃣ 앱 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
