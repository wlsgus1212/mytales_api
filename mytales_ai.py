from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, re, random, logging, json

# ─────────────────────────────────────────────
# 1. 기본 설정
# ─────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────
# 2. 캐릭터 프로필 생성
# ─────────────────────────────────────────────
def generate_character_profile(name, age, gender):
    hair_options = ["짧은 갈색 곱슬머리", "긴 생머리 검은 머리", "웨이비한 밤색 머리"]
    outfit_options = ["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"]
    hair = random.choice(hair_options)
    outfit = random.choice(outfit_options)

    return {
        "name_en": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "face": "부드러운 볼의 둥근 얼굴",
            "eyes": "따뜻한 갈색 아몬드형 눈",
            "hair": hair,
            "outfit": outfit,
            "proportions": "아이 같은 비율"
        }
    }

# ─────────────────────────────────────────────
# 3. 장면 묘사 생성 (GPT-4o)
# ─────────────────────────────────────────────
def describe_scene(paragraph, character_profile, context=""):
    name = character_profile.get("name_en", "아이")
    age = character_profile.get("age", "7")
    gender = character_profile.get("gender", "아이")
    style = character_profile.get("style", "")

    prompt = f"""
당신은 '훈육 동화봇'을 위한 그림책 일러스트레이터입니다.
주어진 이야기 문장을 바탕으로 시각적 장면을 한 문장으로 묘사해주세요.

[이야기 흐름]: {context}
[이번 문장]: "{paragraph}"
[캐릭터 외형]: {age}살 {gender} {name}, 복장과 머리: {style}

🧾 조건:
- 감정, 동작, 배경을 모두 포함
- 수채화 일러스트처럼 부드럽고 아동 친화적인 묘사
- 텍스트나 말풍선 절대 포함하지 말 것
- 같은 캐릭터 스타일을 유지할 것
    """.strip()

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You write concise Korean image descriptions for watercolor children's picture books."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4,
        max_tokens=200
    )

    return re.sub(r"[\"<>]", "", res.choices[0].message.content.strip())

# ─────────────────────────────────────────────
# 4. 이미지 생성용 프롬프트 생성
# ─────────────────────────────────────────────
def build_image_prompt(scene_description, character_profile):
    v = character_profile.get("visual", {})
    name = character_profile.get("name_en", "아이")
    return (
        f"장면 묘사: {scene_description}. "
        f"주인공: {character_profile['age']}살 {character_profile['gender']} {name}, 외형: {v.get('face')}, "
        f"{v.get('hair')}, {v.get('eyes')}, 복장: {v.get('outfit')}, 비율: {v.get('proportions')}. "
        f"부드러운 수채화 스타일, 아동 친화적, 따뜻한 조명, 동일한 외형 유지, 텍스트와 말풍선은 포함하지 마세요."
    ).strip()

# ─────────────────────────────────────────────
# 5. 동화 생성 (/generate-story)
# ─────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    character_profile = generate_character_profile(name, age, gender)

    prompt = f"""
당신은 '훈육 동화봇'이라는 이야기 마법사입니다.

입력:
- 이름: {name}, 나이: {age}세, 성별: {gender}
- 훈육 주제: {goal}

아래 구조로 JSON 형식 동화를 만들어주세요:

{{
  "title": "동화 제목",
  "character": {{
    "name": "{name}",
    "age": "{age}",
    "gender": "{gender}",
    "style": "머리와 복장 설명"
  }},
  "chapters": [
    {{
      "title": "1장 제목",
      "paragraph": "이 장면의 이야기 (2~4 문장)",
      "illustration": "삽화 묘사 (1 문장)"
    }},
    ...
  ]
}}

조건:
- 총 5장
- 문장은 짧고 간결하며 반복과 감정 중심
- 아이가 공감하고 배울 수 있도록
- 장난감, 동물, 상상 요소 자유롭게 사용
    """.strip()

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "너는 어린이를 위한 따뜻한 훈육 동화를 쓰는 이야기 마법사야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1800
        )
        raw = res.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        story_data = json.loads(raw)
    except Exception as e:
        logging.error("❌ GPT 응답 파싱 실패: %s", str(e))
        return jsonify({"error": "동화 생성 실패", "details": str(e)}), 500

    # 이미지 프롬프트 생성
    image_descriptions = []
    image_prompts = []
    context = ""

    for ch in story_data["chapters"]:
        desc = describe_scene(ch["paragraph"], character_profile, context)
        image_descriptions.append(desc)
        image_prompts.append(build_image_prompt(desc, character_profile))
        context += ch["paragraph"] + " "

    return jsonify({
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story": [c["paragraph"] for c in story_data["chapters"]],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts
    })

# ─────────────────────────────────────────────
# 6. 이미지 생성 (/generate-image)
# ─────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        image_url = res.data[0].url
        return jsonify({"image_url": image_url, "used_prompt": prompt})
    except Exception as e:
        logging.error("❌ 이미지 생성 실패: %s", str(e))
        return jsonify({"error": "이미지 생성 실패"}), 500

# ─────────────────────────────────────────────
# 7. 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
