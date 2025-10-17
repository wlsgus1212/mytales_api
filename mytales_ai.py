from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

# ───────────────────────
# 초기 설정
# ───────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ───────────────────────
# 유틸 함수
# ───────────────────────
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
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, dict):
                return parsed
        except:
            pass
        # fallback
        return {
            "name": None,
            "age": None,
            "gender": None,
            "style": obj,
            "visual": {
                "canonical": obj,
                "hair": "",
                "outfit": "",
                "face": "",
                "eyes": "",
                "proportions": ""
            }
        }
    return None

# ───────────────────────
# 캐릭터 생성
# ───────────────────────
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

# ───────────────────────
# 동화 생성 (GPT)
# ───────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    base_prompt = f"""
당신은 '훈육 동화봇'입니다. 대상은 5~9세 아동이며, 동화는 아이의 눈높이에 맞춰 감정 중심의 리드미컬한 말투로 작성되어야 합니다.

요구사항:
1. 주인공은 "{topic}"으로 인해 불편한 감정을 느낍니다.
2. 의인화된 존재와 조력자가 등장합니다. (조력자는 동일하게 유지)
3. 주인공은 스스로 2번 이상의 작은 시도를 합니다.
4. 직접적인 교훈을 말하지 말고, 행동으로 암시하세요.
5. 쉬운 단어와 짧은 문장, 풍부한 감정, 감각적 표현 사용.
6. 각 챕터는 1~3문장으로 구성, 마지막에 삽화 설명 1문장.
7. JSON 형식 출력 필수:
{{
"title": "...",
"character": "...",
"chapters": [
  {{"title": "...", "paragraph": "...", "illustration": "..."}},
  ...
],
"ending": "..."
}}

입력 정보:
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {topic}
"""
    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are '훈육 동화봇' writing Korean discipline stories for children in JSON."},
                    {"role": "user", "content": base_prompt.strip()}
                ],
                temperature=0.6,
                max_tokens=1200,
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r"```(?:json)?", "", raw).strip()
            data = json.loads(cleaned)
        except Exception:
            match = re.search(r'\{[\s\S]*\}\s*$', raw)
            try:
                data = json.loads(match.group(0)) if match else None
            except:
                data = None

        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
            paragraph_text = " ".join([c.get("paragraph", "") for c in data["chapters"]])
            if count_self_choice_indicators(paragraph_text) >= 2:
                return data

        time.sleep(0.5)

    # fallback
    return {
        "title": f"{name}의 작은 모험",
        "character": f"{name} ({age} {gender})",
        "chapters": [],
        "ending": ""
    }

# ───────────────────────
# 장면 묘사 → 이미지 프롬프트
# ───────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    prompt = f"""
당신은 한국 아동 그림책 전문 일러스트 작가입니다.
이전까지 줄거리: {previous_summary}
현재 장면: {scene_text}
캐릭터 외형: {character_profile.get('visual', {}).get('canonical')}

→ 감정, 행동, 배경, 조명, 구도 중 2가지 이상을 포함한 1문장 삽화 설명 작성. 말풍선/텍스트 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You write Korean children's illustration descriptions."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.3,
            max_tokens=200,
        )
        return clean_text(res.choices[0].message.content)
    except:
        return f"{scene_text[:120]}... (따뜻한 조명, 부드러운 수채화 느낌)"

def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    canonical = character_profile.get('visual', {}).get('canonical', "")
    style_tags = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    meta_prev = f"이전 이미지 메타: {previous_meta}." if previous_meta else ""
    return (
        f"{canonical} {meta_prev} 장면 인덱스: {scene_index}. 장면 설명: {scene_sentence}. "
        f"스타일: {style_tags}. 카메라: 중간 샷 권장. 캐릭터 생김새는 절대 변경하지 마세요. 텍스트/말풍선 금지."
    ).strip()

# ───────────────────────
# API: /generate-story
# ───────────────────────
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
    chapters = story_data.get("chapters", []) or []

    image_descriptions, image_prompts = [], []
    accumulated, previous_meta = "", None

    for idx, chapter in enumerate(chapters, start=1):
        para = chapter.get("paragraph", "")
        prev = accumulated or "이야기 시작"
        desc = describe_scene_kor(para, character_profile, idx, prev)
        prompt = build_image_prompt_kor(desc, character_profile, idx, previous_meta)
        image_descriptions.append(desc)
        image_prompts.append(prompt)
        accumulated += " " + para
        previous_meta = {"style_tags": "부드러운 수채화; 따뜻한 조명"}

    return jsonify({
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in chapters],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts,
        "ending": story_data.get("ending") or ""
    })

# ───────────────────────
# API: /generate-image
# ───────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    raw_cp = data.get("character_profile") or data.get("character") or data.get("characterProfile")
    scene_description = data.get("image_description") or data.get("scene") or data.get("scene_description") or data.get("scene_sentence") or ""
    scene_index = data.get("scene_index") or data.get("index") or 1

    character_profile = ensure_character_profile(raw_cp)
    if not character_profile:
        return jsonify({"error": "character_profile이 필요합니다."}), 400
    if not scene_description:
        return jsonify({"error": "scene_description이 필요합니다."}), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",  # 세로형
            quality="standard",
            n=1
        )
        image_url = res.data[0].url if res and res.data else None
        if not image_url:
            return jsonify({"error": "이미지 URL 없음", "prompt_used": prompt}), 500
        return jsonify({"image_url": image_url, "prompt_used": prompt})
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "detail": str(e), "prompt_used": prompt}), 500

# ───────────────────────
# 앱 실행
# ───────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
