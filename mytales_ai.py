from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, re, json, random, time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────
# 환경 변수 및 초기 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)

# ✅ CORS 허용 설정 (Wix 미리보기 포함)
CORS(app, resources={r"/*": {"origins": [
    "https://*.wixsite.com",
    "https://*.wix-code.com",
    "https://editor.wix.com"
]}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─────────────────────────────
# OPTIONS 사전 요청 응답 (CORS Preflight 대응)
# ─────────────────────────────
@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return '', 200

# ─────────────────────────────
# 유틸
# ─────────────────────────────
def clean_json(s: str):
    s = re.sub(r"```(?:json)?", "", s)
    try:
        return json.loads(s.strip())
    except:
        m = re.search(r"(\{[\s\S]*\})", s)
        if m:
            try:
                return json.loads(m.group(1))
            except:
                return None
    return None

# ─────────────────────────────
# 캐릭터 설정 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"{hair}; {outfit}; round face with soft cheeks; warm brown almond eyes; gentle smile; childlike proportions; gender:{gender}; age:{age}."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit
        }
    }

# ─────────────────────────────
# 동화 생성
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
1. 발단-전개-절정-결말 구조
2. 직접적 훈계 없이 감정과 상황을 통해 학습 유도
3. artist_description 포함 (배경, 감정, 구도)
4. JSON 이외 출력 금지
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Korean children's story writer who outputs JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1400
        )
        data = clean_json(res.choices[0].message.content)
        if data:
            return data
    except:
        logging.exception("동화 생성 실패")
    return {}

# ─────────────────────────────
# 이미지 프롬프트 구성 및 생성
# ─────────────────────────────
def build_image_prompt(character, artist_description):
    return f"{character['visual']['canonical']} {artist_description}. soft watercolor, pastel, warm lighting, no text, picture book illustration."

def generate_image_from_prompt(prompt):
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            n=1,
            quality="standard"
        )
        if res.data and res.data[0].url:
            return res.data[0].url
    except:
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
        desc = chapter.get("artist_description") or " ".join(chapter.get("paragraphs", []))
        prompt = build_image_prompt(character, desc)
        return generate_image_from_prompt(prompt)

    images = [None] * len(chapters)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(generate_scene, ch): i for i, ch in enumerate(chapters)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                images[idx] = future.result()
            except:
                images[idx] = None

    for i, ch in enumerate(chapters):
        ch["image"] = images[i] or None

    result = {
        "title": story.get("title", ""),
        "character_profile": character,
        "chapters": chapters,
        "ending": story.get("ending", ""),
        "time_taken": round(time.time() - start, 2)
    }
    return jsonify(result)

# ─────────────────────────────
# 상태 확인
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
