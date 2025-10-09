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
# 이미지 프롬프트 정화
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
# 장면 묘사 → 이미지 프롬프트로 변환
# ───────────────────────────────
def describe_scene(paragraph, name, age, gender):
    character = f"A {age}-year-old {gender} named {name}, with short wavy brown hair, wearing a yellow shirt and blue overalls"

    if any(k in paragraph for k in ["달렸", "뛰", "전력", "급히"]):
        action = "is running with excitement"
    elif "걷" in paragraph:
        action = "is walking slowly and carefully"
    elif any(k in paragraph for k in ["바라보", "쳐다보", "응시"]):
        action = "is gazing curiously at something"
    elif any(k in paragraph for k in ["앉", "쉬", "멈췄"]):
        action = "is sitting down and resting"
    else:
        action = "is calmly standing"

    if "숲" in paragraph:
        background = "in a sunny, magical forest where light peeks through the trees"
    elif "바다" in paragraph:
        background = "on a peaceful beach with gentle waves"
    elif "하늘" in paragraph or "별" in paragraph:
        background = "under a sky filled with twinkling stars"
    elif "학교" in paragraph:
        background = "in a cozy and colorful classroom"
    elif "성" in paragraph:
        background = "near a grand fairytale castle"
    elif "공원" in paragraph:
        background = "in a quiet park with blooming flowers"
    else:
        background = "in a bright and warm open space"

    if any(k in paragraph for k in ["기뻐", "행복", "웃"]):
        emotion = "with a big, joyful smile"
    elif any(k in paragraph for k in ["무서", "두려", "불안"]):
        emotion = "looking slightly scared but trying to be brave"
    elif any(k in paragraph for k in ["놀라", "깜짝"]):
        emotion = "with wide eyes full of surprise"
    elif any(k in paragraph for k in ["슬퍼", "울"]):
        emotion = "with teary eyes but a hopeful heart"
    else:
        emotion = "with a calm and gentle expression"

    scene = f"{character} {action} {background}, {emotion}. The illustration is drawn in soft pastel tones with a watercolor storybook style. No text or logos. Same outfit and hairstyle should be used to maintain consistency with previous scenes."

    return sanitize_caption(scene, name, age, gender)

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
너의 임무는 5~9세 어린이를 위한 따뜻하고 공감 가는 동화를 만드는 거야.
아래 정보를 바탕으로, 아이가 스스로 느끼고 배울 수 있는 훈육 동화를 써줘.

🧒 입력 정보:
- 이름: {name}
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: '{goal}'

🎯 목표:
- ‘가르침’이 아닌 ‘이해와 공감’으로 배우게 해줘.
- 아이의 감정에 초점을 맞추고, 반복과 리듬을 살려 자연스럽게 몰입하게 해줘.
- 이야기 중간마다 귀여운 동물, 장난감, 자연 요소를 활용해서 상상력을 자극해줘.

📘 동화 구성 형식:
1. 제목
2. 목차 (총 5개 챕터 제목)
3. 주인공 정보 요약 (이름/나이/성별)
4. 각 챕터는 다음 순서로:
   - ✍️ 챕터 번호 + 제목
   - 2~3문장 내외의 따뜻한 이야기
   - 🖼 삽화 설명 (동화적이고 상상력 넘치게)

출력 형식은 아래 JSON 형식으로 해줘:
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
    {{
      "title": "5장 제목",
      "paragraph": "결말 내용",
      "illustration": "삽화 설명"
    }}
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
                {"role": "system", "content": "너는 어린이를 위한 따뜻한 훈육 동화를 만드는 이야기 마법사야."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.9,
            max_tokens=1600,
        )

        content = res.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        story = []
        for item in story_data["chapters"]:
            paragraph = item.get("paragraph", "").strip()
            caption = describe_scene(paragraph, name, age, gender)
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
