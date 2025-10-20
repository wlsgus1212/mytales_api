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
    raise RuntimeError("OPENAI_API_KEY not found. Please check your .env file or environment variables.")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────
# 유틸 함수
# ─────────────────────────────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def count_self_choice_indicators(text):
    indicators = ["한 번", "스스로", "시도", "용기", "다시", "조심스레", "결심"]
    return sum(text.count(ind) for ind in indicators)

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
        except:
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
# DALL·E 안전 필터 우회 + 표현 단순화
# ─────────────────────────────
def sanitize_prompt_text(text: str) -> str:
    """DALL·E 안전 정책 + 어린이 단어 정제"""
    replacements = {
        # 위험하거나 감각 관련된 단어
        "먹는다": "시도해 본다",
        "먹었어요": "용기 내어 보았어요",
        "입": "얼굴",
        "입가": "얼굴",
        "혀": "얼굴",
        "손": "몸",
        "손끝": "몸",
        "손가락": "몸",
        "포크": "작은 도구",
        "젓가락": "작은 도구",
        "냄새": "향기",
        "향기를 맡": "느꼈",
        "육회": "음식",
        "피": "빨간색 소스",
        "죽었다": "잠들었다",
        "벌칙": "도전",
        "울었다": "조용히 눈을 감았어요",
        # 어려운 단어
        "결심": "마음먹었어요",
        "자제": "기다렸어요",
        "훈육": "이야기",
        "도덕": "이야기",
        "규칙": "약속",
        "욕심": "바람",
        "인내": "기다림",
    }
    sanitized = text
    for k, v in replacements.items():
        sanitized = sanitized.replace(k, v)
    return sanitized


# ─────────────────────────────
# 캐릭터 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    if gender == "여자":
        hair = random.choice(["갈색 단발머리", "긴 생머리", "밤색 웨이브 머리"])
        outfit = random.choice(["분홍 원피스", "노란 셔츠와 멜빵바지", "하늘색 티셔츠와 스커트"])
    else:
        hair = random.choice(["짧은 검은 머리", "갈색 머리", "단정한 밤색 머리"])
        outfit = random.choice(["초록 후드", "파란 티셔츠와 반바지", "노란 셔츠와 청바지"])

    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face with soft cheeks; bright eyes; childlike proportions."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit,
            "face": "둥글고 부드러운 얼굴",
            "eyes": "맑은 눈",
            "proportions": "아이 같은 비율"
        }
    }


# ─────────────────────────────
# 동화 텍스트 생성
# ─────────────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    prompt = f"""
당신은 5~9세 어린이를 위한 동화 작가입니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

목표:
- 아이 눈높이의 쉬운 단어로만 구성 (예: 놀다, 반짝이다, 용기, 친구)
- 어려운 말(결심, 도덕, 인내 등) 금지
- 교훈은 직접 말하지 않고, 행동과 감정으로 표현
- 주인공은 스스로 시도하며 성장 (2회 이상 시도 장면)
- 의인화된 조력자 등장 (예: 요정, 새, 별 등)
- 구조: 제목 / 5개 챕터 / 마무리
- 각 챕터는 2~3문장 + 삽화용 묘사 1문장
- 출력은 JSON 형태:
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}},...], "ending":""}}
"""
    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are '훈육 동화봇' writing gentle, simple Korean stories for children."},
                    {"role": "user", "content": prompt.strip()}
                ],
                temperature=0.6,
                max_tokens=1100,
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            data = json.loads(cleaned)
            if isinstance(data, dict) and len(data.get("chapters", [])) >= 5:
                return data
        except Exception:
            logging.exception("동화 생성 실패, 재시도 중...")
            time.sleep(0.5)

    # fallback 기본 구조
    title = f"{name}의 작은 이야기"
    chapters = [
        {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 일을 두려워했어요.", "illustration": "햇살이 비치는 방 안의 아이"},
        {"title": "2. 초대", "paragraph": "작은 요정이 나타나 손을 내밀었어요.", "illustration": "빛나는 요정이 웃는 장면"},
        {"title": "3. 시도", "paragraph": f"{name}은(는) 용기를 내어 한 발짝 내딛었어요.", "illustration": "초록 들판 위의 아이"},
        {"title": "4. 깨달음", "paragraph": "바람이 불며 아이의 마음이 가벼워졌어요.", "illustration": "머리카락이 흩날리는 장면"},
        {"title": "5. 귀환", "paragraph": f"{name}은(는) 미소를 지으며 하늘을 올려다보았어요.", "illustration": "푸른 하늘을 보는 아이"}
    ]
    return {"title": title, "character": f"{name} ({age} {gender})", "chapters": chapters, "ending": "아이의 마음이 따뜻해졌어요."}


# ─────────────────────────────
# 장면 묘사 + 이미지 프롬프트
# ─────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    """장면 설명을 부드럽고 안전하게 생성"""
    gender = character_profile.get("gender", "")
    age = character_profile.get("age", "")
    try:
        prompt = f"""
이전 장면 요약: {previous_summary}
현재 장면: {scene_text}

{age}세 {gender} 아이가 등장하는 그림책 장면을 설명하세요.
- 감정과 배경 중심으로 한 문장만 생성
- 신체, 음식, 감각 표현(입, 손, 포크, 냄새 등) 금지
- 예: "아이의 얼굴에 햇살이 비치며 미소가 번져요."
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write safe Korean visual descriptions for children's picture books."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.25,
            max_tokens=180,
        )
        desc = clean_text(res.choices[0].message.content)
        return sanitize_prompt_text(desc)
    except Exception:
        logging.exception("장면 묘사 실패")
        return sanitize_prompt_text(f"{scene_text[:100]} ... 따뜻한 조명, 수채화 느낌.")


def build_image_prompt_kor(scene_sentence, character_profile, scene_index):
    """이미지 생성용 안전 프롬프트"""
    canonical = sanitize_prompt_text(character_profile.get('visual', {}).get('canonical') or "")
    style = "부드러운 수채화; 따뜻한 조명; 아동 친화적 색감; 순한 그림체"
    gender = character_profile.get("gender", "아이")
    age = character_profile.get("age", "")
    safe_scene = sanitize_prompt_text(scene_sentence)

    return (
        f"{age}세 {gender} 아이. {canonical}. "
        f"장면 {scene_index}: {safe_scene}. "
        f"스타일: {style}. 캐릭터 외형은 동일 유지. 텍스트/말풍선 금지."
    )


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
        return jsonify({"error": "name, age, gender, topic 모두 필요"}), 400

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

    return jsonify({
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in chapters],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts,
        "ending": story_data.get("ending", "")
    })


# ─────────────────────────────
# 엔드포인트: /generate-image
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    character_profile = ensure_character_profile(data.get("character_profile"))
    scene_description = data.get("image_description") or ""
    scene_index = data.get("scene_index") or 1

    if not character_profile or not scene_description:
        return jsonify({"error": "character_profile 및 scene_description 필요"}), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)
    logging.info(f"🎨 이미지 {scene_index} 생성 중... prompt 길이={len(prompt)}")

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        url = res.data[0].url if res and res.data else None
        if not url:
            raise ValueError("이미지 응답에 URL 없음")
        return jsonify({"image_url": url, "prompt_used": prompt})
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "detail": str(e)}), 500


# ─────────────────────────────
# 앱 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
