from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, random, logging, time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

# ─────────────────────────────
# 유틸
# ─────────────────────────────
def clean_text(s):
    return re.sub(r"[\"<>]", "", (s or "")).strip()

def safe_json_loads(s):
    try:
        return json.loads(s)
    except:
        m = re.search(r"(\{[\s\S]*\})", s)
        if m:
            try:
                return json.loads(m.group(1))
            except:
                return None
    return None

# ─────────────────────────────
# 캐릭터 프로필
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face, warm brown eyes, childlike proportions."
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
            "proportions": "아이 같은 비율"
        }
    }

# ─────────────────────────────
# 동화 생성 (텍스트 전용)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    logging.info("🧠 ChatGPT 동화 생성 시작")
    prompt = f"""
당신은 어린이 훈육동화 작가입니다. 대상은 5~9세이며, 말투는 따뜻하고 리드미컬해야 합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

형식(JSON):
{{
  "title": "",
  "chapters": [
    {{"title": "", "paragraph": "", "illustration": ""}},
    ...
  ],
  "ending": ""
}}

조건:
1. 총 5개의 장면 (각 2~3문장)
2. 교훈은 직접 말하지 말고, 행동 변화로 암시
3. 감정 변화와 감각 묘사 포함
4. 등장인물: 주인공 + 의인화된 조력자 1명
5. 어려운 단어 금지, 잔인하거나 위험한 표현 금지
6. 출력은 반드시 JSON
    """.strip()

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You write gentle Korean picture book stories for children."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1000,
            timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list):
            return data
    except Exception as e:
        logging.exception("❌ 동화 생성 실패")
    # fallback
    return {
        "title": f"{name}의 작은 모험",
        "chapters": [
            {"title": "시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": "식탁 앞의 아이"},
            {"title": "친구의 등장", "paragraph": "작은 요정이 나타나 용기를 주었어요.", "illustration": "요정과 아이"},
            {"title": "도전", "paragraph": f"{name}은(는) 조심스레 한입 시도했어요.", "illustration": "포크를 든 아이"},
            {"title": "변화", "paragraph": "달콤한 향기가 입안을 감쌌어요.", "illustration": "웃는 아이"},
            {"title": "마무리", "paragraph": "이제 {name}은(는) 새로운 음식을 두렵지 않아했어요.", "illustration": "창가에 앉은 아이"}
        ],
        "ending": "작은 용기가 큰 변화를 만들었어요."
    }

# ─────────────────────────────
# 이미지 생성 함수
# ─────────────────────────────
def generate_image_from_prompt(character_profile, scene_desc, scene_index):
    canonical = character_profile["visual"]["canonical"]
    prompt = (
        f"{canonical}. Scene {scene_index}: {scene_desc}. "
        f"Watercolor style, soft warm light, gentle children's illustration, no text, no captions."
    )
    try:
        result = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="standard",
            n=1,
            timeout=60
        )
        return result.data[0].url
    except Exception as e:
        logging.exception(f"❌ 이미지 생성 실패 ({scene_index})")
        return None

# ─────────────────────────────
# 엔드포인트: /generate-story
# ─────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("education_goal", data.get("topic", "")).strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "모든 입력값 필요"}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)

    return jsonify({
        "title": story.get("title"),
        "character_profile": character,
        "story_paragraphs": [c["paragraph"] for c in story.get("chapters", [])],
        "image_descriptions": [c.get("illustration", "") for c in story.get("chapters", [])],
        "ending": story.get("ending", "")
    })

# ─────────────────────────────
# 엔드포인트: /generate-image
# (결과페이지에서 병렬 호출)
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    character = data.get("character_profile")
    scenes = data.get("image_descriptions", [])
    if not character or not scenes:
        return jsonify({"error": "character_profile 및 image_descriptions 필요"}), 400

    urls = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_scene = {executor.submit(generate_image_from_prompt, character, desc, i + 1): i for i, desc in enumerate(scenes)}
        for future in as_completed(future_to_scene):
            url = future.result()
            urls.append(url)

    return jsonify({"image_urls": urls})

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
