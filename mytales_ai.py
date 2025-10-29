# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import os, json, logging, time, re, uuid, random

# ── init/env ─────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

TEXT_MODEL   = os.getenv("TEXT_MODEL",   "gpt-4o-mini")   # gpt-4o | gpt-4o-mini
TEXT_T       = float(os.getenv("TEXT_T", "0.8"))
TEXT_TOP_P   = float(os.getenv("TEXT_TOP_P", "0.9"))
TEXT_PP      = float(os.getenv("TEXT_PP", "0.5"))

IMAGE_MODEL  = os.getenv("IMAGE_MODEL",  "gpt-image-1")
IMAGE_SIZE   = os.getenv("IMAGE_SIZE",   "1024x1024")     # 1024x1024|1024x1536|1536x1024|auto

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
log = logging.getLogger("mytales")

# ── 다양성 장치 ──────────────────────────────────────────────────────
PALETTES = [
  "soft pastel spring", "warm sunset pastel", "cool morning pastel",
  "mint-lilac cream", "peach-ivory sky"
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

# ── 프롬프트: 상상 인과 시스템 ──────────────────────────────────────
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
3) 상상 결과는 은유적·신비한·미묘한 변화여야 한다.
   예)
   - 짜증 → 짜증 요정이 나타나 물건이 삐뚤어진다.
   - 편식 → 안 먹은 음식 속 ‘잠든 친구들’이 꿈속에서 신호를 보낸다.
   - 싸움 → 싸움귀신이 따라와 다시 싸움을 건다.
   - 거짓말 → ‘거짓말 그림자’가 커져 말을 삼킨다.
   - 정리정돈 → 물건들이 밤마다 자기 집을 찾게 해달라 속삭인다.
4) 결말은 작은 깨달음·미세한 감정 변화·다음 회차 예고로 끝난다.
   예) “그날 밤, {name}은 꿈속에서 조용히 결심했어요.”

[문체]
- 5~9세 수준, 쉬운 단어.
- 감정은 행동·상황으로 표현.
- 따뜻하지만 약간 신비로운 분위기.
- 한 문장 12~15자, 한 문단 3~4문장.

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
   {{"text": "현실 감정 — 불편함·짜증·싫음 등 현실적 시작"}},
   {{"text": "이상한 징후 — 작은 소리·그림자·속삭임 등장"}},
   {{"text": "상상 세계 진입 — 조력자/상징 존재와 만남"}},
   {{"text": "상상의 사건 — 이상한 규칙, 은유적 체험"}},
   {{"text": "현실 복귀 — 여운, 몸·마음의 미묘한 변화"}},
   {{"text": "여운 — 직접 해결 금지, 다음 회차 암시"}}
 ],
 "ending": "직접 교훈 없이, 꿈·감각·상징으로 마무리"
}}
"""

def build_prompt(name, age, gender, goal):
    outfit, room, palette = choose_combo(gender)
    seed = story_seed()
    return IMAGINATIVE_PROMPT_TEMPLATE.format(
        name=name, age=age, gender=gender, goal=goal,
        outfit=outfit, room=room, palette=palette, seed=seed
    )

# ── 직접 인과 결말 차단(주제 불문) ─────────────────────────────────
DIRECT_RESOLUTION_PATTERNS = [
  r"(했더니|하니|해서)\s*(기뻤|좋았|괜찮았|행복했|편해졌|모두\s*웃었|문제.*해결|화해했|다시는\s*안)"
]

def has_direct_resolution(paragraphs):
    text = "\n".join(paragraphs or [])
    return any(re.search(p, text) for p in DIRECT_RESOLUTION_PATTERNS)

REWRITE_PROGRESS_PROMPT = """
다음 동화 문단에서 '직접 인과 결말(예: ~했더니 좋았어요/해결됐어요/화해했어요/참았어요)'을 제거하고
'상상 인과 시스템'에 맞춘 '진행-중 결말'로 고쳐라.
규칙:
- 해결 선언 금지, 평가 언어 금지.
- 결말은 꿈·상징·감각·다음 회차 암시로 끝낸다.
- 5~9세 수준, 한 문장 12~15자, 한 문단 3~4문장.
JSON만 반환:
{"paragraphs": ["...", "...", "..."]}

원문:
{original}
"""

def rewrite_progress(paragraphs):
    original = "\n".join(paragraphs or [])
    rsp = client.chat.completions.create(
        model=TEXT_MODEL, temperature=0.4, max_tokens=700,
        messages=[{"role":"user","content":REWRITE_PROGRESS_PROMPT.format(original=original)}]
    )
    s = rsp.choices[0].message.content or ""
    s = re.sub(r"^```json|^```|```$", "", s, flags=re.MULTILINE).strip()
    try:
        return json.loads(s).get("paragraphs", paragraphs)
    except Exception:
        return paragraphs

# ── 헬퍼들 ──────────────────────────────────────────────────────────
def safe_json_parse(s: str):
    s = (s or "").strip()
    s = re.sub(r"^```json|^```|```$", "", s, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}\s*$", s, flags=re.DOTALL)
    if m: s = m.group(0)
    return json.loads(s)

def generate_plan(name, age, gender, goal):
    prompt = build_prompt(name, age, gender, goal)
    rsp = client.chat.completions.create(
        model=TEXT_MODEL,
        temperature=TEXT_T,
        top_p=TEXT_TOP_P,
        presence_penalty=TEXT_PP,
        max_tokens=1200,
        messages=[{"role":"user","content":prompt}]
    )
    txt = rsp.choices[0].message.content or "{}"
    plan = safe_json_parse(txt)
    scenes = plan.get("scenes", [])
    paragraphs = [ (s.get("text","") if isinstance(s, dict) else str(s)) for s in scenes ]

    # 직접 인과 결말 감지 → 재작성
    if has_direct_resolution(paragraphs):
        paragraphs = rewrite_progress(paragraphs)
    # 최후 안전망: 남아 있으면 중화
    if has_direct_resolution(paragraphs):
        fixed = []
        for p in paragraphs:
            s = re.sub(DIRECT_RESOLUTION_PATTERNS[0],
                       "오늘은 작은 떨림. 밤에 다시 속삭임이 올 거예요.", p)
            fixed.append(s)
        paragraphs = fixed

    return {
        "title": plan.get("title",""),
        "protagonist": plan.get("protagonist",""),
        "story_paragraphs": paragraphs[:6],
        "ending": plan.get("ending",""),
        "scenes": plan.get("scenes", []),
        "global_style": plan.get("global_style", {})
    }

def build_image_prompt(scene_text: str, gs: dict, ref=False):
    style    = gs.get("style","pastel watercolor storybook")
    outfit   = gs.get("outfit","")
    room     = gs.get("room","")
    lighting = gs.get("lighting","soft afternoon sunlight")
    tail = ("same character identity, same outfit, same room, same lighting. "
            "focus on symbolic imaginative causality cues. ")
    tail += "same seed as first image." if ref else "seed fixed."
    return (
      f"{style}. outfit:{outfit}. room:{room}. lighting:{lighting}. "
      f"Illustrate this scene faithfully: {scene_text}. {tail}"
    )

def generate_one_image(prompt: str, size=None):
    size = size or IMAGE_SIZE
    img = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=size)
    return {"b64": img.data[0].b64_json, "id": img.created}

# ── endpoints ────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "text_model": TEXT_MODEL,
        "image_model": IMAGE_MODEL,
        "image_size": IMAGE_SIZE,
        "t": TEXT_T, "top_p": TEXT_TOP_P, "presence_penalty": TEXT_PP
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
    return jsonify({
        "title": plan["title"],
        "protagonist": plan["protagonist"],
        "story_paragraphs": plan["story_paragraphs"],
        "ending": plan["ending"],
        "global_style": plan["global_style"],
        "scenes": plan["scenes"]
    })

@app.route("/generate-image", methods=["POST"])
def generate_image():
    d = request.get_json(force=True)
    scene = d.get("scene", {}) or {}
    gs = d.get("global_style", {}) or {}
    is_ref = bool(d.get("is_reference", False))
    scene_text = scene.get("text","") if isinstance(scene, dict) else str(scene)
    prompt = build_image_prompt(scene_text, gs, ref=is_ref)
    img = generate_one_image(prompt, IMAGE_SIZE)
    return jsonify({"b64": img["b64"]})

@app.route("/generate-full", methods=["POST"])
def generate_full_disabled():
    return jsonify({"error": "disabled. use /generate-story then /generate-image per scene."}), 410

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
