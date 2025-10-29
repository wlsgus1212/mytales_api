# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import os, json, logging, time, concurrent.futures, re

# ─────────────────────────────────
# init
# ─────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
log = logging.getLogger("mytales")

# ─────────────────────────────────
# prompt (text+images, JSON 출력 강제)
# ─────────────────────────────────
STORY_AND_IMAGES_PROMPT = """
너는 5~9세 어린이를 위한 **훈육 중심 감성 동화 작가**다.
입력 정보를 바탕으로, 아이가 공감하며 스스로 배우는 짧고 따뜻한 이야기를 만든다.
동화는 6개 장면으로 나누고, 각 장면마다 이미지 프롬프트를 함께 작성한다.

─────────────────────────────
📥 입력
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {goal}

─────────────────────────────
🎯 이야기 목적
- 꾸짖음이 아닌 공감·이해 중심.
- 아이가 스스로 이유를 이해하고 선택하도록 설계.
- 감정 변화 + 재미/상상으로 자연스러운 행동 변화 유도.

🧭 감정 흐름(5단계)
1) 공감(현실적 거부·불편: 맛/냄새/식감/귀찮음)
2) 고립(혼자 고민)
3) 조력자(아이 선호 존재: {helper_hint})
4) 자기 행동(스스로 시도)
5) 성장(다음에도 해보고 싶은 마음)

🧒 조력자 규칙
- 명령 금지. “같이 해보자” 태도.
- 아이 마음에서 비롯된 존재처럼 자연스럽게 등장.

📖 어휘·문체
- 쉬운 단어. 한 문장 12~15자. 문단 3~4문장.
- 추상·한자어 금지(‘성실/배려’ 등 대신 구체 행동·감정).
- 감정은 몸짓·상황으로 표현(예: “볼이 빨개졌어요.”).
- 부정적·무서운·강압 표현 금지.

🥦 편식 주제 주의
- 비현실적 이유 금지(“색이 무서워서” X).
- 감각 기반 표현 사용(“쓴맛일까 봐 싫어요”, “냄새가 이상해요”).
- 어른은 강요 금지. 감정 인정.
- 결말은 “맛있다” 대신 “생각보다 괜찮았어요/다음에 또 먹어볼까?”.

✨ 설득형(상상 보상형)
- 이해가 어려우면 상상 보상(마법/초능력)로 흥미 유도.
- 보상은 상징적·상상적 표현으로 마무리(기분·행동 변화로 연결).

🎨 전역 스타일(이미지 일관성)
- style: "pastel watercolor storybook"
- outfit: 성별에 맞는 한 벌 의상(모든 장면 동일)
- room: 한 공간(예: “따뜻한 햇살의 주방 식탁”)
- lighting: "soft afternoon sunlight"
- seed_hint: "use same seed across all images"
- 모든 장면은 same character identity, same outfit, same room, same lighting 유지.

─────────────────────────────
📤 출력(JSON만, 추가 설명 금지)
{{
 "title": "...",
 "protagonist": "{name} ({age}살 {gender})",
 "story_paragraphs": [
   "장면1 텍스트(공감)",
   "장면2 텍스트(고립)",
   "장면3 텍스트(조력자)",
   "장면4 텍스트(대화/제안)",
   "장면5 텍스트(자기 행동)",
   "장면6 텍스트(성장·여운)"
 ],
 "ending": "마무리 한두 문장",
 "global_style": {{
   "style": "pastel watercolor storybook",
   "outfit": "{outfit}",
   "room": "{room}",
   "lighting": "soft afternoon sunlight",
   "seed_hint": "use same seed across all images"
 }},
 "image_prompts": [
   "기준 이미지(장면1): {name}, {age}, {gender}, outfit, room, lighting를 명시. 장면1 상황 정확 묘사. same character identity, same outfit, same room, same lighting. seed fixed.",
   "장면2: 장면2 상황. keep the same character, outfit, hairstyle, color palette, background, and lighting as the previous image. same seed as first image.",
   "장면3: 조력자 등장. 동일 환경. keep the same character, outfit, hairstyle, color palette, background, and lighting. same seed as first image.",
   "장면4: 대화/제안. 동일 환경. keep the same character... same seed as first image.",
   "장면5: 시도 장면. 동일 환경. keep the same character... same seed as first image.",
   "장면6: 성장·미소. 동일 환경. keep the same character... same seed as first image."
 ]
}}
"""

def build_prompt(name, age, gender, goal):
    outfit = "하늘색 원피스, 흰 양말, 노란 슬리퍼" if str(gender).startswith("여") else "하늘색 티셔츠, 반바지, 운동화"
    room = "따뜻한 햇살의 주방 식탁"
    helper_hint = "요정, 작은 동물(토끼·고양이·새), 인형, 별, 꽃" if str(gender).startswith("여") \
                  else "로봇, 공룡, 자동차, 번개 요정, 하늘 새"
    return STORY_AND_IMAGES_PROMPT.format(
        name=name, age=age, gender=gender, goal=goal,
        helper_hint=helper_hint, outfit=outfit, room=room
    )

# ─────────────────────────────────
# text plan
# ─────────────────────────────────
def safe_json_parse(s: str):
    # 코드펜스나 잡문 제거
    s = s.strip()
    s = re.sub(r"^```json|^```|```$", "", s, flags=re.MULTILINE).strip()
    # JSON 시작/끝 추정
    m = re.search(r"\{.*\}\s*$", s, flags=re.DOTALL)
    if m:
        s = m.group(0)
    return json.loads(s)

def generate_plan(name, age, gender, goal):
    prompt = build_prompt(name, age, gender, goal)
    rsp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.6,
        max_tokens=900,
        messages=[{"role":"user","content":prompt}]
    )
    txt = rsp.choices[0].message.content
    plan = safe_json_parse(txt)
    # 정규화
    return {
        "title": plan.get("title",""),
        "protagonist": plan.get("protagonist",""),
        "story_paragraphs": plan.get("story_paragraphs", []),
        "ending": plan.get("ending",""),
        "image_prompts": plan.get("image_prompts", []),
        "global_style": plan.get("global_style", {})
    }

# ─────────────────────────────────
# image gen
# ─────────────────────────────────
def build_image_prompt(base: str, gs: dict, ref=False):
    style = gs.get("style","pastel watercolor storybook")
    outfit = gs.get("outfit","")
    room = gs.get("room","")
    lighting = gs.get("lighting","soft afternoon sunlight")
    tail = "same character identity, same outfit, same room, same lighting."
    if ref:
        tail += " same seed as first image."
    else:
        tail += " seed fixed."
    return f"{base}\n{style}, outfit: {outfit}, room: {room}, lighting: {lighting}.\n{tail}"

def generate_one_image(prompt: str, size="768x768"):
    img = client.images.generate(model="gpt-image-1", prompt=prompt, size=size)
    return {"b64": img.data[0].b64_json, "id": img.created}

def generate_images(image_prompts, global_style):
    if not image_prompts:
        return []
    # 1장 기준
    p0 = build_image_prompt(image_prompts[0], global_style, ref=False)
    img0 = generate_one_image(p0)
    ref_id = img0["id"]  # 힌트용(동일 시드 개념)
    # 2~6 병렬
    def task(p):
        return generate_one_image(build_image_prompt(p, global_style, ref=True))
    imgs = [None]*len(image_prompts)
    imgs[0] = img0
    if len(image_prompts) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futs = {ex.submit(task, image_prompts[i]): i for i in range(1, len(image_prompts))}
            for f in concurrent.futures.as_completed(futs):
                i = futs[f]
                imgs[i] = f.result()
    return [im["b64"] for im in imgs]

# ─────────────────────────────────
# endpoints
# ─────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

@app.route("/generate-full", methods=["POST"])
def generate_full():
    t0 = time.time()
    d = request.get_json(force=True)
    name = str(d.get("name","")).strip()
    age = int(d.get("age", 6))
    gender = str(d.get("gender","여자")).strip()
    goal = d.get("topic") or d.get("goal") or "편식"
    want_images = bool(d.get("generate_images", True))

    plan = generate_plan(name, age, gender, goal)

    images_b64 = []
    if want_images:
        try:
            images_b64 = generate_images(plan["image_prompts"], plan["global_style"])
        except Exception as e:
            log.warning(f"image generation fail: {e}")

    resp = {
        "title": plan["title"],
        "protagonist": plan["protagonist"],
        "story_paragraphs": plan["story_paragraphs"],
        "ending": plan["ending"],
        "image_prompts": plan["image_prompts"],
        "images_base64": images_b64,
        "ms": int((time.time()-t0)*1000)
    }
    return jsonify(resp)

# 선택: 텍스트만 필요 시
@app.route("/generate-story", methods=["POST"])
def generate_story():
    d = request.get_json(force=True)
    name = str(d.get("name","")).strip()
    age = int(d.get("age", 6))
    gender = str(d.get("gender","여자")).strip()
    goal = d.get("topic") or d.get("goal") or "편식"
    plan = generate_plan(name, age, gender, goal)
    return jsonify({
        "title": plan["title"],
        "protagonist": plan["protagonist"],
        "story_paragraphs": plan["story_paragraphs"],
        "ending": plan["ending"],
        "image_prompts": plan["image_prompts"],
        "global_style": plan["global_style"]
    })

if __name__ == "__main__":
    # Render: gunicorn 사용 시 무시됨. 로컬 테스트용.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
