from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Please set it in .env file")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────
# 유틸 함수
# ─────────────────────────────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def sanitize_prompt_text(s):
    """이미지 안전 필터를 피하기 위한 위험 단어 제거"""
    if not s:
        return ""
    forbidden = [
        "얼굴", "눈", "입", "손", "팔", "다리", "몸", "피부", "표정", "미소",
        "울다", "웃다", "먹다", "한입", "마시다", "감정", "행동", "아이", "어린이",
        "소년", "소녀", "hug", "face", "child", "boy", "girl", "hand", "mouth"
    ]
    result = s
    for w in forbidden:
        result = result.replace(w, "")
    return result.strip()

def ensure_character_profile(obj):
    if not obj:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        m = re.search(r'Canonical\s*Visual\s*Descriptor\s*[:\-]?\s*(.+)', s, re.IGNORECASE)
        canonical = m.group(1).strip() if m else s
        return {
            "name": None,
            "age": None,
            "gender": None,
            "style": canonical,
            "visual": {
                "canonical": canonical,
                "hair": "",
                "outfit": "",
                "face": "",
                "eyes": "",
                "proportions": ""
            }
        }
    return None

# ─────────────────────────────
# 캐릭터 프로필 생성
# ─────────────────────────────
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

# ─────────────────────────────
# 동화 텍스트 생성
# ─────────────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    """훈육 주제를 반영한 따뜻한 동화 구조"""
    base_prompt = f"""
당신은 5~9세 아동을 위한 따뜻하고 교훈적인 동화 작가입니다.
주제: {topic}, 주인공: {name}({age}세, {gender})

요구사항:
1. 구조: 시작(문제 인식) → 시도(2회 이상) → 조력자 등장 → 변화와 암시적 결말
2. '먹다', '울다', '화나다' 같은 직접 행동 표현 금지
3. 주제는 행동이 아니라 '감정과 배경의 변화'로 표현
4. JSON 형식:
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}},...], "ending":""}}
"""
    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role":"system","content":"You are a Korean children's story writer."},
                    {"role":"user","content": base_prompt.strip()}
                ],
                temperature=0.6,
                max_tokens=1100,
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            data = json.loads(cleaned)
            if isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
                return data
        except Exception as e:
            logging.warning(f"스토리 생성 실패, 재시도 중: {e}")
            time.sleep(0.5)
    # fallback
    return {
        "title": f"{name}의 작은 모험",
        "character": f"{name} ({age} {gender})",
        "chapters": [
            {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 세상을 궁금해했어요.", "illustration": "밝은 들판의 시작 장면"},
            {"title": "2. 발견", "paragraph": "햇살 아래에서 작은 소리를 들었어요.", "illustration": "햇살과 바람이 부는 초원"},
            {"title": "3. 만남", "paragraph": "작은 빛이 반짝이며 친구처럼 다가왔어요.", "illustration": "부드러운 빛이 떠 있는 장면"},
            {"title": "4. 변화", "paragraph": "마음속에서 따뜻한 무언가가 퍼졌어요.", "illustration": "따뜻한 색감의 장면"},
            {"title": "5. 귀환", "paragraph": "집으로 돌아온 {name}은(는) 미소 지었어요.", "illustration": "노을 속 따뜻한 집"}
        ],
        "ending": "주인공의 마음에 잔잔한 빛이 남았어요."
    }

# ─────────────────────────────
# 안전한 이미지 설명 생성
# ─────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    """사람·행동 묘사 없이 배경 중심 묘사 생성"""
    try:
        prompt = f"""
이전 내용: {previous_summary}
현재 장면: {scene_text}

조건:
- 인물 묘사 금지 (얼굴, 손, 눈, 입, 몸, 행동, 감정 등)
- 배경, 색감, 조명, 공간 중심으로 한 문장 생성
- 예: "따뜻한 햇살이 비치는 평화로운 들판", "부드러운 조명이 켜진 방 안"
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role":"system","content":"Write neutral Korean illustration scene descriptions (no people or actions)."},
                {"role":"user","content": prompt.strip()}
            ],
            temperature=0.25,
            max_tokens=120,
        )
        desc = clean_text(res.choices[0].message.content)
        return sanitize_prompt_text(desc)
    except Exception:
        logging.exception("장면 묘사 실패")
        return "따뜻한 조명과 부드러운 색감의 평화로운 풍경."

# ─────────────────────────────
# 이미지 프롬프트 생성
# ─────────────────────────────
def build_image_prompt_kor(scene_sentence, character_profile, scene_index):
    """안전한 이미지 프롬프트"""
    safe_scene = sanitize_prompt_text(scene_sentence)
    canonical = sanitize_prompt_text(character_profile.get('visual', {}).get('canonical') or "")
    style = "soft watercolor illustration, pastel tones, warm light, no humans, no faces, children's picture book background"
    return f"{canonical}. Scene {scene_index}: {safe_scene}. {style}."

# ─────────────────────────────
# 엔드포인트: /generate-story
# ─────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    age = (data.get("age") or "").strip()
    gender = (data.get("gender") or "").strip()
    topic = (data.get("topic") or data.get("education_goal") or "").strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error":"name, age, gender, topic 모두 필요"}), 400

    character_profile = generate_character_profile(name, age, gender)
    story_data = generate_story_text(name, age, gender, topic)

    chapters = story_data.get("chapters", [])
    image_descriptions, image_prompts = [], []
    accumulated = ""

    for idx, ch in enumerate(chapters, start=1):
        para = ch.get("paragraph", "")
        prev = accumulated or "이야기 시작"
        desc = describe_scene_kor(para, character_profile, idx, prev)
        prompt = build_image_prompt_kor(desc, character_profile, idx)
        image_descriptions.append(desc)
        image_prompts.append(prompt)
        accumulated += " " + para

    response = {
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in chapters],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts,
        "ending": story_data.get("ending", "")
    }
    return jsonify(response)

# ─────────────────────────────
# 엔드포인트: /generate-image
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    raw_cp = data.get("character_profile")
    scene_description = data.get("image_description") or data.get("scene_description") or ""
    scene_index = data.get("scene_index") or 1

    character_profile = ensure_character_profile(raw_cp)
    if not character_profile or not scene_description:
        return jsonify({"error":"character_profile 및 scene_description 필요"}), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)
    logging.info(f"🎨 이미지 {scene_index} 생성 중... prompt 길이={len(prompt)}")

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="standard",
            n=1
        )
        url = res.data[0].url if res and getattr(res, "data", None) else None
        if not url:
            raise ValueError("이미지 URL 없음")
        return jsonify({"image_url": url, "prompt_used": prompt})
    except Exception as e:
        logging.warning(f"⚠️ 이미지 생성 실패, 안전 프롬프트로 재시도: {e}")
        fallback_prompt = "soft watercolor landscape illustration, no people, warm colors, gentle light"
        try:
            res2 = client.images.generate(
                model="dall-e-3",
                prompt=fallback_prompt,
                size="1024x1024",
                n=1
            )
            url2 = res2.data[0].url
            return jsonify({"image_url": url2, "prompt_used": fallback_prompt})
        except Exception as e2:
            logging.exception("Fallback 이미지 생성 실패")
            return jsonify({"error":"이미지 생성 실패","detail":str(e2)}), 500

# ─────────────────────────────
# 로컬 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
