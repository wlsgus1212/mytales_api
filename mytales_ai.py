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
RECENT_SET = []  # 최근 10개 조합 회피

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
    combo = (outfit, room, palette)
    tries = 0
    while combo in RECENT_SET and tries < 5:
        outfit = random.choice(OUTFITS_F if str(gender).startswith("여") else OUTFITS_M)
        room = random.choice(ROOMS); palette = random.choice(PALETTES)
        combo = (outfit, room, palette); tries += 1
    RECENT_SET.append(combo)
    if len(RECENT_SET) > 10: RECENT_SET.pop(0)
    return outfit, room, palette

# ── 규칙 블록(동적 생성) ────────────────────────────────────────────
RULE_BLOCK_PROMPT = """
너는 5~9세 아동 훈육 설계자다.
아래 훈육 주제에 맞는 '장면 설계 규칙 블록'을 JSON으로 만들어라.

주제: "{goal}"

요구 스키마(JSON만 출력):
{
 "goal_tags": ["감정조절","사회갈등","정직","습관","안전","자립","정리정돈","나눔","수면","분리불안","두려움","디지털","기타"],
 "do": [
   "장면에서 반드시 구현할 핵심 행동 지침 3~6개(쉬운 말)"
 ],
 "dont": [
   "피해야 할 표현/전개 3~6개(예: 설교 금지, 공포 묘사 금지 등)"
 ],
 "self_efficacy_endings": [
   "맛 평가/외부 칭찬 없이 마무리 예시 3개"
 ],
 "scene_must_include": [
   "시각 프롬프트에 넣을 필수 소품/인물/행동 5~8개"
 ],
 "helper_suggestions_female": ["요정","작은 동물","별 친구","꽃 정령","인형"],
 "helper_suggestions_male": ["로봇","공룡","번개 요정","하늘 새","작은 자동차"],
 "micro_skills": [
   "주제 해결용 미시 기술(호흡 10초, I-메시지, 한입 규칙, 차례 정하기 등) 3~6개"
 ]
}
제약:
- '맛있다/괜찮다' 같은 맛평가 결말은 넣지 말 것.
- 설교/체벌/공포 유도 금지.
- 쉬운 단어만.
"""

def derive_rule_block(goal: str, gender: str):
    try:
        rsp = client.chat.completions.create(
            model=TEXT_MODEL, temperature=0.6, max_tokens=700,
            messages=[{"role":"user","content":RULE_BLOCK_PROMPT.format(goal=goal)}],
        )
        jb = rsp.choices[0].message.content or "{}"
        jb = re.sub(r"^```json|^```|```$", "", jb, flags=re.MULTILINE).strip()
        rule = json.loads(jb)
    except Exception:
        rule = {
          "goal_tags": ["기타"],
          "do": ["공감 먼저 말하기","아이 스스로 선택 넣기","시도는 작게","몸으로 느끼는 변화 묘사"],
          "dont": ["설교 금지","위협 금지","맛 평가로 끝내기 금지","부모 칭찬만으로 마무리 금지"],
          "self_efficacy_endings": ["오늘 한 가지 해냈다. 내일은 한 걸음 더.","내 마음을 내가 잠깐 멈출 수 있었어.","작은 약속 카드 한 장을 얻었다."],
          "scene_must_include": ["주인공","조력자","상황 소품","손 동작","표정 클로즈업","작은 보상/기록물"],
          "helper_suggestions_female": ["요정","작은 동물","별 친구","꽃 정령","인형"],
          "helper_suggestions_male": ["로봇","공룡","번개 요정","하늘 새","작은 자동차"],
          "micro_skills": ["10초 숨 쉬기","손가락 카운트","I-메시지","차례 정하기","한입 규칙"]
        }
    helpers = rule.get("helper_suggestions_female" if str(gender).startswith("여") else "helper_suggestions_male", [])
    rule["_helper_hint"] = ", ".join(helpers[:3]) if helpers else ""
    return rule

# ── 베이스 프롬프트(직접 해결 금지 포함) ───────────────────────────
PROMPT_TEMPLATE_BASE = """
너는 5~9세 어린이를 위한 **훈육 중심 감성 동화 작가**다.
입력 정보를 바탕으로, 아이가 공감하며 스스로 배우는 짧고 따뜻한 이야기를 만든다.

[입력]
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {goal}

[공통 목적]
- 꾸짖음 대신 공감·이해.
- 재미·상상으로 행동 변화의 씨앗 만들기.
- 쉬운 단어, 문장 12~15자, 문단 3~4문장.
- 감정은 몸짓·상황으로 표현. 무섭거나 강압적 표현 금지.

[직접 해결 금지]
- “문제가 해결됐다/안 한다/다시는/완전히 고쳤다/이제 안 해요” 같은 **직설 해결 서술 금지**.
- “좋은/착한/올바른” 등 평가 언어 금지.
- **맛 평가 금지**(맛있다/괜찮다 등).
- 해결은 **간접 효과**로 표현:
  · 능력·게이지·뱃지·카드·도감 등 수집/기록 자산
  · **미세 목표** 한 걸음(“오늘 한입 → 내일 두입”, “열까지 숨 쉬기”)
  · **신체감각 변화**(“숨이 편해졌어요”, “어깨가 가벼웠어요”)
  · **관계 신호**(“다음에 같이 해보자고 약속했어요”)
- 문제 행동은 **완전 소거 금지**. 다음에도 연습할 여지 남김.

[주제별 규칙 요약]
{rule_block}

[전역 스타일(일관성)]
- style: "pastel watercolor storybook, palette: {palette}, STYLE_TOKEN#{seed}"
- outfit: "{outfit}"
- room: "{room}"
- lighting: "soft afternoon sunlight"
- 이미지는 동일 캐릭터/의상/공간/조명. 1번 장면 seed 고정, 이후 장면은 첫 seed 재사용.

[출력(JSON만)]
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
   {{"text":"장면1(공감)",        "action":"...", "must_include":[], "emotion":"...", "framing":"..."}},
   {{"text":"장면2(갈등/고립)",    "action":"...", "must_include":[], "emotion":"...", "framing":"..."}},
   {{"text":"장면3(조력자 등장)",  "action":"...", "must_include":[], "emotion":"...", "framing":"..."}},
   {{"text":"장면4(제안/연습)",    "action":"...", "must_include":[], "emotion":"...", "framing":"..."}},
   {{"text":"장면5(자기 행동)",    "action":"...", "must_include":[], "emotion":"...", "framing":"..."}},
   {{"text":"장면6(여운/다음 한 걸음 — 직접 해결 금지)",
     "action":"...", "must_include":[], "emotion":"뿌듯함", "framing":"작은 보상/기록 강조"}}
 ],
 "ending": "부모 칭찬·문제완해 서술 없이, 수집/미세 목표/신체감각/약속 중 하나로 마무리"
}}
"""

def build_prompt(name, age, gender, goal):
    outfit, room, palette = choose_combo(gender)
    seed = story_seed()
    rule = derive_rule_block(goal, gender)

    rb = []
    rb.append(f"- 태그: {', '.join(rule.get('goal_tags', []))}")
    rb += [f"- 해야 할 것: {x}" for x in rule.get("do", [])]
    rb += [f"- 금지: {x}" for x in rule.get("dont", [])]
    rb.append(f"- 마무리 예시: {', '.join(rule.get('self_efficacy_endings', [])[:3])}")
    rb.append(f"- 장면 필수요소 힌트: {', '.join(rule.get('scene_must_include', [])[:6])}")
    rb.append(f"- 미시 기술: {', '.join(rule.get('micro_skills', [])[:4])}")
    rule_block = "\n".join(rb)

    return PROMPT_TEMPLATE_BASE.format(
        name=name, age=age, gender=gender, goal=goal,
        palette=palette, seed=seed, outfit=outfit, room=room,
        rule_block=rule_block
    )

# ── 직접 해결/맛평가 감지·수정 ─────────────────────────────────────
VIOLATION_PATTERNS = [
    r"(안\s*냈[어요]|안\s*하[겠였]어요|다시는|완전히\s*고쳤|이제\s*안\s*해요)",
    r"(좋은\s*아이|착한\s*아이|바른\s*아이|올바른\s*행동)",
    r"(맛있었|맛있다|괜찮았[어요]?)"
]

def violates_nonliteral(paragraphs):
    text = "\n".join(paragraphs)
    return any(re.search(p, text) for p in VIOLATION_PATTERNS)

REPAIR_PROMPT = """
다음 동화 문단에서 '직접 해결'·'맛 평가'·'평가 언어'를 제거하고
간접 효과(수집/미세 목표/신체감각/약속)로 마무리되게 고쳐라.
문장 길이와 난이도는 5~9세 수준을 유지하라. JSON만 반환:
{"paragraphs": ["...", "...", "..."]}

원문:
{original}
"""

def repair_story(paragraphs):
    original = "\n".join(paragraphs)
    rsp = client.chat.completions.create(
        model=TEXT_MODEL, temperature=0.4, max_tokens=600,
        messages=[{"role":"user","content":REPAIR_PROMPT.format(original=original)}]
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
    paragraphs = [s.get("text","") for s in scenes]
    if violates_nonliteral(paragraphs):
        paragraphs = repair_story(paragraphs)
    return {
        "title": plan.get("title",""),
        "protagonist": plan.get("protagonist",""),
        "story_paragraphs": paragraphs,
        "ending": plan.get("ending",""),
        "scenes": scenes,
        "global_style": plan.get("global_style", {})
    }

def build_image_prompt_from_scene(scene: dict, gs: dict, ref=False):
    style    = gs.get("style","pastel watercolor storybook")
    outfit   = gs.get("outfit","")
    room     = gs.get("room","")
    lighting = gs.get("lighting","soft afternoon sunlight")

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
    prompt = build_image_prompt_from_scene(scene, gs, ref=is_ref)
    img = generate_one_image(prompt, IMAGE_SIZE)
    return jsonify({"b64": img["b64"]})

@app.route("/generate-full", methods=["POST"])
def generate_full_disabled():
    return jsonify({"error": "disabled. use /generate-story then /generate-image per scene."}), 410

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
