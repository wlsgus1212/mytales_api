from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging

# ───────────────────────────────
# 1️⃣ 환경 설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
log = logging.getLogger("mytales")
logging.basicConfig(level=logging.INFO)

# ───────────────────────────────
# 이름 조사 처리: 수정이는, 지효는 등
# ───────────────────────────────
def format_child_name(name: str) -> str:
    if not name:
        return name
    last_code = ord(name[-1]) - 0xAC00
    has_final = (last_code % 28) != 0
    return f"{name}이는" if has_final else f"{name}는"

# ───────────────────────────────
# 이미지 프롬프트 정화
# ───────────────────────────────
def sanitize_caption(caption: str, name="child", age="8", gender="child"):
    banned = ["blood","kill","dead","violence","weapon","fight","monster","ghost","drug",
              "alcohol","beer","wine","sex","photo","realistic","photoreal","gore",
              "fear","scary","dark","logo","text","brand","war"]
    replace = {
        "monster": "friendly imaginary creature",
        "fight": "playful challenge",
        "weapon": "magic wand",
        "blood": "red ribbon",
        "dark": "warm light",
        "fire": "gentle light",
        "realistic": "watercolor",
        "photo": "watercolor"
    }

    for k, v in replace.items():
        caption = re.sub(rf"\b{k}\b", v, caption, flags=re.I)
    for k in banned:
        caption = re.sub(rf"\b{k}\b", "", caption, flags=re.I)

    caption = re.sub(r'["\'`<>]', " ", caption).strip()
    caption = " ".join(caption.split()[:28])
    tail = ", same character and same world, consistent outfit and hairstyle, pastel tone, soft watercolor storybook style, child-friendly, no text, no logos"
    if "storybook" not in caption.lower():
        caption += tail

    if not re.search(r"\b\d+[- ]?year[- ]?old\b|\b세\b", caption):
        caption = f"{age}-year-old {gender} named {name}, " + caption
    return caption

# ───────────────────────────────
# 스타일 자동 생성
# ───────────────────────────────
def generate_character_style(name, age, gender):
    prompt = f"""
너는 동화 삽화 디자이너야. 다음 조건의 아이가 등장하는 동화를 위해 고정된 캐릭터 외형을 만들어줘.

- 이름: {name}
- 나이: {age}세
- 성별: {gender}

필수 출력 형식 (JSON):
{{
  "hair": "짧은 곱슬 갈색 머리",
  "clothes": "노란 셔츠와 파란 멜빵바지"
}}
"""
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "너는 동화 캐릭터 스타일을 디자인하는 전문가야."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.7,
        max_tokens=300,
    )
    content = res.choices[0].message.content.strip()
    content = re.sub(r"```json|```", "", content).strip()
    return json.loads(content)

# ───────────────────────────────
# GPT에게 이미지 프롬프트 생성 요청
# ───────────────────────────────
def describe_scene(paragraph, name, age, gender, scene_index, style):
    try:
        character_desc = (
            f"The story is about a {age}-year-old {gender} named {name}, "
            f"who has {style['hair']} and wears {style['clothes']} throughout the story."
        )

        prompt = f"""
You are a children's illustrator. Create a rich, vivid DALL·E prompt for this scene:

📘 Character:
{character_desc}

📖 Scene {scene_index+1}:
"{paragraph}"

🖼️ Include:
- Emotion, action, location, lighting, fantasy elements
- Pastel tone, watercolor, no text/logos, same character & outfit
Return a short English prompt only.
"""

        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a professional children's illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.7,
            max_tokens=300,
        )

        caption = res.choices[0].message.content.strip()
        return sanitize_caption(caption, name, age, gender)

    except Exception as e:
        log.error("❌ describe_scene GPT 실패: %s", traceback.format_exc())
        fallback = f"{age}-year-old {gender} named {name}, smiling in a warm storybook scene, watercolor style."
        return sanitize_caption(fallback, name, age, gender)

# ───────────────────────────────
# 2️⃣ 동화 생성 API
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        age = data.get("age", "")
        gender = data.get("gender", "").strip()
        goal = data.get("education_goal", "").strip()

        if not all([name, age, gender, goal]):
            return jsonify({"error": "모든 항목을 입력해주세요."}), 400

        name_particle = format_child_name(name)
        style = generate_character_style(name, age, gender)

        prompt = f"""
너는 ‘훈육 동화봇’이라는 이야기 마법사야. 아래 정보를 바탕으로 따뜻한 5장짜리 훈육 동화를 써줘:

🧒 이름: {name}, 나이: {age}세, 성별: {gender}, 주제: '{goal}'

📚 구성:
- 제목
- 목차 (5개)
- 각 장:
  ✍️ 제목 + 본문(2~3문장)
  🖼 삽화 설명

JSON 형식:
{{
  "title": "동화 제목",
  "chapters": [
    {{
      "title": "1장 제목",
      "paragraph": "이야기",
      "illustration": "삽화 설명"
    }} ... 총 5장
  ],
  "character": {{
    "name": "{name}",
    "age": "{age}",
    "gender": "{gender}"
  }}
}}
"""

        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "너는 훈육을 위한 동화를 짓는 이야기 마법사야."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.9,
            max_tokens=1600,
        )

        content = res.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        story = []
        for i, item in enumerate(story_data["chapters"]):
            paragraph = item.get("paragraph", "")
            caption = describe_scene(paragraph, name, age, gender, i, style)
            story.append({
                "title": item.get("title", ""),
                "paragraph": paragraph,
                "illustration": item.get("illustration", ""),
                "illustration_caption": caption
            })

        return Response(json.dumps({
            "title": story_data.get("title"),
            "character": story_data.get("character"),
            "character_style": style,
            "story": story
        }, ensure_ascii=False), content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("❌ generate-story error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 3️⃣ 이미지 생성 API
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        def attempt(p):
            return client.images.generate(model="dall-e-3", prompt=p, size="1024x1024", quality="standard")

        try:
            r = attempt(prompt)
            return jsonify({"image_url": r.data[0].url}), 200
        except:
            clean = sanitize_caption(prompt)
            try:
                r2 = attempt(clean)
                return jsonify({"image_url": r2.data[0].url}), 200
            except:
                fallback = sanitize_caption("child in warm bright place, watercolor")
                r3 = attempt(fallback)
                return jsonify({"image_url": r3.data[0].url, "note": "fallback"}), 200

    except Exception as e:
        log.error("❌ generate-image error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 4️⃣ 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
