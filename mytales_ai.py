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

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ───────────────────────────────
@app.get("/")
def root():
    return "✅ MyTales Flask API is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

# ───────────────────────────────
# 3️⃣ 동화 텍스트 (아동용 + 캐릭터 일관성 강화)
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
        f"너는 5~8세 어린이를 위한 전문 동화 작가야.\n"
        f"주인공의 이름은 '{name}', 나이는 {age}세, 성별은 {gender}야.\n"
        f"부모가 전달하고 싶은 교훈 주제는 '{goal}'이야.\n\n"
        "이 설정으로 아이가 쉽게 이해하고 공감할 수 있는 따뜻한 동화를 써줘.\n"
        "전체 이야기는 6개의 장면으로 구성하고, 한 인물과 세계관이 일관되게 유지되어야 해.\n"
        "모든 문단에서 주인공의 외형, 표정, 주변 환경, 행동이 자연스럽게 이어지도록 만들어.\n\n"
        "💡 문체 지침:\n"
        "- 유치원~초등 1학년 수준 어휘만 사용\n"
        "- 추상어나 어려운 단어(예: 손해, 인내심, 감정, 책임 등)는 금지\n"
        "- 교훈은 이야기 안에서 자연스럽게 드러나야 하며, 직접적으로 설명하지 말 것\n"
        "- 각 장면마다 감정을 '표정, 행동, 상황'으로 보여줘\n"
        "- 이야기는 따뜻하고 희망찬 결말로 마무리해\n\n"
        "💡 출력 형식:\n"
        "JSON 배열 형태로 출력해. 각 원소는 다음 구조를 따라야 해.\n"
        "[\n"
        "  {\"paragraph\": \"첫 번째 문단 내용\", \"image_prompt\": \"그 장면을 영어로 짧게 묘사 (same main character, continuous scene)\"},\n"
        "  {\"paragraph\": \"두 번째 문단 내용\", \"image_prompt\": \"...\"}, ...\n"
        "]"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 따뜻하고 일관된 세계관을 가진 유아 동화 작가야."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()
        log.info("✅ Story generated: %s", content[:300])

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
        log.error("❌ Story Error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ───────────────────────────────
# 4️⃣ 삽화 (DALL·E-3 + 캐릭터 유지)
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()
        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        # GPT로 영어 장면 설명 생성
        prompt_for_gpt = (
            "You are an illustrator for a children's picture book.\n"
            "Convert the following Korean paragraph into a short English scene description "
            "that continues the same main character and setting consistently.\n"
            "Keep the same child (same hair, clothes, face), environment, and mood as previous scenes.\n"
            "Use warm, soft pastel colors, emotional lighting, and cute expressions.\n"
            "Output only one English sentence.\n\n"
            f"Paragraph:\n{text_prompt}"
        )

        gpt_scene = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create consistent illustration prompts for children's stories."},
                {"role": "user", "content": prompt_for_gpt},
            ],
            temperature=0.6,
            max_tokens=120,
        )

        refined_prompt = gpt_scene.choices[0].message.content.strip()
        log.info("🖋️ DALL-E Prompt: %s", refined_prompt)

        # DALL·E-3 생성
        full_prompt = (
            f"{refined_prompt}. "
            "Same main character, consistent environment, children's storybook illustration, "
            "soft pastel tones, warm lighting, detailed expressions, 4k quality."
        )

        result = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image returned"}), 500

        return jsonify({"image_url": image_url, "used_prompt": refined_prompt}), 200

    except Exception as e:
        log.error("❌ Image Error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
