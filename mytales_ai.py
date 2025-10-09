# ⚙️ 이 코드는 mytales_ai.py 로 저장하여 실행
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging

# ───────────────────────────────
# 1️⃣ 환경설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ───────────────────────────────
# 이름 조사 처리: 수정이는, 지효는 등
# ───────────────────────────────
def format_child_name(name: str) -> str:
    if not name:
        return name
    last_char = name[-1]
    last_code = ord(last_char) - 0xAC00
    has_final = (last_code % 28) != 0
    return f"{name}이는" if has_final else f"{name}는"

# ───────────────────────────────
# 이미지 프롬프트 정화기
# ───────────────────────────────
def sanitize_caption(caption: str, name="child", age="8", gender="child"):
    banned = [
        "blood", "kill", "dead", "violence", "weapon", "fight", "monster", "ghost", "drug", "alcohol",
        "beer", "wine", "sex", "photo", "realistic", "photoreal", "gore", "fear", "scary", "dark",
        "logo", "text", "brand", "war"
    ]
    replace = {
        "monster": "friendly imaginary friend",
        "fight": "face the challenge",
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
    words = caption.split()
    if len(words) > 28:
        caption = " ".join(words[:28])

    tail = ", same character and world, consistent outfit and hairstyle, pastel tone, soft watercolor storybook style, child-friendly, no text, no logos"
    if "storybook" not in caption.lower():
        caption += tail

    if not re.search(r"\b\d+[- ]?year[- ]?old\b|\b세\b", caption):
        caption = f"{age}-year-old {gender} named {name}, " + caption

    return caption

# ───────────────────────────────
# GPT에게 장면 묘사 요청 (이미지 프롬프트)
# ───────────────────────────────
def describe_scene(paragraph, name, age, gender, scene_index=0):
    try:
        character_desc = (
            f"The story is about a {age}-year-old {gender} named {name}, "
            "who has short wavy brown hair and wears a yellow shirt and blue overalls throughout the story."
        )

        prompt = f"""
You are a children's storybook illustrator. Please generate a DALL·E style English image prompt
based on the following scene description and story context.

📘 Character:
{character_desc}

📖 Scene {scene_index + 1}:
"{paragraph}"

🖼️ Instruction:
- Describe what should appear in the illustration.
- Include background, actions, emotions, environment, atmosphere, and any fantasy or playful elements.
- Use soft, child-friendly language and imagination.
- Output only a short English sentence that can be used as a prompt for DALL·E.
- Must include: pastel tone, watercolor, storybook style, child-safe, no text, no logos, same character and outfit
"""

        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert children's illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.7,
            max_tokens=300,
        )

        caption = res.choices[0].message.content.strip()
        return sanitize_caption(caption, name, age, gender)

    except Exception as e:
        log.error("❌ describe_scene GPT 호출 실패: %s", traceback.format_exc())
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

        prompt = f"""
너는 ‘훈육 동화봇’이라는 이름을 가진 이야기 마법사야.
아래 정보를 바탕으로, 아이가 공감하고 배울 수 있는 따뜻한 동화를 써줘.

🧒 입력 정보:
- 이름: {name}
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: '{goal}'

🎯 목표:
- ‘가르침’이 아닌 ‘이해와 공감’으로 배우게 해줘.
- 반복과 감정을 살리고, 귀여운 상상 요소를 추가해줘.

📘 동화 구성 형식:
1. 제목
2. 목차 (총 5개 챕터 제목)
3. 주인공 요약
4. 각 챕터는:
   - 제목
   - 2~3문장 내외 이야기
   - 삽화 설명

출력 형식:
```json
{{
  "title": "동화 제목",
  "chapters": [
    {{
      "title": "1장 제목",
      "paragraph": "이야기 내용",
      "illustration": "삽화 설명"
    }},
    ...
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
                {"role": "system", "content": "너는 어린이 훈육 동화를 만드는 이야기 마법사야."},
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
            paragraph = item.get("paragraph", "").strip()
            caption = describe_scene(paragraph, name, age, gender, scene_index=i)
            story.append({
                "title": item.get("title", ""),
                "paragraph": paragraph,
                "illustration": item.get("illustration", ""),
                "illustration_caption": caption
            })

        return Response(json.dumps({
            "title": story_data.get("title"),
            "character": story_data.get("character"),
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
            url = r.data[0].url
            return jsonify({"image_url": url}), 200
        except Exception:
            clean = sanitize_caption(prompt)
            try:
                r2 = attempt(clean)
                url = r2.data[0].url
                return jsonify({"image_url": url}), 200
            except Exception:
                fallback = sanitize_caption("child smiling warmly in a safe bright place, watercolor style")
                r3 = attempt(fallback)
                url = r3.data[0].url
                return jsonify({"image_url": url, "note": "fallback"}), 200

    except Exception as e:
        log.error("❌ generate-image error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 4️⃣ 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
