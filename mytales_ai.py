from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging

# ── 기본 설정 ─────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ── 유틸: JSON 안전 파싱 ───────────────────────────────────────────────────────
def _extract_json_block(s: str) -> str:
    if not isinstance(s, str):
        raise ValueError("model content is not string")
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", s, re.I)
    if m:
        return m.group(1)
    # 가장 바깥 대괄호/중괄호 추출 시도
    starts = [(i, "[") for i, c in enumerate(s) if c == "["] + [(i, "{") for i, c in enumerate(s) if c == "{"]
    ends   = [(i, "]") for i, c in enumerate(s) if c == "]"] + [(i, "}") for i, c in enumerate(s) if c == "}"]
    if starts and ends:
        L = min(starts)[0]
        R = max(ends)[0]
        if L < R:
            return s[L:R+1]
    return s

def loads_json_array_only(s: str):
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    s2 = _extract_json_block(s)
    v2 = json.loads(s2)
    if isinstance(v2, list):
        return v2
    # { "story_paragraphs": [...] } 형태 지원
    if isinstance(v2, dict) and "story_paragraphs" in v2 and isinstance(v2["story_paragraphs"], list):
        return v2["story_paragraphs"]
    raise ValueError("model did not return JSON array")

# ── 라우트 ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return "MyTales Flask API is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = str(data.get("name", "")).strip()
    age = data.get("age", "")
    gender = str(data.get("gender", "")).strip()
    education_goal = str(data.get("education_goal", "")).strip()

    try:
        age = int(age)
    except Exception:
        return jsonify({"error": "age must be integer"}), 400

    if not all([name, age, gender, education_goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    # 프롬프트와 JSON 강제
    system = "You are a JSON generator. Output ONLY valid JSON with no extra text."
    user_prompt = (
        f"아이 이름={name}, 나이={age}, 성별={gender}. 훈육 주제=\"{education_goal}\".\n"
        "유치원생이 이해할 쉬운 어휘로 6개 문단 동화 생성.\n"
        "각 문단은 3~4문장. 각 문단엔 삽화 생성용 장면 묘사를 포함.\n"
        "반드시 아래 중 하나의 형식만 출력:\n"
        "A) 순수 JSON 배열: [\"문단1\", ... , \"문단6\"]\n"
        "B) JSON 객체: {\"story_paragraphs\": [\"문단1\", ... , \"문단6\"]}\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},  # 객체 강제. 배열만 나올 수 없을 때 대비.
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            timeout=60
        )
        content = resp.choices[0].message.content or ""
        log.info("OpenAI raw: %s", content[:500])

        # 객체 강제 때문에 보통 {"story_paragraphs":[...]}로 옴. 파서가 배열/객체 모두 허용.
        try:
            paragraphs = loads_json_array_only(content)
        except Exception:
            # 객체 강제 케이스 직접 파싱
            obj = json.loads(content)
            paragraphs = obj.get("story_paragraphs", [])
            if not isinstance(paragraphs, list):
                raise ValueError("story_paragraphs missing or not a list")

        paragraphs = [str(p).strip() for p in paragraphs][:6]
        if len(paragraphs) < 6:
            # 부족하면 컷 대신 남은 문단을 간단 문장으로 채움
            while len(paragraphs) < 6:
                paragraphs.append("이 장면은 아이와 친구들이 협력하며 문제를 해결하는 모습을 간단히 보여준다.")

    except Exception as e:
        log.error("Text generation failed: %s", traceback.format_exc())
        return jsonify({"error": "gpt_text_generation_failed", "message": str(e)}), 500

    # 이미지 생성은 실패해도 텍스트는 반환
    image_urls = []
    for i, para in enumerate(paragraphs, 1):
        try:
            img = client.images.generate(
                model="gpt-image-1",
                prompt=f"{para}\n\nStyle: watercolor, children's picture book, soft lighting, consistent characters.",
                size="1024x1024"
            )
            image_urls.append(img.data[0].url)
        except Exception as e:
            log.warning("image gen failed on slide %d: %s", i, e)
            image_urls.append("")

    return jsonify({"texts": paragraphs, "images": image_urls}), 200

# ── 엔트리 포인트 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Render는 동적으로 부여한 $PORT 사용. 10000 하드코딩 금지.
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
