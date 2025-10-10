from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging, random

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
# 이름 조사 처리 (수정이는 / 지효는 등)
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
    if not caption:
        caption = ""
    banned = [
        "blood","kill","dead","violence","weapon","fight","monster","ghost","drug","alcohol",
        "beer","wine","sex","photo","realistic","photoreal","gore","fear","scary","dark",
        "logo","text","brand","war"
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

    tail = ", same character and same world, consistent outfit and hairstyle, pastel tone, soft watercolor storybook style, child-friendly, no text, no logos"
    if "storybook" not in caption.lower():
        caption += tail

    if not re.search(r"\b\d+[- ]?year[- ]?old\b|\b세\b", caption):
        caption = f"{age}-year-old {gender} named {name}, " + caption
    return caption

# ───────────────────────────────
# GPT 이미지 묘사 생성 함수
# ───────────────────────────────
def describe_scene(paragraph, name, age, gender, style_desc="", scene_index=0):
    try:
        prompt = f"""
You are an expert illustrator for children's storybooks. 
Please write a detailed, vivid, DALL·E-style image prompt for the following scene. 
Include the child’s name, consistent outfit and hairstyle, actions, facial expressions, background, any fantasy or imaginary characters (like vegetables or animal friends), and emotional tone.

💁 Character Info:
- {age}-year-old {gender} named {name}
- Outfit & Hairstyle: {style_desc}

📖 Scene {scene_index + 1}:
"{paragraph}"

🎨 Style:
pastel tone, watercolor, storybook style, child-safe, same character and world, no text, no logos.

✍️ Output format:
Return a single English sentence that vividly describes the scene for image generation.
"""

        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert children's illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.8,
            max_tokens=400,
        )

        caption = res.choices[0].message.content.strip()
        return sanitize_caption(caption, name, age, gender)

    except Exception as e:
        log.error("❌ describe_scene GPT 오류: %s", traceback.format_exc())
        fallback = f"{age}-year-old {gender} named {name}, smiling in a storybook watercolor scene."
        return sanitize_caption(fallback, name, age, gender)

# ───────────────────────────────
# 동화 생성
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

        # 옷 & 머리 랜덤 스타일 고정
        hair_options = ["short curly brown hair", "long straight black hair", "wavy chestnut hair"]
        outfit_options = ["yellow shirt and blue overalls", "red polka-dot dress", "green hoodie and beige pants"]
        hair = random.choice(hair_options)
        outfit = random.choice(outfit_options)
        style_desc = f"{hair}, wearing {outfit}"

        prompt = f"""
너는 ‘훈육 동화봇’이라는 이름의 이야기 마법사야.
5~9세 어린이를 위한 공감 가득한 동화를 만들고, 아이가 스스로 느끼며 배울 수 있게 도와줘.

📥 정보:
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {goal}

🎯 목표:
- 감정 표현 중심, 반복 구조, 따뜻한 표현
- 아이가 '아하!' 하고 스스로 깨달을 수 있는 이야기
- 각 장면에 말하는 동물, 장난감, 채소 친구, 자연 요소 등 상상력 자극 요소 포함

📘 형식:
- 제목
- 목차 (5개 장면)
- 주인공 정보
- 각 장면: 제목, 이야기, 삽화 설명

JSON 형식으로 아래처럼 출력해줘:
```json
{{
  "title": "동화 제목",
  "chapters": [
    {{
      "title": "장면 1 제목",
      "paragraph": "이야기 본문",
      "illustration": "삽화 설명"
    }},
    ...
  ],
  "character": {{
    "name": "{name}",
    "age": "{age}",
    "gender": "{gender}",
    "style": "{style_desc}"
  }}
}}
"""

        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "너는 어린이를 위한 상상력 풍부한 동화를 만드는 이야기 마법사야."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.95,
            max_tokens=1800,
        )

        content = res.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)
        style_desc = story_data["character"].get("style", style_desc)

        story = []
        for i, item in enumerate(story_data["chapters"]):
            paragraph = item.get("paragraph", "").strip()
            caption = describe_scene(paragraph, name, age, gender, style_desc=style_desc, scene_index=i)
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
# 이미지 생성
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
# 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
