from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback

# ────────────────────────────────────────────────
# 1️⃣ 환경 설정
# ────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ────────────────────────────────────────────────
# 2️⃣ 자연스러운 조사 보정
# ────────────────────────────────────────────────
def with_particle(name: str) -> str:
    if not name:
        return name
    last = name[-1]
    code = ord(last) - 44032
    has_final = (code % 28) != 0
    soft = ["현","민","진","윤","린","빈","원","연","훈","준","은","선","안","환"]
    if last in soft:
        return f"{name}이는"
    elif not has_final:
        return f"{name}는"
    else:
        return f"{name}은"

# ────────────────────────────────────────────────
# 3️⃣ 이미지 프롬프트 자동 생성
# ────────────────────────────────────────────────
def build_image_prompt(paragraph, name, age, gender):
    base = f"{age}-year-old {gender} child named {name}"
    style = "soft watercolor storybook style, warm pastel colors, cinematic composition"

    # 핵심 장면 추출
    if "나비" in paragraph:
        scene = "a glowing magical butterfly meeting the child in a forest"
    elif "바다" in paragraph:
        scene = "the child near gentle blue ocean waves"
    elif "별" in paragraph:
        scene = "the child watching bright stars in the night sky"
    elif "눈" in paragraph:
        scene = "the child playing in softly falling snow"
    elif "꽃" in paragraph:
        scene = "the child surrounded by blooming flowers"
    elif "왕" in paragraph or "공주" in paragraph:
        scene = "the child wearing a royal outfit in a fairytale castle"
    else:
        scene = "the child in a warm natural background"

    # 감정 추론
    if any(k in paragraph for k in ["웃","기뻐","밝","신나","즐겁"]):
        emotion = "smiling happily"
    elif any(k in paragraph for k in ["걱정","두려","무섭","불안"]):
        emotion = "looking slightly worried but hopeful"
    elif any(k in paragraph for k in ["놀라","깜짝","호기심","궁금"]):
        emotion = "showing curiosity and wonder"
    elif any(k in paragraph for k in ["용기","결심","도전","해냈"]):
        emotion = "looking brave and confident"
    else:
        emotion = "gentle and calm"

    return f"{base}, {emotion}, {scene}, {style}"

# ────────────────────────────────────────────────
# 4️⃣ /generate-story : 이야기 → 이미지 명령문 자동 변환
# ────────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = data.get("name","").strip()
    age = data.get("age","")
    gender = data.get("gender","").strip()
    goal = data.get("education_goal","").strip()
    if not all([name,age,gender,goal]):
        return jsonify({"error":"모든 항목을 입력해주세요."}),400

    name_particle = with_particle(name)

    # GPT 프롬프트 (텍스트 전용)
    prompt = f"""
너는 5~8세 어린이를 위한 감성 동화 작가야.  
'{goal}' 주제를 자연스럽게 담은 짧은 이야기를 써줘.  
이야기는 현실·판타지 등 어떤 세계관으로도 시작 가능하며 다음 요건을 지켜라.

1️⃣ 아이의 감정 흐름은 평온→갈등→깨달음→따뜻함 으로 이어져야 한다.  
2️⃣ '혼란', '불안정' 등 어려운 단어 금지. 쉬운 말만 사용.  
3️⃣ 교훈은 설교 형태가 아니라 행동이나 상징으로 표현.  
4️⃣ 각 장면은 3~4 문장으로 구성. (총 6 장면 정도)  
5️⃣ 반복되는 리듬 문장 1~2회 포함 (예: "후우, 바람이 속삭였어요.")  
6️⃣ 출력은 JSON 배열 형식으로 paragraph 필드만 포함.  

📦 출력형식:
[
  {{"paragraph":"첫 장면"}},
  {{"paragraph":"둘째 장면"}},
  {{"paragraph":"마지막 장면"}}
]
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"너는 감정적으로 따뜻하고 아이 눈높이에 맞는 동화를 쓰는 전문가야."},
                {"role":"user","content":prompt.strip()}
            ],
            temperature=0.85,
            max_tokens=1600,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"```json|```","",content).strip()
        story_data = json.loads(content)
        if isinstance(story_data,dict):
            story_data=[story_data]

        story=[]
        for item in story_data:
            paragraph=item.get("paragraph","").strip()
            img_prompt=build_image_prompt(paragraph,name,age,gender)
            story.append({"paragraph":paragraph,"image_prompt":img_prompt})

        return Response(json.dumps({"story":story},ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("❌ Error generating story:\n%s",traceback.format_exc())
        return jsonify({"error":str(e)}),500

# ────────────────────────────────────────────────
# 5️⃣ /generate-image : DALL·E 3 삽화 생성
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data=request.get_json(force=True)
        prompt=data.get("prompt","").strip()
        if not prompt:
            return jsonify({"error":"prompt is required"}),400

        result=client.images.generate(
            model="dall-e-3",
            prompt=f"{prompt}",
            size="1024x1024",
            quality="standard"
        )
        url=result.data[0].url if result.data else None
        if not url:
            return jsonify({"error":"No image returned"}),500
        return jsonify({"image_url":url}),200
    except Exception as e:
        log.error("❌ Error generating image:\n%s",traceback.format_exc())
        return jsonify({"error":str(e)}),500

# ────────────────────────────────────────────────
# 6️⃣ 앱 실행
# ────────────────────────────────────────────────
if __name__=="__main__":
    port=int(os.getenv("PORT",10000))
    app.run(host="0.0.0.0",port=port)
