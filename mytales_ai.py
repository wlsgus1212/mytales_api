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
# 조사 자동 보정 (희진 → 희진이는)
# ────────────────────────────────────────────────
def with_particle(name: str) -> str:
    if not name:
        return name
    last_char = name[-1]
    code = ord(last_char) - 44032
    has_final = (code % 28) != 0  # 종성 여부
    return f"{name}은" if has_final else f"{name}는"


# ────────────────────────────────────────────────
# 2️⃣ /generate-story : 동화 + 삽화 프롬프트 생성
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

    name_particle = with_particle(name)  # "희진이는" 형태로 변환

    # 🧠 개선 프롬프트
    prompt = f"""
너는 감성적이고 상상력 풍부한 유아 동화 작가야.
다음 정보를 바탕으로 아이를 위한 따뜻하고 교훈적인 동화를 써줘.

- 주인공 이름: {name} ({name_particle})
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: '{goal}'

🪄 구성 지침:
1. 총 6개의 장면으로 구성된 완전한 이야기를 만들어줘.
2. 각 장면은 아이의 시선으로, 감정과 상상력이 풍부해야 해.
3. 매 장면은 3~4문장으로 자연스럽게 연결되게 써.
4. 마지막 장면에서는 주제의 교훈을 스스로 깨닫는 따뜻한 결말로 마무리해.

🎨 삽화 지침:
- 각 장면마다 "image_prompt"를 포함해야 해.
- 모든 장면의 {name}의 외형(머리색, 옷, 표정, 헤어스타일)은 동일해야 해.
- 따뜻한 색감, 유아 그림책 스타일, 부드러운 톤.
- image_prompt에는 배경, 인물 표정, 감정, 색감을 구체적으로 포함해.

📦 출력 형식(JSON 배열만):
[
  {{
    "paragraph": "첫 번째 장면 내용",
    "image_prompt": "첫 번째 장면의 삽화 설명"
  }},
  ...
  {{
    "paragraph": "여섯 번째 장면 내용",
    "image_prompt": "여섯 번째 장면의 삽화 설명"
  }}
]
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 아이의 언어로 따뜻하고 상상력 있는 이야기를 쓰는 작가야."},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.8,
            max_tokens=1600,
        )

        content = response.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()
        log.info("✅ GPT Response preview: %s", content[:250])

        story_data = json.loads(content)

        if isinstance(story_data, dict):
            story_data = [story_data]

        story = []
        for i, item in enumerate(story_data):
            paragraph = ""
            image_prompt = ""

            if isinstance(item, dict):
                paragraph = item.get("paragraph", "").strip()
                image_prompt = item.get("image_prompt", "").strip()
            elif isinstance(item, list) and len(item) >= 2:
                paragraph, image_prompt = item[0], item[1]
            else:
                paragraph = str(item)

            # 🧩 보정: 첫 장면 이미지 프롬프트 누락 시 문단 기반 생성
            if not image_prompt and paragraph:
                image_prompt = f"유아 그림책 스타일로, {name_particle}이 등장하는 장면. {paragraph[:40]}"

            story.append({
                "paragraph": paragraph or f"{i+1}번째 장면: 내용 누락",
                "image_prompt": image_prompt or f"{name_particle}이 등장하는 장면."
            })

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────────
# 3️⃣ /generate-image : DALL·E 3 삽화 생성
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        result = client.images.generate(
            model="dall-e-3",
            prompt=f"부드럽고 따뜻한 유아 그림책 스타일로: {prompt}",
            size="1024x1024",
            quality="standard"
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
# 4️⃣ 앱 실행
# ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
