# mytales_api.py
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, json, re, time, logging, random
from dotenv import load_dotenv
from openai import OpenAI, __version__ as openai_version

# ───────── 환경 ─────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in .env")
client = OpenAI(api_key=API_KEY)

# SDK 최소 버전 확인
def _ver_tuple(v):
    try:
        return tuple(map(int, v.split(".")[:2]))
    except:
        return (0, 0)
if _ver_tuple(openai_version) < (1, 52):
    raise RuntimeError(f"openai SDK too old: {openai_version}. Upgrade to >=1.52.0")

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mytales")

# ───────── 전역 옵션 ─────────
USE_CHEAPER_MODEL = False        # 품질 우선
SKIP_IMAGES_BY_DEFAULT = False
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1")

# 지원 해상도 고정
SUPPORTED_IMG_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1536x1024")  # 가로형 기본
def _valid_image_size(s: str) -> str:
    if s in SUPPORTED_IMG_SIZES:
        return s
    logging.warning(f"[image] invalid size '{s}', fallback to 1536x1024")
    return "1536x1024"

def pick_model():
    return "gpt-4o-mini" if USE_CHEAPER_MODEL else "gpt-4o"

# ───────── 유틸 ─────────
def clean_json_blocks(s: str) -> str:
    s = re.sub(r"```(?:json)?", "", s).strip()
    return s.strip("` \n\t")

def try_json_load(s: str):
    try:
        return json.loads(s)
    except:
        m = re.search(r"\{.*\}\s*$", s, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise

def clamp_age(age):
    try:
        n = int(age)
        return max(3, min(10, n))
    except:
        return 6

# ───────── 캐릭터 ─────────
def generate_character_profile(name, age, gender):
    age = clamp_age(age)
    hair_styles = [
        "짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리",
        "짧은 금발 머리", "포니테일 머리", "보브 컷"
    ]
    outfits = [
        "노란 셔츠와 파란 멜빵", "분홍 스웨터와 청바지", "하늘색 원피스",
        "빨간 후드와 검은 바지", "초록 체크 셔츠와 카키 바지", "보라색 원피스"
    ]
    hair = random.choice(hair_styles)
    outfit = random.choice(outfits)
    anchor = f"<<{name}-{age}-{gender}>>"

    canonical_ko = f"{hair}, {outfit} 착용. 둥근 얼굴과 부드러운 볼, 따뜻한 갈색 아몬드형 눈. 아이 체형. 모든 장면에서 동일한 외형 유지."
    canonical_en = (
        f"{anchor} is a {age}-year-old {gender} child. {hair}. Wearing {outfit}. "
        "Round face with soft cheeks, warm brown almond eyes, childlike proportions. "
        "The exact same character must appear consistently in every scene with identical appearance."
    )

    profile = {
        "name": name,
        "age": age,
        "gender": gender,
        "anchor": anchor,
        "visual_description": canonical_ko,
        "canonical": canonical_en
    }
    logger.info(f"✅ 캐릭터 프로필: {profile}")
    return profile

# ───────── 스토리 ─────────
def story_prompt(name, age, gender, topic, anchor):
    return f"""
당신은 5~9세 아동용 감성 그림책 작가 겸 편집자다.
목표: 아이가 스스로 깨닫는 교훈을 체화하게 만든다. 설교 금지. 경험으로 보여주기.

출력언어: 한국어.
정보: 이름={name}, 나이={age}, 성별={gender}, 훈육주제='{topic}', 캐릭터앵커='{anchor}'.

작성 규칙:
- 총 5개 챕터. 각 챕터 paragraphs 2~4문장. 짧고 리듬감 있게.
- 구조: 도입→갈등→깨달음→변화→희망.
- 내면은 행동·대사·상황으로 보여주기. 설명형 교훈 금지.
- 각 챕터에 illustration 필수: 구도(카메라), 배경, 조명, 소품, 색, 상징, 감정, '{anchor}' 동일 외형 지시 포함.

반드시 아래 JSON만 반환:
{{
  "title": "짧고 상징적인 제목",
  "character": "주인공 {name}의 한 줄 소개",
  "chapters": [
    {{
      "title": "챕터 제목",
      "paragraphs": ["문장1", "문장2"],
      "illustration": "구체적 장면/구도/빛/색/상징/감정/환경. '{anchor}' 동일 외형 지시 포함"
    }}
  ],
  "ending": "따뜻한 마무리 한 단락"
}}
""".strip()

def generate_story_text(name, age, gender, topic):
    logger.info(f"📝 스토리 생성: {name}/{age}/{gender}/{topic}")
    age = clamp_age(age)
    profile = generate_character_profile(name, age, gender)
    prompt = story_prompt(name, age, gender, topic, profile["anchor"])
    sys = (
        "You are a senior children's picture-book writer. "
        "Return ONLY strict JSON that exactly matches the schema. "
        "No extra text. Korean output."
    )
    model = pick_model()

    for attempt in range(2):
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": prompt}
            ],
            temperature=0.35,
            max_tokens=1600,
            response_format={"type": "json_object"}
        )
        raw = clean_json_blocks(resp.choices[0].message.content)
        try:
            data = try_json_load(raw)
            assert "title" in data
            assert "chapters" in data and len(data["chapters"]) == 5
            for ch in data["chapters"]:
                assert "title" in ch
                assert "paragraphs" in ch and 2 <= len(ch["paragraphs"]) <= 4
                assert "illustration" in ch and len(ch["illustration"]) >= 40
            return data, profile
        except Exception as e:
            logger.warning(f"JSON 검증 실패 재시도 {attempt+1}: {e}")
            prompt += "\n\n주의: 정확히 5개 챕터, 각 2~4문장, illustration 상세."

    raise RuntimeError("스토리 JSON 생성 실패")

# ───────── 이미지 ─────────
def build_image_prompt(chapter_content, character_profile, chapter_index):
    title = chapter_content.get("title", f"챕터 {chapter_index+1}")
    illu  = chapter_content.get("illustration", "")
    anchor = character_profile["anchor"]
    canonical = character_profile["canonical"]

    return f"""
Children's picture-book illustration, chapter {chapter_index+1}: "{title}"

Scene:
{illu}

Main character sheet (must match 1:1 in every scene):
{canonical}
Hidden identity anchor: {anchor}

Composition checklist:
- Single wide shot showing environment (no collage, no split panels)
- Character medium size, clean silhouette, readable facial expression
- Camera: eye-level, 35mm lens equivalent, gentle perspective
- Lighting: soft key light with warm bounce, natural falloff
- Palette: warm pastels with subtle complementary accents
- Background: simplified props only; avoid clutter
- Symbolic elements that reflect the moral of this chapter

Strict negatives:
- No text, captions, watermarks
- No deformed anatomy, extra fingers/limbs
- No harsh outlines, posterization, melted shapes
- No phototype, UI mockups
""".strip()

def generate_image(chapter_content, character_profile, chapter_index):
    try:
        size = _valid_image_size(IMAGE_SIZE)
        prompt = build_image_prompt(chapter_content, character_profile, chapter_index)
        logger.info(f"🖼️ 이미지 생성: 챕터 {chapter_index+1} | model={IMAGE_MODEL} size={size}")
        img = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size=size,
            n=1
        )
        return img.data[0].url
    except Exception as e:
        logger.error(f"이미지 생성 실패 #{chapter_index+1}: {e}")
        return None

# ───────── 파이프라인 ─────────
def generate_story_with_images(name, age, gender, topic, generate_images=True):
    story, profile = generate_story_text(name, age, gender, topic)
    if generate_images and not SKIP_IMAGES_BY_DEFAULT:
        for i, ch in enumerate(story.get("chapters", [])):
            url = generate_image(ch, profile, i)
            if url:
                ch["image_url"] = url
    return {
        "title": story.get("title"),
        "character_profile": profile,
        "chapters": story.get("chapters", []),
        "ending": story.get("ending", "")
    }

# ───────── 템플릿 라우트 ─────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/free-input")
def free_input():
    return render_template("free_input.html")

@app.route("/free-preview")
def free_preview():
    return render_template("free_preview.html")

@app.route("/free-full")
def free_full():
    return render_template("free_full.html")

@app.route("/paid-test")
def paid_test():
    return render_template("paid_test.html")

@app.route("/paid-preview")
def paid_preview():
    return render_template("paid_preview.html")

@app.route("/paid-full")
def paid_full():
    return render_template("paid_full.html")

@app.route("/payment")
def payment():
    return render_template("payment.html")

@app.route("/mypage")
def mypage():
    return render_template("mypage.html")

@app.route("/faq")
def faq():
    return render_template("faq.html")

@app.route("/thank-you")
def thank_you():
    return render_template("thank_you.html")

@app.route("/admin")
def admin():
    return render_template("admin.html")

# ───────── API ─────────
@app.route("/generate-full", methods=["POST", "OPTIONS"])
def generate_full():
    if request.method == "OPTIONS":
        r = jsonify({"status": "ok"})
        r.headers.add("Access-Control-Allow-Origin", "*")
        r.headers.add("Access-Control-Allow-Headers", "Content-Type")
        r.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return r
    try:
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        age = (data.get("age") or "").strip()
        gender = (data.get("gender") or "").strip()
        topic = (data.get("topic") or data.get("education_goal") or "").strip()
        generate_images = bool(data.get("generate_images", True))
        use_fast_mode = bool(data.get("fast_mode", False))

        if not all([name, age, gender, topic]):
            return jsonify({"error": "입력 누락"}), 400

        global USE_CHEAPER_MODEL
        USE_CHEAPER_MODEL = use_fast_mode

        if generate_images:
            result = generate_story_with_images(name, age, gender, topic, True)
        else:
            story, profile = generate_story_text(name, age, gender, topic)
            result = {
                "title": story.get("title"),
                "character_profile": profile,
                "chapters": story.get("chapters", []),
                "ending": story.get("ending", "")
            }

        r = jsonify(result)
        r.headers.add("Access-Control-Allow-Origin", "*")
        r.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        r.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        r.headers.add("Access-Control-Allow-Credentials", "true")
        return r
    except Exception as e:
        logger.error(f"/generate-full 오류: {e}")
        er = jsonify({"error": f"서버 오류: {str(e)}"})
        er.headers.add("Access-Control-Allow-Origin", "*")
        er.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        er.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        er.headers.add("Access-Control-Allow-Credentials", "true")
        return er, 500

@app.route("/health", methods=["GET", "OPTIONS"])
def health_check():
    if request.method == "OPTIONS":
        r = jsonify({"status": "ok"})
        r.headers.add("Access-Control-Allow-Origin", "*")
        r.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        r.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return r
    r = jsonify({"status": "healthy", "timestamp": time.time()})
    r.headers.add("Access-Control-Allow-Origin", "*")
    r.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
    r.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return r

@app.route("/simple-test", methods=["GET", "POST", "OPTIONS"])
def simple_test():
    if request.method == "OPTIONS":
        r = jsonify({"status": "ok"})
        r.headers.add("Access-Control-Allow-Origin", "*")
        r.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        r.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return r
    r = jsonify({"message": "서버 정상", "timestamp": time.time(), "status": "success"})
    r.headers.add("Access-Control-Allow-Origin", "*")
    r.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
    r.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return r

# 진단용
@app.route("/diag", methods=["GET"])
def diag():
    return jsonify({
        "openai_version": openai_version,
        "image_model": IMAGE_MODEL,
        "image_size": IMAGE_SIZE,
        "valid_size_used": _valid_image_size(IMAGE_SIZE),
        "supported_sizes": sorted(list(SUPPORTED_IMG_SIZES)),
        "cheap_mode": USE_CHEAPER_MODEL
    })

if __name__ == "__main__":
    logger.info("🚀 MyTales AI 서버 시작")
    logger.info(f"💰 저렴한 모델 사용: {USE_CHEAPER_MODEL}")
    logger.info(f"🖼️ 이미지 모델: {IMAGE_MODEL}, 크기: {IMAGE_SIZE}")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
