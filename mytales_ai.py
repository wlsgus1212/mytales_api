# mytales_ai.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, time

# ─────────────────────────────
# 초기 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────
# 유틸 함수
# ─────────────────────────────
def clean_text(s: str):
    """텍스트에서 불필요한 특수문자 제거"""
    return re.sub(r"[\"<>]", "", (s or "")).strip()

def ensure_character_profile(profile):
    """캐릭터 프로필 dict 일관성 유지"""
    if isinstance(profile, dict):
        return profile
    return {
        "name": None,
        "age": None,
        "gender": None,
        "visual": {
            "canonical": str(profile),
            "hair": "",
            "outfit": "",
            "eyes": "",
            "face": "",
            "proportions": ""
        }
    }

# ─────────────────────────────
# 캐릭터 기본 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair_options = ["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"]
    outfit_options = ["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"]
    hair = hair_options[hash(name) % len(hair_options)]
    outfit = outfit_options[hash(age) % len(outfit_options)]

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
            "eyes": "따뜻한 갈색 눈",
            "face": "부드러운 볼의 둥근 얼굴",
            "proportions": "아이 같은 비율"
        }
    }

# ─────────────────────────────
# 통합 동화 + 이미지 설명 생성
# ─────────────────────────────
def generate_story_with_images(name, age, gender, topic):
    """GPT가 동화 + 이미지 설명을 한 번에 생성"""
    prompt = f"""
당신은 5~9세 어린이를 위한 '훈육 동화 작가'입니다.
주제: {topic}, 주인공: {name} ({age}세, {gender}).

규칙:
1. 스토리 구조는 5개의 장면으로 구성합니다.
   - 1장: 시작 (문제 제시)
   - 2~4장: 모험과 시도 (조력자, 의인화된 존재 등장)
   - 5장: 마무리 (행동으로 변화 암시)
2. 각 장면은 2~4문장으로 따뜻하고 간결한 한국어로 작성하세요.
3. 교훈은 직접 말하지 말고 행동으로 보여주세요.
4. 어린이에게 부적절하거나 이해하기 어려운 단어는 절대 사용하지 마세요.
5. 감정 변화, 냄새·색깔·소리 등 감각 묘사를 꼭 포함하세요.
6. 각 장면 끝에 반드시 시각적 삽화 설명을 한 문장으로 덧붙이세요.
   (예: [그림: 따뜻한 주방에서 아이가 조심스레 포크를 드는 장면])

출력 형식은 반드시 JSON으로:
{{
  "title": "",
  "character": "",
  "chapters": [
     {{
       "title": "",
       "paragraph": "",
       "illustration": ""
     }},
     ...
  ],
  "ending": ""
}}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are '훈육 동화봇' writing warm Korean discipline stories in JSON."},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.6,
            max_tokens=1500
        )
        raw = res.choices[0].message.content.strip()
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        data = json.loads(cleaned)
        return data
    except Exception as e:
        logging.exception("동화 생성 실패")
        return None

# ─────────────────────────────
# 이미지 생성 함수
# ─────────────────────────────
def generate_image_from_prompt(character_profile, scene_description, scene_index):
    """DALL·E를 사용해 이미지 생성"""
    canonical = character_profile.get("visual", {}).get("canonical", "")
    gender = character_profile.get("gender", "")
    style = "부드러운 수채화 스타일; 따뜻한 조명; 밝고 순한 색감; 어린이 그림책 느낌"
    safe_desc = re.sub(r"[^\w\s가-힣.,!?;:]", "", scene_description)

    prompt = (
        f"{canonical} "
        f"주인공은 {gender} 어린이입니다. "
        f"장면 {scene_index}: {safe_desc}. "
        f"스타일: {style}. "
        f"텍스트, 말풍선, 자막은 포함하지 마세요."
    )

    try:
        result = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            n=1,
            quality="standard"
        )
        return result.data[0].url
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return None

# ─────────────────────────────
# 엔드포인트: /generate-story
# ─────────────────────────────
@app.post("/generate-story")
def generate_story():
    """한 번에 스토리 + 이미지 모두 생성"""
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("topic") or data.get("education_goal", "")

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic 모두 필요합니다."}), 400

    # 캐릭터 프로필 생성
    character_profile = generate_character_profile(name, age, gender)
    logging.info(f"🎨 캐릭터 생성 완료: {character_profile['visual']['canonical']}")

    # GPT로 전체 스토리 생성
    story_data = generate_story_with_images(name, age, gender, topic)
    if not story_data or "chapters" not in story_data:
        return jsonify({"error": "스토리 생성 실패"}), 500

    # 각 장면별 이미지 생성
    image_urls = []
    for idx, ch in enumerate(story_data["chapters"], start=1):
        desc = ch.get("illustration") or ch.get("paragraph", "")
        logging.info(f"🖼️ 장면 {idx} 이미지 생성 중: {desc[:40]}")
        url = generate_image_from_prompt(character_profile, desc, idx)
        image_urls.append(url)

    response = {
        "title": story_data.get("title", f"{name}의 이야기"),
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in story_data["chapters"]],
        "illustrations": [c.get("illustration", "") for c in story_data["chapters"]],
        "image_urls": image_urls,
        "ending": story_data.get("ending", "")
    }

    logging.info("✅ 통합 스토리+이미지 생성 완료")
    return jsonify(response)

# ─────────────────────────────
# 서버 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
