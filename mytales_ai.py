from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, random, logging, time

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────
# 유틸 함수
# ─────────────────────────────
def clean_text(s: str) -> str:
    """텍스트 내 불필요한 문자 제거"""
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def ensure_character_profile(obj):
    """캐릭터 프로필이 문자열이면 dict로 변환"""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        canonical = re.sub(r'Canonical\s*Visual\s*Descriptor\s*[:\-]?', '', obj).strip()
        return {
            "visual": {"canonical": canonical},
            "style": canonical
        }
    return None

# ─────────────────────────────
# 캐릭터 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = (
        f"Canonical Visual Descriptor: {hair}; {outfit}; "
        "둥근 얼굴과 부드러운 볼; 따뜻한 갈색 눈; 아이 같은 비율."
    )
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {"canonical": canonical, "hair": hair, "outfit": outfit}
    }

# ─────────────────────────────
# 단일 호출로 동화 + 이미지 설명 생성
# ─────────────────────────────
def generate_story_and_illustrations(name, age, gender, topic):
    """GPT가 한 번에 동화 본문 + 이미지 설명까지 생성"""
    prompt = f"""
당신은 5~9세 어린이를 위한 훈육 동화 작가이자 일러스트 기획자입니다.
입력값:
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {topic}

요구사항:
1. 주제에 맞는 따뜻한 이야기 작성 (기승전결 포함, 5장 구성).
2. 직접적인 교훈 서술 금지. 행동, 감정, 묘사를 통해 암시.
3. 의인화된 존재와 조력자 등장 필수.
4. 주인공은 스스로 두 번 이상 시도함.
5. 어려운 어휘, 폭력/부적절한 단어 사용 금지.
6. 각 장면마다 ‘illustration’ 항목에 시각적 묘사 한 문장 포함.
7. 형식은 아래 JSON만 출력:
{{
  "title": "",
  "character": "",
  "chapters": [
    {{"title": "", "paragraph": "", "illustration": ""}},
    ...
  ],
  "ending": ""
}}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Korean children's story writer and illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.7,
            max_tokens=1500,
        )

        raw = res.choices[0].message.content.strip()
        cleaned = re.sub(r'```(?:json)?', '', raw).strip()
        story_data = json.loads(cleaned)

        # JSON 구조 검증
        if not isinstance(story_data.get("chapters"), list) or len(story_data["chapters"]) < 5:
            raise ValueError("Invalid story structure")

        return story_data

    except Exception as e:
        logging.exception("⚠️ 동화 생성 실패, 기본값으로 대체")
        # fallback story
        title = f"{name}의 작은 모험"
        chapters = [
            {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": "따뜻한 부엌의 식탁 장면"},
            {"title": "2. 만남", "paragraph": "말하는 당근이 다가와 인사했어요.", "illustration": "작은 당근 요정이 인사하는 장면"},
            {"title": "3. 시도", "paragraph": f"{name}은(는) 한입 시도했지만 멈칫했어요.", "illustration": "포크를 든 아이의 긴장된 표정"},
            {"title": "4. 도움", "paragraph": "호박 요정이 용기를 주었어요.", "illustration": "호박 요정이 따뜻하게 미소짓는 장면"},
            {"title": "5. 변화", "paragraph": f"{name}은(는) 작은 조각을 맛보고 웃었어요.", "illustration": "창가에서 미소짓는 아이"}
        ]
        return {"title": title, "character": f"{name} ({age}세 {gender})", "chapters": chapters, "ending": "작은 용기가 큰 웃음을 만들었어요."}

# ─────────────────────────────
# 이미지 프롬프트 구성
# ─────────────────────────────
def build_image_prompt(scene_text, character_profile):
    canonical = character_profile.get("visual", {}).get("canonical", "")
    style = (
        "부드러운 수채화 스타일; 따뜻한 조명; 밝고 순한 색감; "
        "아이 친화적 구성; mid-shot; 텍스트나 말풍선 없음."
    )
    # 안전한 프롬프트 필터링
    safe_text = re.sub(r"(피|죽|살|붉은|검은|어두운)", "밝은", scene_text)
    return f"{canonical} 장면: {safe_text}. {style}"

# ─────────────────────────────
# 엔드포인트: /generate-story (텍스트 + 이미지 설명)
# ─────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("topic") or data.get("education_goal", "")
    if not all([name, age, gender, topic]):
        return jsonify({"error": "모든 항목(name, age, gender, topic)이 필요합니다."}), 400

    character_profile = generate_character_profile(name, age, gender)
    story_data = generate_story_and_illustrations(name, age, gender, topic)

    # 이미지 프롬프트 생성
    image_prompts = []
    for ch in story_data.get("chapters", []):
        desc = ch.get("illustration", "")
        prompt = build_image_prompt(desc, character_profile)
        image_prompts.append(prompt)

    response = {
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph") for c in story_data["chapters"]],
        "image_descriptions": [c.get("illustration") for c in story_data["chapters"]],
        "image_prompts": image_prompts,
        "ending": story_data.get("ending")
    }
    logging.info(f"✅ /generate-story 완료: {story_data.get('title')}")
    return jsonify(response)

# ─────────────────────────────
# 엔드포인트: /generate-image
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    scene_description = data.get("scene_description") or data.get("image_description")
    character_profile = ensure_character_profile(data.get("character_profile"))
    if not scene_description or not character_profile:
        return jsonify({"error": "scene_description과 character_profile이 필요합니다."}), 400

    prompt = build_image_prompt(scene_description, character_profile)
    logging.info(f"🎨 이미지 생성 중... prompt 길이={len(prompt)}")

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            n=1,
            quality="standard"
        )
        image_url = res.data[0].url
        return jsonify({"image_url": image_url, "prompt_used": prompt})
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "detail": str(e)}), 500

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
