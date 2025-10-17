from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

# ───────────────────────────────
# 환경 설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ───────────────────────────────
# 유틸 함수
# ───────────────────────────────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def split_sentences_kor(text, expected=5):
    parts = [p.strip() for p in re.split(r'\n+|(?<=\.)\s+|(?<=\?|!)\s+', text) if p.strip()]
    if len(parts) < expected:
        joined = " ".join(parts)
        parts = [joined] if joined else []
    return parts

def count_self_choice_indicators(text):
    indicators = ["한 번", "한입", "한 입", "냄새", "손끝", "손가락", "스스로", "직접", "시도", "골라", "골라보다", "조심스레", "조심히", "다시 한 번", "다시 한입"]
    return sum(text.count(ind) for ind in indicators)

# ───────────────────────────────
# 캐릭터 프로필 생성
# ───────────────────────────────
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

# ───────────────────────────────
# 동화 텍스트 생성 (GPT)
# ───────────────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    base_prompt = f"""
당신은 '훈육 동화봇'입니다. 대상은 5~9세 아동이며, 말투는 따뜻하고 리드미컬합니다.
이야기는 의인화된 존재(훈육 주제의 화신)와 조력자가 등장하는 모험 서사로, 주인공이 스스로 여러 번 작은 시도를 통해 변화에 다가가는 형식이어야 합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 훈육 주제={topic}.

반드시 지킬 사항:
1) 구조: 제목, 목차(5개), 주인공 소개, 챕터1~5, 마무리(행동으로 암시).
2) 각 챕터는 1~3문장. 감정 변화, 감각 묘사 포함.
3) 의인화된 존재 + 조력자 필수.
4) '스스로 시도' 장면 2회 이상 필수.
5) 교훈은 직접 언급 금지 (행동으로 암시).
6) 각 챕터 끝에 삽화 설명 1문장.
7) JSON 형식: 
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}},...], "ending":""}}
"""

    for attempt in range(max_attempts):
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are '훈육 동화봇' writing Korean discipline stories in JSON."},
                {"role": "user", "content": base_prompt.strip()}
            ],
            temperature=0.6,
            max_tokens=1200,
        )
        raw = res.choices[0].message.content.strip()

        try:
            cleaned = re.sub(r"```(?:json)?", "", raw).strip()
            data = json.loads(cleaned)
        except:
            match = re.search(r'\{[\s\S]*\}\s*$', raw)
            data = json.loads(match.group(0)) if match else None

        if not data: continue

        chapters = data.get("chapters", [])
        paragraphs = " ".join(c.get("paragraph", "") for c in chapters)
        if len(chapters) >= 5 and count_self_choice_indicators(paragraphs) >= 2:
            return data

    return {"title": f"{name}의 이야기", "character": f"{name} ({age} {gender})", "chapters": [], "ending": ""}

# ───────────────────────────────
# 장면 묘사 → 이미지 프롬프트 생성
# ───────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    prompt = f"""
당신은 어린이 그림책 일러스트 전문가입니다.
- 이전 요약: {previous_summary}
- 현재 장면: {scene_text}
- 캐릭터 외형: {character_profile['visual']['canonical']}
→ 감정, 행동, 배경, 조명 또는 카메라 구도 중 최소 2개 포함하여 1문장 묘사하세요. 말풍선/텍스트 금지.
"""
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Write Korean visual descriptions for children's picture books."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.25,
        max_tokens=200,
    )
    return clean_text(res.choices[0].message.content)

def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    canonical = character_profile['visual']['canonical']
    style_tags = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    meta_prev = f"이전 이미지 메타: {previous_meta}." if previous_meta else ""
    return (
        f"{canonical} {meta_prev} 장면 인덱스: {scene_index}. 장면 설명: {scene_sentence}. "
        f"스타일: {style_tags}. 카메라: 중간 샷 권장. 캐릭터 외형은 절대 변경하지 마세요. 텍스트/말풍선 금지."
    )

# ───────────────────────────────
# 엔드포인트: /generate-story
# ───────────────────────────────
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
        "ending": story_data.get("ending")
    })

# ───────────────────────────────
# 엔드포인트: /generate-image
# 이미지 1장씩 생성
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    character_profile = data.get("character_profile") or data.get("character")
    scene_description = (data.get("image_description") or data.get("scene") or "")
    scene_index = data.get("scene_index") or 1

    # 문자열이면 dict로 파싱
    if isinstance(character_profile, str):
        try:
            character_profile = json.loads(character_profile)
        except json.JSONDecodeError:
            return jsonify({"error": "character_profile이 JSON 형식이 아닙니다."}), 400

    if not isinstance(character_profile, dict):
        return jsonify({"error": "character_profile은 dict 또는 JSON 문자열이어야 합니다."}), 400

    if not scene_description:
        return jsonify({"error": "scene_description 필수"}), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        image_url = res.data[0].url
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "prompt_used": prompt}), 500

    return jsonify({"image_url": image_url, "prompt_used": prompt})

# ───────────────────────────────
# 앱 실행
# ───────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
