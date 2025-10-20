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
    indicators = ["한 번", "한입", "한 입", "냄새", "손끝", "손가락", "스스로", "직접", "시도", "골라", "조심스레", "다시 한 번"]
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
# 캐릭터 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    if gender == "여자":
        hair = random.choice(["긴 갈색 웨이브 머리", "단발 검은 생머리", "짧은 밤색 머리"])
        outfit = random.choice(["빨간 원피스", "노란 셔츠와 멜빵", "하늘색 티셔츠와 분홍 치마"])
    else:
        hair = random.choice(["짧은 갈색 머리", "단정한 검은 머리", "부드러운 밤색 머리"])
        outfit = random.choice(["파란 티셔츠와 청바지", "초록 후드와 반바지", "노란 셔츠와 멜빵바지"])

    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face with soft cheeks; warm brown eyes; childlike proportions."
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
            "eyes": "따뜻한 갈색 눈",
            "proportions": "아이 같은 비율"
        }
    }

# ─────────────────────────────
# 동화 텍스트 생성
# ─────────────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    prompt = f"""
당신은 5~9세 어린이를 위한 따뜻하고 감정적인 동화 작가입니다.
입력값: 이름={name}, 나이={age}, 성별={gender}, 훈육주제={topic}

요구사항:
1. 구조: 발단 → 전개 → 절정 → 결말 (5개 챕터)
2. 등장: 주인공 + 의인화된 존재(훈육 주제의 상징) + 조력자
3. 주인공은 스스로 시도하고 배우며, 두 번 이상 행동 변화를 겪음
4. 교훈은 직접 말하지 말고, 행동·감정으로 암시
5. 각 챕터는 2~4문장, 마지막에 삽화용 시각 묘사 1문장 추가 (텍스트 금지)
6. 출력은 반드시 JSON:
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}},...], "ending":""}}
""".strip()

    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are '훈육 동화봇' writing Korean discipline stories in JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=1200,
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            data = json.loads(cleaned)

            if isinstance(data, dict) and len(data.get("chapters", [])) >= 5:
                text = " ".join([c.get("paragraph", "") for c in data["chapters"]])
                if count_self_choice_indicators(text) >= 2:
                    return data
        except Exception:
            logging.exception("generate_story_text 실패")
            time.sleep(0.5)

    # fallback
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작", "paragraph": f"{name}은(는) 채소를 보기만 해도 고개를 돌렸어요.", "illustration": "식탁 앞에서 머뭇거리는 아이"},
        {"title": "2. 초대", "paragraph": "작은 후추 요정이 나타나 채소 나라로 초대했어요.", "illustration": "요정이 반짝이는 빛으로 손짓하는 장면"},
        {"title": "3. 시도", "paragraph": f"{name}은(는) 브로콜리를 조심스레 만져보고 냄새를 맡았어요.", "illustration": "브로콜리를 코끝에 가져가는 아이"},
        {"title": "4. 깨달음", "paragraph": "조력자 호박이 '색깔마다 다른 힘'을 알려주었어요.", "illustration": "호박 조력자가 미소 짓는 장면"},
        {"title": "5. 귀환", "paragraph": f"{name}은(는) 작은 조각을 먹으며 고개를 끄덕였어요.", "illustration": "햇살 아래 포크를 든 아이"}
    ]
    return {
        "title": title,
        "character": f"{name} ({age} {gender})",
        "chapters": chapters,
        "ending": "수지의 마음에는 부드러운 용기가 피어났어요."
    }

# ─────────────────────────────
# 장면 묘사 + 이미지 프롬프트
# ─────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    gender = character_profile.get("gender", "")
    age = character_profile.get("age", "")
    try:
        prompt = f"""
이전 장면 요약: {previous_summary}
현재 장면: {scene_text}
캐릭터: {age}세 {gender} 아이
캐릭터 외형: {character_profile.get('visual', {}).get('canonical')}

→ 감정, 행동, 배경, 조명을 포함한 한 문장짜리 시각 묘사를 만드세요.
예: "여자 아이가 포크를 들고 햇살이 비치는 창가에 앉아 있어요. 따뜻한 빛이 얼굴을 감싸요."
텍스트/말풍선 금지.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write visual descriptions for children's picture books in Korean."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.25,
            max_tokens=180,
        )
        return clean_text(res.choices[0].message.content)
    except:
        logging.exception("묘사 실패")
        return f"{scene_text[:100]} ... 따뜻한 조명, 수채화 느낌."

def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    canonical = character_profile.get('visual', {}).get('canonical') or ""
    style = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 색감; 부드러운 그림체"
    gender = character_profile.get("gender", "아이")
    age = character_profile.get("age", "")

    return (
        f"{age}세 {gender} 아이. {canonical}. "
        f"장면 {scene_index}: {scene_sentence}. "
        f"스타일: {style}. "
        f"캐릭터 머리, 옷, 눈, 비율 유지. 텍스트/말풍선 금지."
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
            size="1024x1024",  # ✅ 정사각형으로 회전 방지
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
