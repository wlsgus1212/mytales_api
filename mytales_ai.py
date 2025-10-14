from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging

# ───────────────────────────────
# 환경 설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)

# ───────────────────────────────
# 한글 이름 조사 자동 처리 함수 (은/는, 이/가 등)
# ───────────────────────────────
def format_korean_name_with_josa(name, josa_pair=("은", "는")):
    code = ord(name[-1]) - 0xAC00
    if code < 0 or code > 11171:
        return name + josa_pair[1]
    return name + (josa_pair[0] if code % 28 else josa_pair[1])

# ───────────────────────────────
# 캐릭터 설정 생성
# ───────────────────────────────
def generate_character_profile(name, age, gender):
    hair_options = ["짧은 갈색 곱슬머리", "긴 생머리 검은 머리", "웨이비한 밤색 머리"]
    outfit_options = ["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"]
    hair = random.choice(hair_options)
    outfit = random.choice(outfit_options)
    style = f"{hair}, 착용: {outfit}"

    return {
        "name_en": name,
        "age": age,
        "gender": gender,
        "style": style,
        "visual": {
            "face": "부드러운 볼의 둥근 얼굴",
            "eyes": "따뜻한 갈색 아몬드형 눈",
            "hair": hair,
            "outfit": outfit,
            "proportions": "아이 같은 비율"
        }
    }

# ───────────────────────────────
# 장면 설명 생성
# ───────────────────────────────
def describe_scene(paragraph, character_profile, previous_scenes_text):
    name = character_profile.get("name_en", "아이")
    age = character_profile.get("age", "8")
    gender = character_profile.get("gender", "아이")
    style = character_profile.get("style", "")

    context = previous_scenes_text if previous_scenes_text else "이야기의 시작 장면입니다."

    prompt = f"""
당신은 어린이 그림책 일러스트 전문가입니다.
지금까지의 이야기 요약: {context}
다음 장면: "{paragraph}"

이 장면을 그대로 묘사한 한 문장의 한국어 일러스트 설명을 작성하세요.
- 캐릭터의 감정, 행동, 배경을 생생하고 구체적으로 포함하세요.
- 캐릭터 외형을 유지하세요: {age}살 {gender} {name}, 복장과 헤어스타일: {style}.
- 자연스럽고 따뜻한 톤, 아이 친화적으로 묘사하세요.
- 텍스트, 말풍선, 자막은 포함하지 마세요.
"""

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert children's illustrator who writes concise Korean visual descriptions."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.3,
        max_tokens=180,
    )

    sentence = res.choices[0].message.content.strip()
    sentence = re.sub(r"[\"<>]", "", sentence)
    return sentence

# ───────────────────────────────
# 이미지 프롬프트 생성
# ───────────────────────────────
def build_image_prompt(scene_sentence, character_profile):
    visual = character_profile.get("visual", {})
    name = character_profile.get("name_en", "아이")
    age = character_profile.get("age", "8")
    gender = character_profile.get("gender", "아이")

    face = visual.get("face", "")
    eyes = visual.get("eyes", "")
    hair = visual.get("hair", "")
    outfit = visual.get("outfit", "")
    proportions = visual.get("proportions", "")

    prompt = (
        f"장면 묘사: {scene_sentence}. "
        f"주인공은 {age}살 {gender} {name}이며, 외형: {face}, {hair}, {eyes}, 복장: {outfit}, 비율: {proportions}. "
        f"부드러운 수채화 스타일, 따뜻한 조명, 아동 친화적, 일관된 외형 유지, 텍스트나 말풍선 없음."
    )
    return prompt.strip()

# ───────────────────────────────
# 동화 생성 엔드포인트
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    character_profile = generate_character_profile(name, age, gender)

    story_prompt = f"""
다음 정보를 바탕으로 어린이 동화의 핵심 장면 3개를 '한국어'로 각각 한 문장씩 만들어 주세요.
각 문장은 그림책 일러스트 한 장면을 묘사할 수 있도록 시각적이어야 합니다.

캐릭터: 이름={name}, 나이={age}세, 성별={gender}.
교육 목표: {goal}.
"""

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You generate concise Korean story scene sentences for children's picture books."},
            {"role": "user", "content": story_prompt.strip()}
        ],
        temperature=0.6,
        max_tokens=600,
    )

    raw = res.choices[0].message.content.strip()

    # 줄바꿈 기준 우선 → 없으면 종결 문장 기준
    if "\n" in raw:
        story_paragraphs = [s.strip() for s in raw.strip().split("\n") if s.strip()]
    else:
        story_paragraphs = re.findall(r'[^.!?]+[.!?]', raw.strip())

    # 예외 처리: 문장이 부족할 경우 기본 예시
    if len(story_paragraphs) < 3:
        base_name = format_korean_name_with_josa(name)
        story_paragraphs = [
            f"{base_name} 노란 램프 아래에서 조용히 책을 들여다본다.",
            f"창밖에 빗방울이 떨어지고, {base_name} 창밖을 응시하며 생각에 잠긴다.",
            f"따뜻한 바람이 불어와 {base_name} 머리카락을 살랑거리게 한다."
        ]

    # 장면별 묘사 생성
    image_descriptions = []
    accumulated_text = ""
    for p in story_paragraphs:
        desc = describe_scene(p, character_profile, accumulated_text)
        image_descriptions.append(desc)
        accumulated_text = (accumulated_text + " " + p).strip()

    # 이미지 생성용 프롬프트
    image_prompts = [build_image_prompt(desc, character_profile) for desc in image_descriptions]

    return jsonify({
        "story": story_paragraphs,
        "character_profile": character_profile,
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts
    })

# ───────────────────────────────
# 이미지 생성 엔드포인트
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    logging.info("DEBUG /generate-image payload: %s", data)

    character_profile = data.get("character_profile") or data.get("characterProfile")
    scene_description = data.get("image_description") or data.get("imageDescription") or data.get("scene_sentence") or data.get("sceneSentence")

    if not character_profile or not scene_description:
        return jsonify({
            "error": "캐릭터 정보와 장면 설명이 필요합니다.",
            "received": {
                "character_profile": bool(character_profile),
                "scene_description": bool(scene_description)
            }
        }), 400

    prompt = build_image_prompt(scene_description, character_profile)

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )

        image_url = res.data[0].url if res and getattr(res, "data", None) else None

        if not image_url:
            logging.error("❌ DALL·E 응답에 URL 없음: %s", res)
            return jsonify({"error": "이미지 생성 실패"}), 500

        return jsonify({"image_url": image_url, "prompt_used": prompt})

    except Exception as e:
        logging.exception("❌ 이미지 생성 중 오류 발생")
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 앱 실행
# ───────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
