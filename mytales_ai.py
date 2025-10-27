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
당신은 5~9세 어린이를 위한 따뜻하고 리드미컬한 동화 작가입니다.
출력은 JSON 형식만 반환하세요:
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}}, ...], "ending":""}}

요구사항:
1. 입력값 반영: 이름={name}, 나이={age}, 성별={gender}, 훈육주제={topic}
2. 구성: 발단 → 전개 → 절정 → 결말 (총 5챕터, 각 챕터 2~4문장)
3. 등장: 의인화된 훈육 화신 + 조력자
4. 장면마다 감정/감각 묘사, 작은 규칙 포함
5. 교훈은 직접 말하지 말고 행동과 결과로 암시
6. 챕터마다 1문장짜리 시각적 삽화 설명 추가 (텍스트 금지)

반드시 JSON만 반환하세요.
""".strip()

    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a Korean children's story writer. Respond only in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=1200,
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            try:
                data = json.loads(cleaned)
            except:
                match = re.search(r'(\{[\s\S]*\})\s*$', cleaned)
                data = json.loads(match.group(1)) if match else None

            if isinstance(data, dict) and isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
                full_text = " ".join([c.get("paragraph", "") for c in data["chapters"]])
                if count_self_choice_indicators(full_text) >= 2:
                    return data
        except Exception:
            logging.exception("generate_story_text 실패")
            time.sleep(0.5)

    # fallback
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": "밝은 부엌에서 접시를 바라보는 아이"},
        {"title": "2. 친구 등장", "paragraph": "말하는 당근이 수줍게 인사했어요.", "illustration": "웃는 당근 친구와 아이"},
        {"title": "3. 첫 시도", "paragraph": "수지는 손끝으로 살짝 만져보았어요.", "illustration": "포크를 조심스레 드는 손"},
        {"title": "4. 조력자의 제안", "paragraph": "호박 요정이 작은 게임을 제안했어요.", "illustration": "호박 요정이 손짓하는 모습"},
        {"title": "5. 돌아온 선택", "paragraph": "집으로 돌아온 수지는 다시 한입 시도했어요.", "illustration": "창가에서 포크를 든 아이"}
    ]
    return {
        "title": title,
        "character": f"{name} ({age} {gender})",
        "chapters": chapters,
        "ending": "입가에 작은 미소가 번졌어요."
    }

# ─────────────────────────────
# 장면 묘사 및 이미지 프롬프트
# ─────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    try:
        prompt = f"""
이전 내용: {previous_summary}
현재 장면: {scene_text}
캐릭터 외형: {character_profile.get('visual', {}).get('canonical')}

한 문장으로 감정, 행동, 배경, 조명을 포함한 시각 묘사만 작성하세요.
텍스트/말풍선 금지.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write visual descriptions for Korean children's picture books."},
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
    style = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    return (
        f"{canonical}. 장면 {scene_index}: {scene_sentence}. "
        f"{style}. 캐릭터 외형(머리/눈/옷/비율) 절대 변경 금지. 텍스트/말풍선 없음."
    )

# ─────────────────────────────
# /generate-story
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
# /generate-image
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
    logging.info(f"[프롬프트] 이미지 {scene_index} 생성 중: {prompt[:120]}...")

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",  # ✅ 정사각형 비율로 수정
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
