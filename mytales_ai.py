# mytales_ai.py (v6-Lite)
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback, gc

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
# 2️⃣ 캐릭터 설명 (일관성 유지)
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
    return "✅ MyTales Flask API v6-Lite running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

# ─────────────────────────────
# 4️⃣ /generate-story
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

아이의 상상력을 자극하는 따뜻한 이야기를 써줘.
현실 → 마법의 세계 → 변화 → 귀환 구조로 구성하고, 총 5개의 장면만 사용해.

각 장면은 다음 형식으로:
{{
 "paragraph": "아이도 이해할 수 있는 3~4문장 동화 내용",
 "image_prompt": "그 장면을 그린 듯한 한글 삽화 설명. {MAIN_CHARACTER_DESC} 포함"
}}

조건:
- 쉬운 한글, 따뜻한 어조, 대화와 감정 묘사 중심
- 교훈은 직접 말하지 말고 행동으로 표현
- JSON 배열로만 출력
    """

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": "너는 창의적이고 따뜻한 유아 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.75,
            max_tokens=900
        )

        content = res.choices[0].message.content.strip()
        log.info("✅ GPT Response preview: %s", content[:200])
        del res  # 메모리 해제

        try:
            story = json.loads(content)
        except Exception:
            story = re.findall(r'"paragraph"\s*:\s*"([^"]+)"|"image_prompt"\s*:\s*"([^"]+)"', content)

        if not isinstance(story, list) or not story:
            return jsonify({"error": "동화 생성 실패"}), 500

        gc.collect()
        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Story generation error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────
# 5️⃣ /generate-image
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
            "부드러운 파스텔톤, 따뜻한 햇살, 감정이 잘 드러나는 표정, "
            "유아용 그림책 삽화 스타일로."
        )

        result = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024"
        )

        image_url = result.data[0].url if result.data else None
        del result
        gc.collect()

        if not image_url:
            return jsonify({"error": "No image generated"}), 500

        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("❌ Image generation error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────
# 6️⃣ 실행
# ─────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
