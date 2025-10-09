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
# 3️⃣ 일관형 이미지 프롬프트 생성
# ────────────────────────────────────────────────
def build_image_prompt_v2(paragraph, name, age, gender, base_appearance=None, base_background=None):
    """문단을 분석해 일관성 있는 삽화 프롬프트 생성"""
    if base_appearance is None:
        base_appearance = "soft brown hair, pastel clothes, kind expression"
    if base_background is None:
        base_background = "forest"

    # 배경 탐색
    if "바다" in paragraph: base_background = "beach"
    elif "성" in paragraph or "공주" in paragraph: base_background = "castle"
    elif "하늘" in paragraph or "별" in paragraph: base_background = "sky"
    elif "학교" in paragraph: base_background = "school"
    elif "숲" in paragraph: base_background = "forest"

    # 감정 추론
    if any(k in paragraph for k in ["웃","기뻐","밝","행복"]):
        emotion = "smiling warmly"
    elif any(k in paragraph for k in ["놀라","깜짝","호기심"]):
        emotion = "curious expression"
    elif any(k in paragraph for k in ["걱정","두려","무섭"]):
        emotion = "slightly worried face"
    elif any(k in paragraph for k in ["용기","도전","결심","해냈"]):
        emotion = "determined look"
    else:
        emotion = "gentle calm expression"

    # 행동 추론
    if "달렸" in paragraph: action = "running"
    elif "앉았" in paragraph: action = "sitting"
    elif "바라보" in paragraph: action = "looking at something"
    elif "안았" in paragraph: action = "hugging"
    else: action = "standing"

    # 장면 프롬프트 조합
    return (
        f"{age}-year-old {gender} child named {name}, same appearance as previous scene, "
        f"{base_appearance}, {action}, {emotion}, "
        f"in the same {base_background} environment, "
        f"soft watercolor storybook style, warm pastel tones, cinematic light"
    ), base_appearance, base_background

# ────────────────────────────────────────────────
# 4️⃣ /generate-story : 훈육형 동화 + 이미지 자동화
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

    # 🧠 훈육 중심 동화 프롬프트 (V15)
    prompt = f"""
너는 5~8세 어린이를 위한 **훈육형 감성 동화 작가**야.  
'{goal}'을 주제로, 아이가 스스로 깨닫는 교훈을 행동과 감정 변화로 보여줘.  
직접적인 설명이나 “~해야 해요” 같은 설교체는 쓰지 마.  
이야기는 현실, 판타지, 동물 세계, 공주 이야기 등 어떤 세계관에서도 시작 가능하다.  
하지만 끝에는 반드시 주제에 맞는 **교훈적 변화**가 있어야 한다.  

### 구성 규칙
1️⃣ 총 6장면. 각 장면은 2~4문장.
2️⃣ 문체는 짧고 부드러워야 하며, 어려운 단어나 ‘혼란’ 같은 어휘는 금지.
3️⃣ 주인공 {name}의 감정은 ‘문제 → 시도 → 실패 → 깨달음 → 변화’로 이어져야 한다.
4️⃣ 마지막 장면에서는 {goal}의 교훈이 행동으로 드러나야 한다.
5️⃣ 문장 중 하나는 리듬감 있는 반복 문장으로 만들어라.  
   예: “후우, 바람이 속삭였어요.”, “톡톡, 마음이 두드렸어요.”
6️⃣ 출력은 JSON 배열로 paragraph만 포함해라.

📦 출력 형식:
[
  {{"paragraph":"첫 장면"}},
  ...,
  {{"paragraph":"마지막 장면"}}
]
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"너는 어린이를 위한 교훈 중심 동화를 쓰는 전문가야."},
                {"role":"user","content":prompt.strip()}
            ],
            temperature=0.8,
            max_tokens=1600,
        )

        content = response.choices[0].message.content.strip()
        content = re.sub(r"```json|```","",content).strip()
        story_data = json.loads(content)
        if isinstance(story_data,dict):
            story_data=[story_data]

        story=[]
        base_appearance, base_background = None, None
        for item in story_data:
            paragraph=item.get("paragraph","").strip()
            img_prompt, base_appearance, base_background = build_image_prompt_v2(
                paragraph,name,age,gender,base_appearance,base_background
            )
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
            prompt=prompt,
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
