# mytales_ai.py
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback

# ─────────────────────────────
# 1️⃣ 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ─────────────────────────────
# 2️⃣ 주인공 외형 고정 설명
# ─────────────────────────────
MAIN_CHARACTER_DESC = (
    "7살 여자아이 ‘수정’. 짧은 갈색 머리에 노란 원피스를 입고, "
    "밝고 호기심 많은 표정을 짓고 있는 모습."
)

# ─────────────────────────────
# 3️⃣ 기본 라우트
# ─────────────────────────────
@app.get("/")
def root():
    return "✅ MyTales Flask API v6 is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

# ─────────────────────────────
# 4️⃣ /generate-story : 동화 생성
# ─────────────────────────────
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

    prompt = f"""
너는 5~8세 어린이를 위한 전문 동화 작가이자 그림책 기획가야.

아이의 이름은 '{name}', 나이는 {age}세, 성별은 {gender}야.
부모가 전달하고 싶은 교훈 주제는 '{goal}'이야.

이 정보를 바탕으로, 아이가 몰입하고 상상할 수 있는 따뜻한 이야기를 만들어줘.
단순한 일상 이야기가 아니라, 주인공이 특별한 모험이나 마법 같은 경험을 통해
스스로 깨닫게 되는 이야기여야 해.

다음 조건을 지켜서 써줘:

1️⃣ 전체 이야기는 6개의 장면으로 구성돼.
   - 첫 장면은 현실, 두 번째~다섯 번째는 상상의 세계, 여섯 번째는 현실로 돌아오는 구조.
   - 각 문단은 3~4문장, 자연스럽게 이어지게 써.

2️⃣ "paragraph" 부분:
   - 쉬운 한글로 감정, 행동, 대화를 풍부하게 써.
   - 유치원~초등 저학년 수준 단어만 사용.
   - ‘손해’, ‘결심’ 같은 추상어 대신 구체적인 행동으로 표현.
   - 교훈은 직접 말하지 말고 주인공의 행동으로 보여줘.

3️⃣ "image_prompt" 부분:
   - 해당 문단의 삽화를 한글로 1~2문장으로 설명해.
   - 주인공의 외형은 항상 같아야 해:
     “{MAIN_CHARACTER_DESC}”
   - 장면의 배경, 색감, 분위기를 구체적으로 묘사해.
   - “...하는 장면.” 으로 끝내.

4️⃣ '{goal}' 주제가 직접 등장하지 않게, 이야기 속 상황으로 자연스럽게 표현해.

💡 출력은 반드시 JSON 배열 형식으로 해:
[
  {{
    "paragraph": "첫 번째 장면 내용",
    "image_prompt": "첫 번째 삽화 설명"
  }},
  ...
]
    """

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 창의적이고 따뜻한 유아 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1500,
        )

        content = res.choices[0].message.content.strip()
        log.info("✅ GPT Response (preview): %s", content[:300])

        try:
            story = json.loads(content)
        except Exception:
            story = re.findall(r'"paragraph"\s*:\s*"([^"]+)"|"image_prompt"\s*:\s*"([^"]+)"', content)

        if not isinstance(story, list) or not story:
            return jsonify({"error": "동화 생성 실패"}), 500

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Story generation error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────
# 5️⃣ /generate-image : 삽화 생성
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()

        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        full_prompt = (
            f"{MAIN_CHARACTER_DESC}\n"
            f"{text_prompt}\n"
            "항상 같은 주인공으로 그려줘. "
            "부드러운 파스텔톤, 따뜻한 햇살, 풍부한 감정 표현, "
            "유아용 그림책 스타일로."
        )

        result = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image generated"}), 500

        return jsonify({"image_url": image_url, "used_prompt": text_prompt}), 200

    except Exception as e:
        log.error("❌ Image generation error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────
# 6️⃣ 실행
# ─────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
