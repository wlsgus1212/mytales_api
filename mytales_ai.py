# mytales_ai.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging

# ── 환경 설정 ─────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

client = OpenAI(api_key=API_KEY)

# 이미지 생성 기본 on/off 및 디버그 노출 플래그(환경변수로 제어)
IMAGES_ENABLED = os.getenv("IMAGES_ENABLED", "true").lower() in ("1", "true", "yes")
DEBUG_RETURN_IMAGE_ERRORS = os.getenv("DEBUG_RETURN_IMAGE_ERRORS", "false").lower() in ("1", "true", "yes")

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ── 유틸 ──────────────────────────────────────────────────────────────────────
def _extract_json_block(s: str) -> str:
    """모델이 코드펜스/잡텍스트를 섞어 보낼 때 JSON 블록만 추출."""
    if not isinstance(s, str):
        raise ValueError("model content is not string")
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", s, re.I)
    if m:
        return m.group(1)
    starts = [(i, c) for i, c in enumerate(s) if c in "[{"]
    ends = [(i, c) for i, c in enumerate(s) if c in "]}"]
    if starts and ends and starts[0][0] < ends[-1][0]:
        return s[starts[0][0]:ends[-1][0] + 1]
    return s

def loads_json_array_only(s: str):
    """배열 또는 {"story_paragraphs":[...]} 형태만 허용해 리스트로 반환."""
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    v2 = json.loads(_extract_json_block(s))
    if isinstance(v2, list):
        return v2
    if isinstance(v2, dict) and "story_paragraphs" in v2 and isinstance(v2["story_paragraphs"], list):
        return v2["story_paragraphs"]
    raise ValueError("model did not return JSON array")

def _fix_name_placeholders(text: str, name: str) -> str:
    """모델이 남기는 플레이스홀더 치환."""
    return (text
            .replace("아동 이름", name)
            .replace("아이 이름", name)
            .replace("아동의 이름", name)
            .replace("{이름}", name)
            .replace("{{이름}}", name))

def _normalize_to_six_paragraphs(paragraphs, name: str, age: int) -> list:
    """단일 문자열 또는 6개 미만 리스트를 6문단으로 보정."""
    if isinstance(paragraphs, str):
        parts = [p.strip() for p in re.split(r"[\.!?]\s+", paragraphs) if p.strip()]
        if not parts:
            parts = [paragraphs.strip()]
        chunk = max(1, len(parts) // 6)
        grouped, i = [], 0
        for _ in range(6):
            grp = ". ".join(parts[i:i + chunk]).strip()
            i += chunk
            grouped.append(grp if grp.endswith((".", "!", "?")) else (grp + "."))
        paragraphs = grouped

    paragraphs = [str(p).strip() for p in paragraphs]
    paragraphs = paragraphs[:6]
    while len(paragraphs) < 6:
        paragraphs.append(f"{name}와 친구들이 서로 돕고 배려하며 문제를 해결하는 장면이다.")

    # 이름 치환 및 최소 1회 등장 보장
    paragraphs = [_fix_name_placeholders(p, name) for p in paragraphs]
    if not any(name in p for p in paragraphs):
        paragraphs[0] = f"{name}는 {age}살로, 친구들과 어울리길 좋아해요. " + paragraphs[0]
    return paragraphs

# ── 라우트 ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return "MyTales Flask API is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

@app.post("/generate-story")
def generate_story():
    # 쿼리 토글
    q_images = request.args.get("images")
    images_enabled = IMAGES_ENABLED if q_images is None else (q_images.lower() in ("1", "true", "yes"))
    debug = request.args.get("debug", "0") in ("1", "true", "yes")
    mock = request.args.get("mock", "0") in ("1", "true", "yes")

    # 입력 파싱
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = str(data.get("name", "")).strip()
    gender = str(data.get("gender", "")).strip()
    goal = str(data.get("education_goal", "")).strip()
    try:
        age = int(data.get("age", ""))
    except Exception:
        return jsonify({"error": "age must be integer"}), 400

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    # MOCK 모드: OpenAI 우회해 서버/네트워크 문제 분리
    if mock:
        paragraphs = [
            f"{name}는 놀이터에서 친구들과 모래성을 시작했어요. 모두가 각자 할 일을 정했죠.",
            f"{name}는 성문을 맡고, 친구들은 탑과 해자를 만들며 서로 아이디어를 나눴어요.",
            "바람이 불어 성이 무너졌지만, 아이들은 웃으며 다시 시도하기로 했어요.",
            "이번엔 역할을 바꾸어 더 단단한 기초부터 쌓기 시작했어요.",
            "서로 도와주며 작은 문제를 금방 해결했고 성은 점점 멋져졌어요.",
            f"끝내 모두가 자랑스러워했고 {name}는 '같이하니 더 잘돼!'라고 말했어요."
        ]
        return jsonify({"texts": paragraphs, "images": ["", "", "", "", "", ""]}), 200

    # OpenAI 텍스트 생성
    system = "You are a JSON generator. Output ONLY valid JSON with no extra text."
    user_prompt = (
        f"아동 이름={name}, 나이={age}, 성별={gender}. 훈육 주제=\"{goal}\".\n"
        "유치원생이 이해할 쉬운 어휘로 6개 문단 동화를 생성하라.\n"
        "각 문단은 3~4문장. 각 문단에 삽화용 장면 묘사를 포함한다.\n"
        "본문에는 아동의 이름을 일관되게 사용한다.\n"
        "다음 중 하나의 형식만 출력:\n"
        "A) [\"문단1\", ... , \"문단6\"]\n"
        "B) {\"story_paragraphs\": [\"문단1\", ... , \"문단6\"]}\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},  # JSON 강제
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            timeout=45
        )
        content = resp.choices[0].message.content or ""
        log.info("OpenAI raw: %s", content[:500])

        try:
            paragraphs = loads_json_array_only(content)
        except Exception:
            obj = json.loads(_extract_json_block(content))
            paragraphs = obj.get("story_paragraphs", [])
            if not isinstance(paragraphs, list):
                raise ValueError("story_paragraphs missing or not a list")

        paragraphs = _normalize_to_six_paragraphs(paragraphs, name, age)

    except Exception as e:
        log.error("Text generation failed: %s", traceback.format_exc())
        return jsonify({"error": "gpt_text_generation_failed", "message": str(e)}), 500

    # 이미지 생성(옵션)
    image_urls, image_errors = [], []
    if images_enabled:
        for i, para in enumerate(paragraphs, 1):
            try:
                img = client.images.generate(
                    model="gpt-image-1",
                    prompt=(
                        f"{para}\n\n"
                        f"Main character: {name}, {age} years old, {gender} child.\n"
                        "Style: watercolor, children's picture book, soft lighting, consistent character across all 6 images."
                    ),
                    size="1024x1024"
                )
                image_urls.append(img.data[0].url)
                image_errors.append("")
            except Exception as e:
                msg = str(e)
                log.warning("image gen failed on slide %d: %s", i, msg)
                image_urls.append("")
                image_errors.append(msg)
    else:
        image_urls = [""] * 6
        image_errors = ["disabled"] * 6

    result = {"texts": paragraphs, "images": image_urls}
    if debug or DEBUG_RETURN_IMAGE_ERRORS:
        result["image_errors"] = image_errors
        result["images_enabled"] = images_enabled
    return jsonify(result), 200

# ── 엔트리포인트 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Render는 동적 $PORT 사용
    app.run(host="0.0.0.0", port=port)
