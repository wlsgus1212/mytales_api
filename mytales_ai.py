from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, json, time

# ───── 환경 설정 ─────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found.")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)

# ───── 유틸 함수 ─────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face with soft cheeks; warm brown almond eyes; childlike proportions."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit,
            "face": "부드러운 볼의 둥근 얼굴",
            "eyes": "따뜻한 갈색 아몬드형 눈",
            "proportions": "아이 같은 비율"
        }
    }

# ───── 스토리 생성 ─────
def generate_story_text(name, age, gender, topic):
    prompt = f"""
당신은 5~9세 어린이를 위한 따뜻하고 리드미컬한 동화 작가입니다.

반드시 아래 JSON 형식만 응답하세요:

{{
  "title": "",
  "character": "",
  "chapters": [
    {{
      "title": "",
      "paragraphs": ["", ""],
      "illustration": ""
    }}
  ],
  "ending": ""
}}

요구사항:
- 이름: {name}, 나이: {age}, 성별: {gender}, 훈육주제: {topic}
- 총 5개 챕터
- 각 챕터는 "paragraphs" 리스트 형태로 2~4문장 나눠서 작성
- 각 챕터는 "title", "paragraphs", "illustration" 포함
- 마지막에 "ending" 추가
- 반드시 위 JSON 구조만 반환. 다른 텍스트나 설명 포함 금지.
""".strip()

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Respond only with valid JSON for a children's picture book."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
        max_tokens=1500,
    )

    raw = res.choices[0].message.content.strip()
    cleaned = re.sub(r'```(?:json)?', '', raw).strip()
    try:
        return json.loads(cleaned)
    except:
        m = re.search(r'(\{[\s\S]+\})', cleaned)
        return json.loads(m.group(1)) if m else {}

# ───── API 엔드포인트 ─────
@app.route("/generate-full", methods=["POST"])
def generate_full():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("topic", data.get("education_goal", "")).strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "입력 누락"}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)

    return jsonify({
        "title": story.get("title"),
        "character_profile": character,
        "chapters": story.get("chapters", []),
        "ending": story.get("ending", "")
    })

# ───── 실행 ─────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
