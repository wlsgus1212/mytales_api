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
# 3️⃣ /generate-story : 동화 + 이미지 프롬프트 생성
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

    # 🧠 개선된 프롬프트 (일관된 캐릭터 + 창의성 강조)
    prompt = f"""
너는 감성적이고 상상력 풍부한 유아 동화 작가야.
아래 정보를 바탕으로 5~8세 어린이를 위한 따뜻하고 교훈적인 동화를 만들어줘.

- 아이 이름: {name}
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: '{goal}'

🪄 스토리 구성 지침:
1. 총 6개의 장면으로 구성된 이야기로 써줘.
2. 각 장면은 아이의 시선에서 흥미롭게 전개되어야 하며, 마법이나 상상력을 활용해도 좋아.
3. 매 장면은 3~4문장으로, 감정 변화와 교훈적 흐름이 자연스럽게 이어지게 해줘.
4. 마지막 장면에서는 아이가 스스로 배운 점을 깨닫는 따뜻한 결말로 마무리해.

🎨 삽화 지침:
- 각 장면에는 삽화를 위한 프롬프트도 함께 작성해줘.
- 모든 장면의 주인공 {name}의 외형(머리색, 옷 색상, 표정 등)은 항상 일관되게 유지해줘.
- 밝고 부드러운 색감, 유아용 그림책 스타일로 묘사하도록.
- 이미지 프롬프트에는 감정 표현(기쁨, 놀람, 용기 등)과 배경 환경(정원, 하늘, 식탁 등)을 포함해줘.

📦 출력 형식 (JSON 배열로만):
[
  {{
    "paragraph": "첫 번째 장면 내용",
    "image_prompt": "첫 번째 장면의 삽화 설명"
  }},
  {{
    "paragraph": "두 번째 장면 내용",
    "image_prompt": "두 번째 장면의 삽화 설명"
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
            model="gpt-4o-mini",  # gpt-4o-mini는 텍스트+프롬프트 생성에 충분
            messages=[
                {"role": "system", "content": "너는 감정 표현이 풍부하고 일관된 캐릭터를 그릴 줄 아는 동화 작가야."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.8,
            max_tokens=1600
        )

        content = response.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()

        log.info("✅ GPT Response preview: %s", content[:300])

        # JSON 파싱
        story_data = json.loads(content)

        # 보정: 배열이 아닌 경우 단일 객체라도 리스트로 감싸기
        if isinstance(story_data, dict):
            story_data = [story_data]

        # 구조 보정: paragraph 또는 image_prompt 누락 방지
        story = []
        for i, item in enumerate(story_data):
            if isinstance(item, dict):
                paragraph = item.get("paragraph", "").strip()
                image_prompt = item.get("image_prompt", "").strip()
                story.append({
                    "paragraph": paragraph or f"{i+1}번째 장면: 내용이 누락되었습니다.",
                    "image_prompt": image_prompt or f"{name}이(가) 등장하는 장면의 삽화."
                })
            elif isinstance(item, list) and len(item) >= 2:
                story.append({"paragraph": item[0], "image_prompt": item[1]})
            else:
                story.append({"paragraph": str(item), "image_prompt": f"{name}이(가) 나오는 장면 묘사."})

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────────
# 4️⃣ /generate-image : 삽화 생성
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 🖼️ DALL·E 3은 한글 프롬프트도 완벽 지원
        result = client.images.generate(
            model="dall-e-3",
            prompt=f"유아 그림책 스타일로 따뜻하고 부드러운 색감의 장면: {prompt}",
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
# 5️⃣ 앱 실행 (Render 자동 포트 인식)
# ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
