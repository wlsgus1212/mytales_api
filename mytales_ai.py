from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, logging, traceback

# ─────────────────────────────────────────────────────
# 환경 설정
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ─────────────────────────────────────────────────────
@app.get("/")
def root():
    return "MyTales Flask API is running."

# ─────────────────────────────────────────────────────
# [1] 무료 동화 텍스트 생성 (6문단)
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        age = data.get("age", "")
        gender = data.get("gender", "")
        goal = data.get("education_goal", "")

        if not all([name, age, gender, goal]):
            return jsonify({"error": "모든 항목을 입력해주세요."}), 400

        prompt = f"""
        아동 이름={name}, 나이={age}세, 성별={gender}.
        훈육 주제="{goal}"에 맞는 맞춤형 동화를 만들어 주세요.
        총 6개의 문단으로 구성하되, 각 문단은 3~4문장으로 작성하고
        각 문단마다 삽화를 만들 수 있도록 구체적인 장면 묘사를 포함하세요.
        반드시 JSON 배열 형식으로 출력하세요:
        [
          "문단1", "문단2", ..., "문단6"
        ]
        """

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 유아 맞춤 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        content = resp.choices[0].message.content.strip()
        try:
            story_paragraphs = json.loads(content)
        except:
            story_paragraphs = json.loads(content.split("```")[-2])

        if not isinstance(story_paragraphs, list):
            raise ValueError("GPT output is not a JSON list.")

        return jsonify({"texts": story_paragraphs}), 200

    except Exception as e:
        log.error("Error in /generate-story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────────────
# [2] 이미지 한 장씩 생성
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "prompt가 비어 있습니다."}), 400

        img = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024"
        )

        image_url = img.data[0].url
        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("Error in /generate-image: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
