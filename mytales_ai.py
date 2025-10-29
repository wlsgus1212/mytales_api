# mytales_ai.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, time, re, uuid, random, hashlib, logging
from dotenv import load_dotenv
from openai import OpenAI

# ── env ─────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY       = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

TEXT_MODEL    = os.getenv("TEXT_MODEL", "gpt-4o-mini")   # gpt-4o | gpt-4o-mini
TEXT_T        = float(os.getenv("TEXT_T", "0.6"))
TEXT_TOP_P    = float(os.getenv("TEXT_TOP_P", "0.9"))
TEXT_PP       = float(os.getenv("TEXT_PP", "0.0"))
OPENAI_TIMEOUT= float(os.getenv("OPENAI_TIMEOUT", "25.0"))

IMAGE_MODEL   = os.getenv("IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE    = os.getenv("IMAGE_SIZE", "1024x1024")     # 1024x1024|1024x1536|1536x1024|auto
IMG_RETRIES   = int(os.getenv("IMG_RETRIES", "2"))
CACHE_TTL_S   = int(os.getenv("CACHE_TTL_S", "600"))

# ── app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# gzip(선택)
try:
    from flask_compress import Compress
    Compress(app)
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
log = logging.getLogger("mytales")

# OpenAI client with timeout
client = OpenAI(api_key=API_KEY, timeout=OPENAI_TIMEOUT)

# ── small caches (mem) ─────────────────────────────────────────────────
_STORY_CACHE = {}
_IMAGE_CACHE = {}

def _now(): return time.time()

def _cache_get(store, key):
    v = store.get(key)
    if not v: return None
    if v["exp"] < _now():
        try: del store[key]
        except: pass
        return None
    return v["val"]

def _cache_set(store, key, val, ttl=CACHE_TTL_S):
    store[key] = {"val": val, "exp": _now() + ttl}

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

# ── style presets ──────────────────────────────────────────────────────
PALETTES = [
  "soft pastel spring", "warm sunset pastel",
  "cool morning pastel", "mint-lilac cream", "peach-ivory sky"
]
ROOMS = ["따뜻한 햇살의 주방 식탁", "창가가 밝은 거실 테이블", "아늑한 식탁 옆 작은 창문"]
OUTFITS_F = [
  "하늘색 원피스+흰 양말+노란 슬리퍼",
  "복숭아 티셔츠+민트 스커트+흰 운동화",
  "연보라 원피스+아이보리 가디건+플랫슈즈",
]
OUTFITS_M = [
  "하늘색 티셔츠+네이비 반바지+운동화",
  "라임 티셔츠+베이지 팬츠+운동화",
  "민트 후드+회색 반바지+운동화",
]

def story_seed():
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(time.time_ns())).hex[:8]

def choose_combo(gender: str):
    outfit = random.choice(OUTFITS_F if str(gender).startswith("여") else OUTFITS_M)
    room = random.choice(ROOMS)
    palette = random.choice(PALETTES)
    return outfit, room, palette

# ── prompt (요청한 버전 그대로) ───────────────────────────────────────
IMAGINATIVE_PROMPT_TEMPLATE = """
너는 5~9세 어린이를 위한 ‘상상 인과형 감성 동화 작가’야.
아이의 실제 행동을 직접 교정하지 않고, 상상 속 결과로 표현해야 해.

[입력]
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {goal}

[핵심 원칙]
1) 직접 해결 금지: “짜증을 안 냈어요/화해했어요/편식이 사라졌어요/괜찮았어요” 금지.
2) 결과는 현실이 아닌 상상 세계에서만 드러난다.
3) 상상 결과는 은유적·신비한·미묘한 변화로 제시한다.
4) 결말은 **작은 감각·상징으로 열린 결말**로 끝낸다. 교훈 문장 금지.

[문체]
- 5~9세 수준, 쉬운 단어.
- 감정은 행동·상황으로 표현.
- 따뜻하지만 약간 신비로운 분위기.

[길이 규칙]
- 반드시 6개 장면을 모두 채워라.
- **각 장면 40~80자**로 제한(공백 포함). 문장 2~3문장 권장.
- 총 분량은 300~600자 사이.

[전역 스타일(일관성)]
- style: "pastel watercolor storybook, palette: {palette}, STYLE_TOKEN#{seed}"
- outfit: "{outfit}"
- room: "{room}"
- lighting: "soft afternoon sunlight"

[출력(JSON만)]
{{
 "title": "제목",
 "protagonist": "{name} ({age}살 {gender})",
 "global_style": {{
   "style": "pastel watercolor storybook, palette: {palette}, STYLE_TOKEN#{seed}",
   "outfit": "{outfit}",
   "room": "{room}",
   "lighting": "soft afternoon sunlight"
 }},
 "scenes": [
   {{"text": "장면1: 현실 감정 — 불편함·짜증·싫음 등 현실적 시작. 40~80자."}},
   {{"text": "장면2: 이상한 징후 — 작은 소리·그림자·속삭임 등장. 40~80자."}},
   {{"text": "장면3: 상상 세계 진입 — 조력자/상징 존재 만남. 40~80자."}},
   {{"text": "장면4: 상상의 사건 — 이상한 규칙·은유 체험. 40~80자."}},
   {{"text": "장면5: 현실 복귀 — 몸·마음의 미묘한 변화. 40~80자."}},
   {{"text": "장면6: 여운 — 직접 해결 금지, **열린 결말**. 40~80자."}}
 ],
 "ending": "직접 교훈 없이, 꿈·감각·상징으로 잔잔히 마무리"
}}
"""

def build_prompt(name, age, gender, goal):
    outfit, room, palette = choose_combo(gender)
    seed = story_seed()
    return IMAGINATIVE_PROMPT_TEMPLATE.format(
        name=name, age=age, gender=gender, goal=goal,
        outfit=outfit, room=room, palette=palette, seed=seed
    )

# ── anti direct-resolution(서버 안전망, 간결화) ───────────────────────
DIRECT_RESOLUTION_PATTERNS = [
  r"(했더니|하니|해서)\s*(기뻤|좋았|괜찮았|행복했|편해졌|모두\s*웃었|문제.*해결|화해했|다시는\s*안)"
]
def has_direct_resolution(paragraphs):
    text = "\n".join(paragraphs or [])
    return any(re.search(p, text) for p in DIRECT_RESOLUTION_PATTERNS)

def neutralize_direct_resolution(paragraphs):
    fixed = []
    for p in paragraphs:
        s = re.sub(DIRECT_RESOLUTION_PATTERNS[0],
                   "작은 숨이 고요해졌어요.", p)
        fixed.append(s)
    return fixed

# ── story generation ──────────────────────────────────────────────────
def safe_json_parse(s: str):
    s = (s or "").strip()
    s = re.sub(r"^```json|^```|```$", "", s, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}\s*$", s, flags=re.DOTALL)
    if m: s = m.group(0)
    return json.loads(s)

def generate_plan(name, age, gender, goal):
    cache_key = _hash(f"story:{name}|{age}|{gender}|{goal}")
    hit = _cache_get(_STORY_CACHE, cache_key)
    if hit: return hit

    prompt = build_prompt(name, age, gender, goal)
    rsp = client.chat.completions.create(
        model=TEXT_MODEL,
        temperature=TEXT_T,
        top_p=TEXT_TOP_P,
        presence_penalty=TEXT_PP,
        max_tokens=900,
        messages=[{"role":"user","content":prompt}]
    )
    plan = safe_json_parse(rsp.choices[0].message.content or "{}")
    scenes = plan.get("scenes", []) or []
    paragraphs = [(s.get("text","") if isinstance(s, dict) else str(s)) for s in scenes][:6]

    if has_direct_resolution(paragraphs):
        paragraphs = neutralize_direct_resolution(paragraphs)

    result = {
        "title": plan.get("title",""),
        "protagonist": plan.get("protagonist",""),
        "story_paragraphs": paragraphs,
        "ending": plan.get("ending",""),
        "scenes": scenes[:6],
        "global_style": plan.get("global_style", {})
    }
    _cache_set(_STORY_CACHE, cache_key, result)
    return result

# ── image generation ──────────────────────────────────────────────────
def build_image_prompt(scene_text: str, gs: dict, ref=False):
    style    = gs.get("style","pastel watercolor storybook")
    outfit   = gs.get("outfit","")
    room     = gs.get("room","")
    lighting = gs.get("lighting","soft afternoon sunlight")
    tail = "same character, same outfit, same room, same lighting. "
    tail += ("same seed as first image." if ref else "seed fixed.")
    # 간결 프롬프트
    return f"{style}. outfit:{outfit}. room:{room}. lighting:{lighting}. Illustrate: {scene_text}. {tail}"

def generate_one_image(prompt: str, size=None):
    size = size or IMAGE_SIZE
    last_err = None
    for _ in range(IMG_RETRIES + 1):
        try:
            img = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=size)
            return {"b64": img.data[0].b64_json, "id": img.created}
        except Exception as e:
            last_err = e
            time.sleep(0.6)
    raise last_err

# ── routes ────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "text_model": TEXT_MODEL,
        "image_model": IMAGE_MODEL,
        "image_size": IMAGE_SIZE,
        "timeout": OPENAI_TIMEOUT,
        "img_retries": IMG_RETRIES,
        "cache_ttl_s": CACHE_TTL_S
    })

@app.route("/generate-story", methods=["POST"])
def generate_story():
    d = request.get_json(force=True)
    name   = str(d.get("name","")).strip()
    age    = int(d.get("age", 6))
    gender = str(d.get("gender","여자")).strip()
    goal   = d.get("topic") or d.get("goal") or "기타"
    log.info(f"generate-story: {name}, {age}, {gender}, {goal}")
    plan = generate_plan(name, age, gender, goal)
    return jsonify(plan)

@app.route("/generate-image", methods=["POST"])
def generate_image():
    d = request.get_json(force=True)
    scene = d.get("scene", {}) or {}
    gs = d.get("global_style", {}) or {}
    is_ref = bool(d.get("is_reference", False))
    scene_text = (scene.get("text","") if isinstance(scene, dict) else str(scene)).strip()
    if not scene_text:
        return jsonify({"error":"empty scene"}), 400

    # 캐시 키: scene_text + style 일관성
    cache_key = _hash(f"img:{scene_text}|{json.dumps(gs, ensure_ascii=False, sort_keys=True)}|{is_ref}")
    hit = _cache_get(_IMAGE_CACHE, cache_key)
    if hit:
        return jsonify({"b64": hit})

    prompt = build_image_prompt(scene_text, gs, ref=is_ref)
    try:
        img = generate_one_image(prompt, IMAGE_SIZE)
    except Exception as e:
        return jsonify({"error": f"image_fail: {str(e)}"}), 504

    _cache_set(_IMAGE_CACHE, cache_key, img["b64"])
    return jsonify({"b64": img["b64"]})

@app.route("/generate-full", methods=["POST"])
def generate_full_disabled():
    return jsonify({"error": "disabled. use /generate-story then /generate-image per scene."}), 410

# ── run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Render Start Command 권장:
    # gunicorn -w 1 -k gevent -t 300 --worker-connections 50 mytales_ai:app
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
