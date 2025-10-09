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
# 조사 자동 보정 (희진 → 희진이는)
# ───────────────────────────────
def with_particle(name: str) -> str:
    if not name:
        return name
    last = ord(name[-1]) - 44032
    has_final = (last % 28) != 0
    return f"{name}은" if has_final else f"{name}는"

# ───────────────────────────────
# 이미지 캡션 정화기 (금지어 치환 + 안전 꼬리표)
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
    # ✅ string 인자(capiton) 추가
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
# 동화 장면 기반 이미지 캡션 생성
# ───────────────────────────────
def build_caption(paragraph, name, age, gender):
    act, bg, emo = "standing", "in a bright place", "gentle smile"
    if any(k in paragraph for k in ["달렸", "뛰"]): act = "running"
    elif "걷" in paragraph: act = "walking"
    elif "바라보" in paragraph: act = "looking"
    if "숲" in paragraph: bg = "in a sunny forest"
    elif "바다" in paragraph: bg = "by a calm sea"
    elif "하늘" in paragraph or "별" in paragraph: bg = "under a starry sky"
    elif "학교" in paragraph: bg = "at a cozy school"
    elif "성" in paragraph: bg = "near a fairytale castle"
    if "웃" in paragraph: emo = "happy smile"
    elif "두려" in paragraph: emo = "slightly worried but brave"
    elif "놀라" in paragraph: emo = "curious face"
    raw = f"{age}-year-old {gender} named {name}, {act}, {bg}, {emo}, pastel colors, warm gentle light, soft watercolor storybook style, child-friendly"
    return sanitize_caption(raw, name, age, gender)

# ───────────────────────────────
# 2️⃣ /generate-story : 동화 텍스트 생성
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
        name = data.get("name","").strip()
        age = data.get("age","")
        gender = data.get("gender","").strip()
        goal = data.get("education_goal","").strip()
        if not all([name, age, gender, goal]):
            return jsonify({"error":"모든 항목을 입력해주세요."}),400

        name_particle = with_particle(name)

        prompt = f"""
너는 5~8세 어린이를 위한 감성적이고 창의적인 동화 작가야.
다음 정보를 바탕으로 따뜻하고 상상력 넘치는 이야기를 써줘.

- 이름: {name}
- 나이: {age}세
- 성별: {gender}
- 주제: '{goal}'

💡 목표:
아이에게 가르침이 아닌 깨달음으로 전달되는 교훈형 동화.
읽는 아이가 스스로 "아, 나도 저렇게 해야겠다"라고 느끼게 해줘.

📚 구성 규칙:
1. 총 6개의 장면으로 구성된 완전한 이야기.
2. 각 장면은 아이의 시선에서 2~3문장.
3. 각 장면마다 감정 변화와 행동이 드러나야 함.
4. 구조:
   1장: 일상/상상의 시작
   2장: 문제의 발견
   3장: 시도와 실패
   4장: 마법적 전환점(깨달음의 씨앗)
   5장: 행동 변화
   6장: 따뜻한 결말과 교훈적 자각
5. 교훈은 직접 말하지 말고, 아이의 행동으로 보여줘.
6. 어두운 내용, 폭력, 공포, 현실의 죽음·범죄 등은 절대 금지.
7. 밝고 희망적, 유머와 상상력이 섞인 톤 유지.

출력 형식(JSON 배열):
[
  {{"paragraph": "첫 번째 장면"}},
  {{"paragraph": "두 번째 장면"}},
  {{"paragraph": "세 번째 장면"}},
  {{"paragraph": "네 번째 장면"}},
  {{"paragraph": "다섯 번째 장면"}},
  {{"paragraph": "여섯 번째 장면 (결말)"}}
]
"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"너는 어린이 눈높이에 맞춰 교훈적이고 상상력 있는 이야기를 쓰는 작가야."},
                {"role":"user","content":prompt.strip()}
            ],
            temperature=0.9,
            max_tokens=1600,
        )

        content = res.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        story = []
        for i, item in enumerate(story_data):
            paragraph = item.get("paragraph","").strip() if isinstance(item,dict) else str(item)
            caption = build_caption(paragraph, name, age, gender)
            story.append({"paragraph": paragraph, "illustration_caption": caption})

        return Response(json.dumps({"story":story}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("❌ generate-story error: %s", traceback.format_exc())
        return jsonify({"error":str(e)}),500

# ───────────────────────────────
# 3️⃣ /generate-image : DALL·E 3 이미지 생성 (정화 재시도 포함)
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error":"prompt is required"}),400

        def attempt(p):
            return client.images.generate(model="dall-e-3", prompt=p, size="1024x1024", quality="standard")

        try:
            r = attempt(prompt)
            url = r.data[0].url
            return jsonify({"image_url":url}),200
        except Exception:
            clean = sanitize_caption(prompt)
            try:
                r2 = attempt(clean)
                url = r2.data[0].url
                return jsonify({"image_url":url}),200
            except Exception:
                fallback = sanitize_caption("child smiling warmly in a safe bright place, watercolor style")
                r3 = attempt(fallback)
                url = r3.data[0].url
                return jsonify({"image_url":url, "note":"fallback"}),200

    except Exception as e:
        log.error("❌ generate-image error: %s", traceback.format_exc())
        return jsonify({"error":str(e)}),500

# ───────────────────────────────
# 4️⃣ 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
