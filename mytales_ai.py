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
    raise RuntimeError("OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ───────────────────────────────
# 유틸
# ───────────────────────────────
def clean_text(s):
    return re.sub(r"[\"<>]", "", s or "").strip()

def split_sentences_kor(text, expected=3):
    parts = [p.strip() for p in re.split(r"\n+|(?<=\.)\s+|(?<=\?|!)\s+", text) if p.strip()]
    if len(parts) < expected:
        joined = " ".join(parts)
        parts = [joined] if joined else []
    return parts

# ───────────────────────────────
# 캐릭터 설정 생성
# ───────────────────────────────
def generate_character_profile(name, age, gender):
    hair_options = ["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"]
    outfit_options = ["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"]
    hair = random.choice(hair_options)
    outfit = random.choice(outfit_options)
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
# 스토리 생성
# ───────────────────────────────
def generate_story_text(name, age, gender, topic):
    prompt = f"""
당신은 '훈육 동화봇'입니다. 대상은 5~9세 아동입니다. 말투는 친근하고 따뜻하며, 짧고 간결한 문장, 리듬감 있는 반복을 사용하세요.
입력: 이름={name}, 나이={age}, 성별={gender}, 훈육 주제={topic}.

요구사항:
1) 결과물은 한국어로 출력합니다.
2) 출력 형식:
제목: 한 줄
목차: 1~5 항목으로 간단히
주인공 소개 (짧게)
챕터 1~5를 순서대로 작성하되, 각 챕터는 짧은 문장 1~2개로 구성합니다.
각 챕터 끝에 '삽화 설명' 한 문장 포함 (아이가 상상할 수 있게 구체적)
3) 스토리는 도입→갈등→도움→해결→마무리 구조를 따릅니다.
4) 문장에 감각적 묘사, 감정 변화, 행동의 원인과 결과 포함
5) 어려운 표현이나 무서운 요소는 피해주세요.
6) 각 삽화 설명에는 캐릭터의 외형을 반드시 포함하세요.
캐릭터 외형: short canonical descriptor: "short curly brown hair; yellow shirt and blue overalls; round face with soft cheeks; warm brown almond eyes; childlike proportions"

마지막 출력은 JSON 형식으로 반환해주세요. 구조는 다음과 같습니다:
{{
  "title": "동화 제목",
  "character": "지우 (6살 여자)",
  "chapters": [
    {{
      "title": "챕터 제목",
      "paragraph": "짧은 문장 1~2개",
      "illustration": "삽화 설명 한 문장"
    }},
    ...
  ]
}}
"""
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are '훈육 동화봇', optimized to write warm Korean discipline stories for children aged 5-9."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.6,
        max_tokens=1000,
    )
    raw = res.choices[0].message.content.strip()

    # JSON 파싱
    import json
    json_data = json.loads(re.sub(r"```json|```", "", raw).strip())
    return json_data

# ───────────────────────────────
# 장면 묘사 생성
# ───────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    prompt = f"""
당신은 어린이 그림책 일러스트 전문가입니다. 다음 지침을 따르세요.
- 이전 요약: {previous_summary}
- 현재 장면(원문): {scene_text}
- 캐릭터 고정 외형: {character_profile['visual']['canonical']}
이 장면을 1개의 한국어 문장으로 시각적으로 구체하게 묘사하세요.
형식: 한 문장. 감정, 행동, 배경, 조명, 카메라 구도 중 2개 이상 포함. 말풍선/텍스트 금지.
"""
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You write concise Korean visual descriptions for children's picture book illustrations."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.3,
        max_tokens=200,
    )
    return clean_text(res.choices[0].message.content)

# ───────────────────────────────
# 이미지 프롬프트 구성
# ───────────────────────────────
def build_image_prompt_kor(scene_sentence, character_profile, scene_index, style_tags=None, previous_image_meta=None):
    canonical = character_profile['visual']['canonical']
    style_tags = style_tags or "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    meta_prev = f"이전 이미지 메타: {previous_image_meta}." if previous_image_meta else ""
    return (
        f"{canonical} {meta_prev} 장면 인덱스: {scene_index}. 장면 설명: {scene_sentence}. "
        f"스타일: {style_tags}. 카메라: 중간 샷 권장. 머리, 옷, 눈 색상 유지. 텍스트/말풍선 없음."
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
        return jsonify({"error": "name, age, gender, topic(또는 education_goal)을 모두 입력하세요."}), 400

    character_profile = generate_character_profile(name, age, gender)
    story_data = generate_story_text(name, age, gender, topic)

    # 장면 묘사 및 이미지 프롬프트 생성
    image_descriptions = []
    image_prompts = []
    accumulated = ""
    for idx, chapter in enumerate(story_data.get("chapters", []), start=1):
        para = chapter["paragraph"]
        prev = accumulated if accumulated else "이야기 시작"
        desc = describe_scene_kor(para, character_profile, idx, prev)
        prompt = build_image_prompt_kor(desc, character_profile, idx)
        image_descriptions.append(desc)
        image_prompts.append(prompt)
        accumulated += " " + para

    return jsonify({
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story": [c["paragraph"] for c in story_data.get("chapters", [])],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts
    })

# ───────────────────────────────
# 엔드포인트: /generate-image
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    logging.info("DEBUG /generate-image payload: %s", data)

    character_profile = data.get("character_profile") or data.get("characterProfile")
    scene_description = data.get("scene") or data.get("image_description") or data.get("scene_sentence")
    scene_index = data.get("scene_index") or data.get("index") or 1

    if not character_profile or not scene_description:
        return jsonify({
            "error": "character_profile과 scene_description 필드는 필수입니다.",
            "received": {
                "character_profile": bool(character_profile),
                "scene_description": bool(scene_description)
            }
        }), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        image_url = res.data[0].url if res and getattr(res, "data", None) else None
    except Exception as e:
        logging.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "detail": str(e)}), 500

    if not image_url:
        return jsonify({"error": "이미지 URL 없음"}), 500

    return jsonify({"image_url": image_url, "prompt_used": prompt})

# ───────────────────────────────
# 앱 실행
# ───────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
