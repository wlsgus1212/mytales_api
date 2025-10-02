from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")
client = OpenAI(api_key=API_KEY)

IMAGES_ENABLED = os.getenv("IMAGES_ENABLED", "true").lower() in ("1","true","yes")
DEBUG_RETURN_IMAGE_ERRORS = os.getenv("DEBUG_RETURN_IMAGE_ERRORS", "false").lower() in ("1","true","yes")

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

def _extract_json_block(s: str) -> str:
    if not isinstance(s, str): raise ValueError("model content is not string")
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", s, re.I)
    if m: return m.group(1)
    starts = [(i, c) for i,c in enumerate(s) if c in "[{"]
    ends = [(i, c) for i,c in enumerate(s) if c in "]}"]
    if starts and ends and starts[0][0] < ends[-1][0]:
        return s[starts[0][0]:ends[-1][0]+1]
    return s

def loads_json_array_only(s: str):
    try:
        v = json.loads(s)
        if isinstance(v, list): return v
    except Exception:
        pass
    v2 = json.loads(_extract_json_block(s))
    if isinstance(v2, list): return v2
    if isinstance(v2, dict) and "story_paragraphs" in v2 and isinstance(v2["story_paragraphs"], list):
        return v2["story_paragraphs"]
    raise ValueError("model did not return JSON array")

@app.get("/")
def root():
    return "MyTales Flask API is running."

@app.get("/healthz")
def healthz():
    return {"ok": True}, 200

@app.post("/generate-story")
def generate_story():
    # query로 이미지 on/off, 디버그 제어
    q_images = request.args.get("images")
    images_enabled = IMAGES_ENABLED if q_images is None else (q_images.lower() in ("1","true","yes"))
    debug = request.args.get("debug","0") in ("1","true","yes")

    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = str(data.get("name","")).strip()
    gender = str(data.get("gender","")).strip()
    goal = str(data.get("education_goal","")).strip()
    try:
        age = int(data.get("age",""))
    except Exception:
        return jsonify({"error":"age must be integer"}), 400

    if not all([name, age, gender, goal]):
        return jsonify({"error":"모든 항목을 입력해주세요."}), 400

    system = "You are a JSON generator. Output ONLY valid JSON with no extra text."
    user_prompt = (
        f"아동 이름={name}, 나이={age}, 성별={gender}. 훈육 주제=\"{goal}\".\n"
        "유치원생이 이해할 쉬운 어휘로 6개 문단 동화 생성.\n"
        "각 문단 3~4문장, 각 문단에 삽화용 장면 묘사 포함.\n"
        "항상 아동 이름을 본문에 등장시키고 일관되게 사용.\n"
        "반드시 다음 중 하나로만 출력:\n"
        "A) [\"문단1\", ... , \"문단6\"]\n"
        "B) {\"story_paragraphs\": [\"문단1\", ... , \"문단6\"]}\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role":"system","content":system},
                {"role":"user","content":user_prompt}
            ],
            temperature=0.7,
            timeout=60
        )
        content = resp.choices[0].message.content or ""
        log.info("OpenAI raw: %s", content[:500])

        try:
            paragraphs = loads_json_array_only(content)
        except Exception:
            obj = json.loads(content)
            paragraphs = obj.get("story_paragraphs", [])
            if not isinstance(paragraphs, list):
                raise ValueError("story_paragraphs missing or not a list")

        paragraphs = [str(p).strip() for p in paragraphs][:6]
        while len(paragraphs) < 6:
            paragraphs.append(f"{name}와 친구들이 서로 돕고 배려하며 문제를 해결하는 간단한 장면이다.")
    except Exception as e:
        log.error("Text generation failed: %s", traceback.format_exc())
        return jsonify({"error":"gpt_text_generation_failed","message":str(e)}), 500

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

    result = {"texts": paragraphs, "images": image_urls}
    if debug or DEBUG_RETURN_IMAGE_ERRORS:
        result["image_errors"] = image_errors
        result["images_enabled"] = images_enabled
    return jsonify(result), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
