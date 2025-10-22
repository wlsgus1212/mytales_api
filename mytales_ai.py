from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

# ─────────────────────────────────────
# 환경 변수 및 기본 세팅
# ─────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return response

# ─────────────────────────────────────
# 캐릭터 외형 생성
# ─────────────────────────────────────
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

# ─────────────────────────────────────
# 동화 텍스트 생성
# ─────────────────────────────────────
def generate_story(name, age, gender, topic):
    prompt = f"""
당신은 5~9세 아이를 위한 훈육 동화를 쓰는 작가입니다.
다음 조건을 반드시 지켜 동화를 JSON 형식으로 출력하세요.

1. 이름: {name}, 나이: {age}, 성별: {gender}, 훈육 주제: {topic}
2. 총 5개의 챕터로 구성 (도입, 갈등, 도움, 해결, 마무리)
3. 각 챕터는 2~4문장으로, 리듬감 있고 반복적이며 아이 눈높이에 맞게
4. 각 챕터에는 1문장짜리 삽화 설명 포함 (텍스트/말풍선 금지)
5. 감정, 행동, 배경이 함께 어우러진 따뜻한 이야기
6. 마무리는 명확한 교훈 없이 긍정적인 정서로 마침
7. 반드시 아래 형식으로 JSON으로만 출력:

{{
  "title": "",
  "character": "",
  "chapters": [
    {{
      "title": "",
      "paragraph": "",
      "illustration": ""
    }}
  ],
  "ending": ""
}}
""".strip()

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Korean children's story writer. Respond only in JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1500
        )
        raw = res.choices[0].message.content.strip()
        cleaned = re.sub(r'```(?:json)?', '', raw).strip()
        data = json.loads(cleaned)
        return data
    except Exception as e:
        logging.exception("Story generation failed")
        return None

# ─────────────────────────────────────
# 이미지 프롬프트 생성
# ─────────────────────────────────────
def build_image_prompt(description, character, index):
    style = "따뜻한 조명, 수채화 스타일, 밝고 순한 색감, 아동 친화적, 텍스트 없음"
    base = character.get("visual", {}).get("canonical", "")
    return f"장면 {index}: {description}. {base}. {style}"

# ─────────────────────────────────────
# 이미지 생성
# ─────────────────────────────────────
def generate_image_url(prompt):
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        return res.data[0].url
    except Exception:
        logging.exception("Image generation failed")
        return None

# ─────────────────────────────────────
# 최종 API: 텍스트 + 이미지 병합 생성
# ─────────────────────────────────────
@app.post("/generate-full")
def generate_full():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("topic", "").strip()
    generate_images = data.get("generate_images", True)

    if not all([name, age, gender, topic]):
        return jsonify({"error": "입력 값이 부족합니다."}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story(name, age, gender, topic)

    if not story:
        return jsonify({"error": "동화 생성 실패"}), 500

    # 이미지 생성
    chapters = story.get("chapters", [])
    images = []
    if generate_images:
        for idx, ch in enumerate(chapters, start=1):
            desc = ch.get("illustration", "")
            prompt = build_image_prompt(desc, character, idx)
            url = generate_image_url(prompt)
            ch["image"] = url if url else None
            time.sleep(1.5)  # DALL-E 호출 간 딜레이

    return jsonify({
        "title": story.get("title", ""),
        "character": character,
        "chapters": chapters,
        "ending": story.get("ending", "")
    })

# ─────────────────────────────────────
# 실행
# ─────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
