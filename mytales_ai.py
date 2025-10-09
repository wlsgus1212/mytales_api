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
# 2) 자연스러운 조사 보정: 진현→진현이는
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
# 3) /generate-story : 동화+삽화설명 통합 생성(V20 규칙 강화)
# ────────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name   = data.get("name","").strip()
    age    = str(data.get("age","")).strip()
    gender = data.get("gender","").strip()
    goal   = data.get("education_goal","").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error":"모든 항목을 입력해주세요."}),400

    name_particle = with_particle(name)

    # ── V20 통합 프롬프트 (동화+삽화설명 동시에 생성, 캡션 누락 불가)
    prompt = f"""
너는 5~8세 어린이를 위한 **훈육형 감성 동화 작가이자 일러스트 디렉터**다.

아래 정보를 바탕으로, 아이가 스스로 교훈을 깨닫는 따뜻한 동화와
각 장면에 맞는 삽화 설명(illustration_caption)을 **반드시** 함께 만들어라.

[입력 정보]
- 주인공 이름: {name} ({name_particle})
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: "{goal}"

[동화 규칙]
1) 전체 6장면. 각 장면 2~4문장. 아이 시점, 짧고 부드러운 문장.
2) 구조: 문제 → 시도 → 실패 → 깨달음 → 변화 → 교훈(행동으로 표현, 설교 금지).
3) 어려운 단어(혼란, 불안, 우울 등) 금지. 안전하고 따뜻한 분위기 유지.
4) 세계관은 자유(현실/마법/동물/공주 등)이나 톤은 항상 밝고 온화.
5) 리듬 문장 1회 이상 포함(예: “후우, 바람이 속삭였어요.” / “톡톡, 마음이 두드렸어요.”).

[삽화설명 규칙(V20)]
- 너는 **어린이 동화 삽화 아티스트**다.
- 각 장면에 대해 "illustration_caption"을 **반드시** 1문장(≤30단어)으로 생성한다.
- paragraph의 행동·감정·배경을 시각적으로 정확히 반영해야 한다.
- 캐릭터 일관성: {age}세 {gender} {name}의 외형/옷/머리/표정 톤은 모든 장면에서 동일.
- 스타일: 밝고 순한 파스텔 + 부드러운 수채화 + 어린이 그림책풍.
- 금지: realistic photo, dark tones, horror, sadness, violence, blood, complex crowd, brands, religious icons.
- 문장 구성요소(모두 포함): [나이·성별·이름 + 행동 + 배경 + 감정 + 조명 + 스타일 + 일관성표현]
- 시리즈 일관성 문구를 문장 끝에 포함: "same character and same world, consistent palette and tone".

[출력 형식(이 형식만 출력, 다른 텍스트/코드블록 금지)]
[
  {{"paragraph":"첫 장면 내용","illustration_caption":"첫 장면 삽화 설명"}},
  {{"paragraph":"두 번째 장면 내용","illustration_caption":"두 번째 장면 삽화 설명"}},
  {{"paragraph":"세 번째 장면 내용","illustration_caption":"세 번째 장면 삽화 설명"}},
  {{"paragraph":"네 번째 장면 내용","illustration_caption":"네 번째 장면 삽화 설명"}},
  {{"paragraph":"다섯 번째 장면 내용","illustration_caption":"다섯 번째 장면 삽화 설명"}},
  {{"paragraph":"여섯 번째 장면 내용(교훈적 결말)","illustration_caption":"여섯 번째 장면 삽화 설명"}}
]
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",  # JSON 준수 강화
            messages=[
                {"role":"system","content":"너는 어린이를 위한 교훈 중심 동화를 쓰는 전문가이자 그림책 일러스트 디렉터다."},
                {"role":"user","content":prompt.strip()}
            ],
            temperature=0.8,
            max_tokens=2200,
        )

        content = resp.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()

        # 1차 파싱
        try:
            story_data = json.loads(content)
        except json.JSONDecodeError:
            # 2차 보정: paragraph/caption 쌍만 추출
            pairs = re.findall(
                r'"paragraph"\s*:\s*"([^"]+)"\s*,\s*"illustration_caption"\s*:\s*"([^"]+)"', content
            )
            story_data = [{"paragraph": p, "illustration_caption": c} for p, c in pairs]

        if isinstance(story_data, dict):
            story_data = [story_data]

        # 필드 보정 및 누락 방지
        story=[]
        fallback_caption = f'{age}세 {gender} {name}가 따뜻한 분위기에서 행동하는 장면, soft watercolor storybook style, pastel colors, warm gentle light, same character and same world, consistent palette and tone'
        for i, item in enumerate(story_data):
            paragraph = (item.get("paragraph","") if isinstance(item,dict) else str(item)).strip()
            caption   = (item.get("illustration_caption","") if isinstance(item,dict) else "").strip()
            if not paragraph:
                paragraph = f"{i+1}번째 장면: 내용 누락"
            if not caption:
                caption = fallback_caption
            # 30단어 초과 방지(너무 길면 축약)
            if len(caption.split()) > 30:
                caption = " ".join(caption.split()[:30])
            story.append({"paragraph": paragraph, "illustration_caption": caption})

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
            prompt=f"{caption}",
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
