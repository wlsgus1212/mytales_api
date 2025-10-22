from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, re, json, random, time, logging, base64, requests
from io import BytesIO
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────
# 초기 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─────────────────────────────
# 기본 유틸
# ─────────────────────────────
def clean_json(s: str):
    s = re.sub(r"```(?:json)?", "", s)
    try:
        return json.loads(s.strip())
    except Exception:
        m = re.search(r"(\{[\s\S]*\})", s)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
    return None

# ─────────────────────────────
# 캐릭터 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face with soft cheeks; warm brown almond eyes; gentle smile; childlike proportions; gender:{gender}; age:{age}."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, {outfit}",
        "visual": {"canonical": canonical, "hair": hair, "outfit": outfit}
    }

# ─────────────────────────────
# 동화 텍스트 생성 (기승전결 + 시도/보상 구조)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    prompt = f"""
당신은 5~9세 아이를 위한 한국어 훈육 동화 작가입니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

아래 JSON 형식으로만 출력하세요:
{{
 "title": "",
 "character": "",
 "chapters": [
   {{
     "title": "",
     "paragraphs": ["", ""],
     "artist_description": ""
   }}
 ],
 "ending": ""
}}

규칙:
1. 스토리 구조: 발단 → 전개(시도와 실패) → 절정(결심과 선택) → 결말(행동의 변화)
2. 직접적인 교훈 대신, 행동과 감정 변화를 통해 의미를 암시
3. 주인공은 스스로 시도하며, 조력자가 상징적 조언 또는 작은 규칙을 전달
4. 각 장면마다 artist_description(그림 묘사)을 추가: 캐릭터 외형 + 감정 + 배경 + 조명 + 구도 포함
5. 언어는 간결하고 따뜻하게, 유아도 이해할 수 있도록 작성
6. JSON 외 텍스트 출력 금지
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Korean children's story writer who outputs JSON only."},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.6,
            max_tokens=1400,
        )
        data = clean_json(res.choices[0].message.content)
        if data and "chapters" in data:
            return data
    except Exception:
        logging.exception("generate_story_text 실패")

    # fallback
    return {
        "title": f"{name}의 작은 모험",
        "character": f"{name} ({age} {gender})",
        "chapters": [
            {"title": "1. 시작", "paragraphs": [f"{name}은 채소를 싫어했어요.", "새로운 음식을 보면 고개를 돌렸어요."],
             "artist_description": "아이의 식탁 앞, 색색의 채소, 부드러운 빛, 따뜻한 분위기"},
            {"title": "2. 만남", "paragraphs": ["작은 요정이 나타났어요.", "요정이 미소 지으며 다가왔어요."],
             "artist_description": "반짝이는 요정과 놀라는 아이, 부엌의 아늑한 조명"},
            {"title": "3. 시도", "paragraphs": ["조심스레 한입 먹어보았어요.", "입안이 낯설지만 이상하게 기분이 좋았어요."],
             "artist_description": "아이의 작은 시도 장면, 밝은 햇살, 따뜻한 그림"},
            {"title": "4. 절정", "paragraphs": ["다시 용기를 냈어요.", "요정의 말이 떠올랐어요. 천천히 한입씩."],
             "artist_description": "결심한 아이의 눈빛, 부드러운 색감, 희미한 마법의 빛"},
            {"title": "5. 결말", "paragraphs": ["이제 채소가 무섭지 않았어요.", "작은 용기가 마음속에서 반짝였어요."],
             "artist_description": "창가에서 미소짓는 아이, 따뜻한 햇살, 수채화 스타일"}
        ],
        "ending": "작은 용기가 큰 변화를 만들었어요."
    }

# ─────────────────────────────
# 이미지 프롬프트 생성
# ─────────────────────────────
def build_image_prompt(character, artist_description):
    canonical = character["visual"]["canonical"]
    return (
        f"{canonical} {artist_description}. "
        "soft watercolor style, warm lighting, pastel colors, no text, "
        "children’s picture book illustration, consistent character appearance."
    )

# ─────────────────────────────
# 이미지 생성
# ─────────────────────────────
def generate_image_from_prompt(prompt):
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            n=1,
            quality="standard"
        )
        if res and res.data and res.data[0].url:
            return res.data[0].url
    except Exception:
        logging.exception("이미지 생성 실패")
    return None

# ─────────────────────────────
# /generate-full
# ─────────────────────────────
@app.post("/generate-full")
def generate_full():
    start = time.time()
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("topic", "").strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic required"}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)
    chapters = story.get("chapters", [])

    def generate_scene(chapter):
        desc = " ".join(chapter.get("paragraphs", []))
        artist_desc = chapter.get("artist_description", "")
        prompt = build_image_prompt(character, artist_desc or desc)
        return generate_image_from_prompt(prompt)

    images = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(generate_scene, ch): i for i, ch in enumerate(chapters)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            try:
                images.insert(idx, fut.result())
            except Exception:
                images.insert(idx, None)

    for i, ch in enumerate(chapters):
        ch["image_url"] = images[i] if i < len(images) else None

    total_time = round(time.time() - start, 1)
    logging.info("✅ 전체 완료: %.1f초", total_time)

    return jsonify({
        "title": story["title"],
        "character_profile": character,
        "chapters": chapters,
        "ending": story["ending"],
        "time_taken": total_time
    })

# ─────────────────────────────
# /health
# ─────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": time.time()})

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
