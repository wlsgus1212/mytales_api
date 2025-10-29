# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import os, json, logging, time, concurrent.futures, re, uuid, random

# ─────────────────────────────────
# init & env
# ─────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

# Text / Image model & knobs
TEXT_MODEL   = os.getenv("TEXT_MODEL",   "gpt-4o-mini")  # gpt-4o | gpt-4o-mini
TEXT_T       = float(os.getenv("TEXT_T", "0.8"))
TEXT_TOP_P   = float(os.getenv("TEXT_TOP_P", "0.9"))
TEXT_PP      = float(os.getenv("TEXT_PP", "0.5"))

IMAGE_MODEL  = os.getenv("IMAGE_MODEL",  "gpt-image-1")
IMAGE_SIZE   = os.getenv("IMAGE_SIZE",   "1024x1024")    # 1024x1024|1024x1536|1536x1024|auto
IMG_WORKERS  = int(os.getenv("IMG_WORKERS", "1"))        # 한 장씩 호출 권장이므로 1

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
log = logging.getLogger("mytales")

# ─────────────────────────────────
# 다양성 장치: 팔레트·의상·공간·헬퍼 로테이션 + 시드
# ─────────────────────────────────
RECENT_SET = []  # 최근 10개 조합 캐시

PALETTES = [
  "soft pastel spring", "warm sunset pastel", "cool morning pastel",
  "mint-lilac cream", "peach-ivory sky"
]
ROOMS = ["따뜻한 햇살의 주방 식탁", "창가가 밝은 거실 테이블", "아늑한 식탁 옆 작은 창문"]
OUTFITS_F = [
  "하늘색 원피스+흰 양말+노란 슬리퍼",
  "복숭아색 티셔츠+민트 스커트+흰 운동화",
  "연보라 원피스+아이보리 가디건+플랫슈즈",
]
OUTFITS_M = [
  "하늘색 티셔츠+네이비 반바지+운동화",
  "라임 티셔츠+베이지 팬츠+운동화",
  "민트 후드+회색 반바지+운동화",
]
HELPERS_F = ["작은 요정", "토끼", "고양이", "새", "별 친구", "꽃 정령"]
HELPERS_M = ["작은 로봇", "공룡", "번개 요정", "하늘 새", "작은 자동차 친구"]

def story_seed():
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(time.time_ns())).hex[:8]

def choose_combo(gender: str):
    outfit = random.choice(OUTFITS_F if str(gender).startswith("여") else OUTFITS_M)
    room = random.choice(ROOMS)
    palette = random.choice(PALETTES)
    helper_pool = HELPERS_F if str(gender).startswith("여") else HELPERS_M
    helper_hint = ", ".join(random.sample(helper_pool, k=3))
    combo = (outfit, room, palette, helper_hint)
    tries = 0
    while combo in RECENT_SET and tries < 5:
        outfit = random.choice(OUTFITS_F if str(gender).startswith("여") else OUTFITS_M)
        room = random.choice(ROOMS); palette = random.choice(PALETTES)
        helper_hint = ", ".join(random.sample(helper_pool, k=3))
        combo = (outfit, room, palette, helper_hint); tries += 1
    RECENT_SET.append(combo)
    if len(RECENT_SET) > 10: RECENT_SET.pop(0)
    return outfit, room, palette, helper_hint

# ─────────────────────────────────
# 프롬프트 (장면 스펙 구조화 + 맛평가 금지 결말)
# ─────────────────────────────────
STORY_AND_SCENES_PROMPT = """
너는 5~9세 어린이를 위한 **훈육 중심 감성 동화 작가**다.
입력 정보를 바탕으로, 아이가 공감하며 스스로 배우는 짧고 따뜻한 이야기를 만든다.
동화는 6개 장면으로 나누며, 각 장면에 시각화를 위한 스펙을 함께 제공한다.

📥 입력
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {goal}

🎯 목적
- 꾸짖음 대신 공감·이해 중심.
- 감정 변화 + 상상/재미로 자연스러운 행동 변화.
- 쉬운 단어, 한 문장 12~15자, 문단 3~4문장.

🥦 편식 주제 규칙
- 비현실적 이유 금지. 감각 기반 표현 사용(쓴맛/냄새/식감/낯섦).
- 어른은 강요 금지. 감정 인정.

✨ 설득형(상상 보상형)
- 보상은 “맛”이 아니라 **이야기 자산**:
  - 능력 게이지(+1), 컬렉션(뱃지/도감), 관계(조력자 약속), 신체감각(“배가 편안했어요”)
- 즉시 보상은 작게, 누적 보상은 크게. 다음 회차 동기 남김.

🏁 결말(맛 평가 금지)
- “맛있다/괜찮다”로 끝내지 말고,
  능력/탐험/관계/신체감각/수집 중 하나로 마무리.
  (예: “한입 해냈다. 내일은 두입.”, “용기 카드 1장 획득”)

🎨 전역 스타일 (작품 내 일관성)
- style: "pastel watercolor storybook, palette: {palette}, STYLE_TOKEN#{seed}"
- outfit: "{outfit}" (모든 장면 동일)
- room: "{room}"  (가능하면 동일 공간)
- lighting: "soft afternoon sunlight"
- 이미지 생성 시 동일 캐릭터/의상/공간/조명 유지, 첫 장면 seed 고정, 이후 장면은 첫 seed 재사용.

📤 출력(JSON만, 추가 설명 금지)
{{
 "title": "...",
 "protagonist": "{name} ({age}살 {gender})",
 "global_style": {{
   "style": "pastel watercolor storybook, palette: {palette}, STYLE_TOKEN#{seed}",
   "outfit": "{outfit}",
   "room": "{room}",
   "lighting": "soft afternoon sunlight"
 }},
 "scenes": [
   {{
     "text": "장면1(공감) 텍스트",
     "action": "화면에 보여줄 핵심 동작 1문장",
     "must_include": ["{name}", "식탁", "접시(채소)"],
     "emotion": "망설임",
     "framing": "중간샷, 아이 좌측, 접시 중앙"
   }},
   {{
     "text": "장면2(고립) 텍스트",
     "action": "…",
     "must_include": ["{name}", "엄마", "식탁"],
     "emotion": "안심",
     "framing": "투샷, 같은 방, 아이 우측"
   }},
   {{
     "text": "장면3(조력자) 텍스트",
     "action": "…",
     "must_include": ["{name}", "조력자"],
     "emotion": "호기심",
     "framing": "중간샷, 조력자 등장 강조"
   }},
   {{
     "text": "장면4(제안/대화) 텍스트",
     "action": "…",
     "must_include": ["{name}", "조력자"],
     "emotion": "용기",
     "framing": "클로즈업, 표정 강조"
   }},
   {{
     "text": "장면5(자기 행동) 텍스트",
     "action": "…",
     "must_include": ["{name}", "채소 한입"],
     "emotion": "집중",
     "framing": "핸드 샷+얼굴, 행동 포커스"
   }},
   {{
     "text": "장면6(성장/여운) 텍스트 — 맛 평가 금지, 능력/탐험/관계/신체감각/수집 중 하나로",
     "action": "…",
     "must_include": ["{name}", "작은 보상(카드/뱃지/게이지 등)"],
     "emotion": "뿌듯함",
     "framing": "부드러운 미소, 작은 보상 강조"
   }}
 ],
 "ending": "짧은 마무리(맛 평가 금지, 다음 회차 동기)"
}}
"""

def build_prompt(name, age, gender, goal):
    outfit, room, palette, helper_hint = choose_combo(gender)
    seed = story_seed()  # 작품 고유 시드
    prompt = STORY_AND_SCENES_PROMPT.format(
        name=name, age=age, gender=gender, goal=goal,
        outfit=outfit, room=room, palette=palette, seed=seed
    )
    return prompt

# ─────────────────────────────────
# helpers
# ─────────────────────────────────
def safe_json_parse(s: str):
    s = s.strip()
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
    txt = rsp.choices[0].message.content
    plan = safe_json_parse(txt)
    scenes = plan.get("scenes", [])
    return {
        "title": plan.get("title",""),
        "protagonist": plan.get("protagonist",""),
        "story_paragraphs": [s.get("text","") for s in scenes],
        "ending": plan.get("ending",""),
        "scenes": scenes,
        "global_style": plan.get("global_style", {})
    }

def build_image_prompt_from_scene(scene: dict, gs: dict, ref=False):
    style   = gs.get("style","pastel watercolor storybook")
    outfit  = gs.get("outfit","")
    room    = gs.get("room","")
    lighting= gs.get("lighting","soft afternoon sunlight")

    action   = scene.get("action","")
    mustlist = scene.get("must_include", []) or []
    must     = ", ".join(mustlist)
    framing  = scene.get("framing","")
    emotion  = scene.get("emotion","")

    tail = ("same character identity, same outfit, same room, same lighting. "
            "focus on ability/progress or collection cue, not taste enjoyment. ")
    tail += "same seed as first image." if ref else "seed fixed."

    return (
      f"{style}. outfit:{outfit}. room:{room}. lighting:{lighting}. "
      f"Render EXACTLY this action: {action}. Must include (all visible): {must}. "
      f"Framing:{framing}. Emotion:{emotion}. {tail}"
    )

def generate_one_image(prompt: str, size=None):
    size = size or IMAGE_SIZE
    img = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=size)
    return {"b64": img.data[0].b64_json, "id": img.created}

# ─────────────────────────────────
# endpoints
# ─────────────────────────────────
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
    goal   = d.get("topic") or d.get("goal") or "편식"

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
    """
    body: {
      "scene": {...},              # /generate-story의 scenes[i] 객체 그대로
      "global_style": {...},
      "is_reference": false|true   # 첫 장면은 false, 이후 true
    }
    """
    d = request.get_json(force=True)
    scene = d.get("scene", {}) or {}
    gs = d.get("global_style", {}) or {}
    is_ref = bool(d.get("is_reference", False))

    prompt = build_image_prompt_from_scene(scene, gs, ref=is_ref)
    img = generate_one_image(prompt, IMAGE_SIZE)
    return jsonify({"b64": img["b64"]})

if __name__ == "__main__":
    # Render에서는 gunicorn 사용; 로컬 테스트용
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
