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
    raise RuntimeError("OPENAI_API_KEY not found. Please check your .env or environment variables.")

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
    indicators = ["한 번", "한입", "한 입", "냄새", "손끝", "손가락", "스스로", "직접", "시도", "골라", "골라보다", "조심스레", "조심히", "다시 한 번", "다시 한입"]
    if not text:
        return 0
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
    prompt = f"""
당신은 '훈육 동화봇'입니다. 대상은 5~9세 아동이며, 말투는 따뜻하고 리드미컬합니다.
이야기는 의인화된 존재(훈육 주제의 화신)와 조력자가 등장하는 모험 서사로, 주인공이 스스로 여러 번 작은 시도를 통해 변화에 다가가는 형식이어야 합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 훈육 주제={topic}.

구성:
- title, character, chapters[5개: title, paragraph, illustration], ending
- 각 챕터는 1~3문장
- 감정 변화와 감각 묘사 포함
- '직접적인 교훈' 금지, 행동으로 암시할 것
    """

    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are '훈육 동화봇' writing Korean discipline stories in JSON."},
                    {"role": "user", "content": prompt.strip()}
                ],
                temperature=0.6,
                max_tokens=1200,
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            data = json.loads(cleaned)
            if isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
                full_text = " ".join([c["paragraph"] for c in data["chapters"]])
                if count_self_choice_indicators(full_text) >= 2:
                    return data
        except Exception as e:
            logging.exception("generate_story_text 실패")
            time.sleep(0.5)

    # Fallback
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": "밝은 주방의 식탁"},
        {"title": "2. 소리", "paragraph": "딸깍 소리와 함께 음식 친구들이 말을 걸었어요.", "illustration": "말하는 당근들"},
        {"title": "3. 조심스러운 접근", "paragraph": f"{name}은(는) 손끝으로 살짝 만져보았어요.", "illustration": "포크를 조심스레 드는 아이"},
        {"title": "4. 조력자의 등장", "paragraph": "호박 요정이 게임을 제안했어요.", "illustration": "작은 호박 캐릭터"},
        {"title": "5. 귀환", "paragraph": "집으로 돌아와 다시 한입 시도했어요.", "illustration": "창가에 앉은 아이"}
    ]
    return {
        "title": title,
        "character": f"{name} ({age} {gender})",
        "chapters": chapters,
        "ending": "아이의 입가에 작은 미소가 피어났어요."
    }

# ─────────────────────────────
# 장면 묘사 + 이미지 프롬프트
# ─────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    try:
        prompt = f"""
이전 내용: {previous_summary}
현재 장면: {scene_text}
캐릭터 외형: {character_profile.get('visual', {}).get('canonical')}
→ 감정/배경/조명/행동을 포함한 묘사, 한 문장으로. 텍스트/말풍선 없이.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write Korean visual descriptions for children's picture books."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.25,
            max_tokens=180,
        )
        return clean_text(res.choices[0].message.content)
    except:
        logging.exception("묘사 실패")
        return f"{scene_text[:100]}... 따뜻한 조명, 수채화 느낌."

def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    canonical = character_profile.get('visual', {}).get('canonical') or ""
    style = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    return (
        f"{canonical} 장면 {scene_index}: {scene_sentence}. "
        f"{style}. 캐릭터 머리/눈/옷은 절대 변경 금지. 텍스트/말풍선 없음."
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
    previous_meta = None

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
    logging.info(f"이미지 프롬프트 길이: {len(prompt)}")

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
            raise ValueError("이미지 응답에 URL 없음")
        return jsonify({"image_url": url, "prompt_used": prompt})
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "detail": str(e)}), 500

# ─────────────────────────────
# 로컬 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
