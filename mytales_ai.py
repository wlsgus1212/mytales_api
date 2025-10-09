from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback

# ────────────────────────────────────────────────
# 1) 환경 설정
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
# 2) 조사 보정: 이름+이는/은/는
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
# 3) /generate-story : V19 통합 프롬프트로 동화+삽화설명 생성
# ────────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name   = data.get("name","").strip()
    age    = data.get("age","")
    gender = data.get("gender","").strip()
    goal   = data.get("education_goal","").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error":"모든 항목을 입력해주세요."}),400

    name_particle = with_particle(name)

    # ── V19 통합 프롬프트
    prompt = f"""
너는 5~8세 어린이를 위한 **훈육형 감성 동화 작가이자 일러스트 디렉터**야.

아래 정보를 바탕으로, 아이가 스스로 교훈을 깨닫는 따뜻한 동화와
각 장면에 맞는 삽화 설명을 함께 만들어줘.

─────────────────────────────
🧩 입력 정보
- 주인공 이름: {name} ({name_particle})
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: "{goal}"
─────────────────────────────

🎯 동화 작성 규칙
1️⃣ 전체를 6장면으로 구성해. 각 장면은 **2~4문장**으로 짧고 부드럽게 써.
2️⃣ 이야기 구조: **문제 → 시도 → 실패 → 깨달음 → 변화 → 교훈**
3️⃣ 교훈은 설명이 아니라 행동으로 보여줘. (“~해야 해요” 금지)
4️⃣ 주제는 아이의 감정 변화를 통해 해결되어야 해.
5️⃣ 리듬감 있는 문장 1회 이상 포함 (“톡톡, 마음이 두드렸어요.” / “후우, 바람이 속삭였어요.” 등).
6️⃣ 아이 시점으로 서술하고, 어려운 단어(혼란, 불안, 우울 등)는 절대 사용하지 마.
7️⃣ 현실적, 판타지, 마법, 동물 세계 등 어떤 배경이든 가능하지만, 따뜻하고 안전한 분위기를 유지해.
8️⃣ 마지막 장면은 아이가 스스로 깨달아 긍정적으로 변하는 결말로 끝내.

🎨 삽화 설명 규칙
1️⃣ 각 장면마다 "illustration_caption"을 추가해. 문장은 한 줄(최대 30단어).
2️⃣ {age}세 {gender} {name}의 외형·표정·옷·헤어스타일은 모든 장면에서 **동일**해야 해.
3️⃣ 스타일: 밝고 부드러운 **수채화 / 파스텔톤 / 어린이 그림책풍**
4️⃣ 사실적·공포·폭력·슬픔 중심 묘사 금지. 안전하고 따뜻한 톤 유지.
5️⃣ 한 문장에 다음 요소를 포함: 나이·성별·이름 / 행동 / 배경 / 감정 / 조명 / 스타일 / 일관성 표기

예시:
"8세 여자아이 수정이, 숲속에서 반짝이는 나비를 바라보는 장면, 부드러운 햇살, 수채화 그림책 스타일, same character and same world"

📦 출력 형식(JSON 배열만)
[
  {{"paragraph": "첫 번째 장면의 동화 내용", "illustration_caption": "첫 번째 장면의 삽화 설명"}},
  {{"paragraph": "두 번째 장면의 동화 내용", "illustration_caption": "두 번째 장면의 삽화 설명"}},
  {{"paragraph": "세 번째 장면의 동화 내용", "illustration_caption": "세 번째 장면의 삽화 설명"}},
  {{"paragraph": "네 번째 장면의 동화 내용", "illustration_caption": "네 번째 장면의 삽화 설명"}},
  {{"paragraph": "다섯 번째 장면의 동화 내용", "illustration_caption": "다섯 번째 장면의 삽화 설명"}},
  {{"paragraph": "여섯 번째 장면의 동화 내용(교훈적 결말)", "illustration_caption": "여섯 번째 장면의 삽화 설명"}}
]

출력은 반드시 위 JSON만 포함하고, 그 외의 텍스트나 코드블록은 금지.
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"너는 어린이를 위한 교훈 중심 동화를 쓰는 전문가이자 그림책 일러스트 디렉터다."},
                {"role":"user","content":prompt.strip()}
            ],
            temperature=0.8,
            max_tokens=2200,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"```json|```","",content).strip()

        story_data = json.loads(content)
        if isinstance(story_data, dict):
            story_data = [story_data]

        # 필드 보정
        story=[]
        for i, item in enumerate(story_data):
            paragraph = (item.get("paragraph","") if isinstance(item,dict) else str(item)).strip()
            caption   = (item.get("illustration_caption","") if isinstance(item,dict) else "").strip()

            if not paragraph:
                paragraph = f"{i+1}번째 장면: 내용 누락"
            if not caption:
                # 최소 안전 캡션 보정
                caption = f"{age}세 {gender} 아이 {name}가 따뜻한 분위기에서 행동하는 장면, 수채화 그림책 스타일, same character and same world"

            story.append({"paragraph":paragraph, "illustration_caption":caption})

        return Response(json.dumps({"story":story}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("❌ Error generating story:\n%s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ────────────────────────────────────────────────
# 4) /generate-image : illustration_caption 기반 생성
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        caption = data.get("prompt","").strip()
        if not caption:
            return jsonify({"error":"prompt is required"}),400

        result = client.images.generate(
            model="dall-e-3",
            prompt=f"{caption}, soft watercolor storybook style, warm pastel tones, same character and same world",
            size="1024x1024",
            quality="standard"
        )
        url = result.data[0].url if result.data else None
        if not url:
            return jsonify({"error":"No image returned"}),500

        return jsonify({"image_url": url}), 200

    except Exception as e:
        log.error("❌ Error generating image:\n%s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ────────────────────────────────────────────────
# 5) 앱 실행
# ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
