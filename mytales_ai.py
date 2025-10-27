# mytales_api.py
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, json, re, time, logging, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from dotenv import load_dotenv
from openai import OpenAI, __version__ as openai_version

# ───────── 환경 ─────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

# OpenAI 클라이언트(타임아웃/재시도)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "180"))      # 초
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))  # 비용 절감
client = OpenAI(api_key=API_KEY, timeout=OPENAI_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)

# SDK 최소 버전 확인
def _ver_tuple(v):
    try:
        return tuple(map(int, v.split(".")[:2]))
    except:
        return (0, 0)
if _ver_tuple(openai_version) < (1, 52):
    raise RuntimeError(f"openai SDK too old: {openai_version}. Upgrade to >=1.52.0")

# ───────── 앱/로그 ─────────
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mytales")

# ───────── 전역 옵션(비용 절약 기본) ─────────
USE_CHEAPER_MODEL = True                # fast_mode 강제 시 full도 mini 사용
SKIP_IMAGES_BY_DEFAULT = False

# 이미지 모델 및 사이즈
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1")
SUPPORTED_IMG_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
IMAGE_SIZE_PREVIEW = os.getenv("IMAGE_SIZE_PREVIEW", "1024x1024")
IMAGE_SIZE_FULL = os.getenv("IMAGE_SIZE_FULL", "1536x1024")

def _valid_image_size(s: str) -> str:
    if s in SUPPORTED_IMG_SIZES:
        return s
    logging.warning(f"[image] invalid size '{s}', fallback to 1024x1024")
    return "1024x1024"

# 동시성 및 장수 제한
IMAGE_LIMIT_DEFAULT = int(os.getenv("IMAGE_LIMIT_DEFAULT", "1"))  # 프리뷰 기본 1장
MAX_WORKERS = int(os.getenv("IMG_WORKERS", "2"))                  # 동시 생성 제한(과금/타임아웃 보호)

# ───────── 캐시(간단 인메모리) ─────────
_story_cache, _image_cache = {}, {}

def _key_story(name, age, gender, topic, cost_mode):
    return sha256(f"{name}|{age}|{gender}|{topic}|{cost_mode}".encode()).hexdigest()

def _key_image(chapter, profile, idx, size):
    sig = f"{profile['anchor']}|{idx}|{size}|{chapter.get('title','')}|{chapter.get('illustration','')}"
    return sha256(sig.encode()).hexdigest()

# ───────── 모델 선택 ─────────
def pick_model(cost_mode: str) -> str:
    # cost_mode: "preview" → mini, "full" → 4o (단, fast_mode/USE_CHEAPER_MODEL면 mini)
    if cost_mode == "full" and not USE_CHEAPER_MODEL:
        return "gpt-4o"
    return "gpt-4o-mini"

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

def generate_character_and_prompt(name, age, gender, topic):
    age = clamp_age(age)
    profile = generate_character_profile(name, age, gender)
    prompt = story_prompt(name, age, gender, topic, profile["anchor"])
    return profile, prompt

def generate_story_text(name, age, gender, topic, cost_mode="preview"):
    # 캐시
    cache_key = _key_story(name, age, gender, topic, cost_mode)
    if cache_key in _story_cache:
        return _story_cache[cache_key]

    logger.info(f"📝 스토리 생성: {name}/{age}/{gender}/{topic} | mode={cost_mode}")
    profile, prompt = generate_character_and_prompt(name, age, gender, topic)

    sys = ("You are a senior children's picture-book writer. "
           "Return ONLY strict JSON that exactly matches the schema. "
           "No extra text. Korean output.")

    model = pick_model(cost_mode)
    # 비용 최적화 파라미터
    temperature = 0.2 if cost_mode == "preview" else 0.35
    max_tokens = 900 if cost_mode == "preview" else 1400

    for attempt in range(2 if cost_mode == "full" else 1):  # preview는 재시도 0~1회
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
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
            _story_cache[cache_key] = (data, profile)
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

def _generate_single_image(ch, profile, idx, size):
    cache_key = _key_image(ch, profile, idx, size)
    if cache_key in _image_cache:
        return _image_cache[cache_key]
    prompt = build_image_prompt(ch, profile, idx)
    logger.info(f"🖼️ 이미지 생성: 챕터 {idx+1} | model={IMAGE_MODEL} size={size}")
    img = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=size, n=1)
    url = img.data[0].url
    _image_cache[cache_key] = url
    return url

def generate_images_batch(chapters, profile, limit, size):
    n = min(limit, len(chapters))
    urls = [None]*n
    if n == 0:
        return urls
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, n)) as ex:
        futs = {ex.submit(_generate_single_image, chapters[i], profile, i, size): i for i in range(n)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                urls[i] = fut.result()
            except Exception as e:
                logger.error(f"이미지 생성 실패 #{i+1}: {e}")
                urls[i] = None
    return urls

# ───────── 파이프라인 ─────────
def generate_story_with_images(name, age, gender, topic, image_limit, cost_mode="preview"):
    story, profile = generate_story_text(name, age, gender, topic, cost_mode=cost_mode)
    size = _valid_image_size(IMAGE_SIZE_PREVIEW if cost_mode == "preview" else IMAGE_SIZE_FULL)
    limit = 1 if cost_mode == "preview" else max(0, min(image_limit, 5))
    if not SKIP_IMAGES_BY_DEFAULT and limit > 0:
        urls = generate_images_batch(story["chapters"], profile, limit, size)
        for i, url in enumerate(urls):
            if url:
                story["chapters"][i]["image_url"] = url
    return {
        "title": story.get("title"),
        "character_profile": profile,
        "chapters": story.get("chapters", []),
        "ending": story.get("ending", "")
    }

# ───────── 템플릿 라우트 ─────────
@app.route("/")
def index(): return render_template("index.html")
@app.route("/free-input")
def free_input(): return render_template("free_input.html")
@app.route("/free-preview")
def free_preview(): return render_template("free_preview.html")
@app.route("/free-full")
def free_full(): return render_template("free_full.html")
@app.route("/paid-test")
def paid_test(): return render_template("paid_test.html")
@app.route("/paid-preview")
def paid_preview(): return render_template("paid_preview.html")
@app.route("/paid-full")
def paid_full(): return render_template("paid_full.html")
@app.route("/payment")
def payment(): return render_template("payment.html")
@app.route("/mypage")
def mypage(): return render_template("mypage.html")
@app.route("/faq")
def faq(): return render_template("faq.html")
@app.route("/thank-you")
def thank_you(): return render_template("thank_you.html")
@app.route("/admin")
def admin(): return render_template("admin.html")

# ───────── API(분리형 추천) ─────────
@app.route("/generate-story", methods=["POST"])
def api_generate_story():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    age = (data.get("age") or "").strip()
    gender = (data.get("gender") or "").strip()
    topic = (data.get("topic") or data.get("education_goal") or "").strip()
    cost_mode = (data.get("cost_mode") or "preview").lower()  # preview | full
    if not all([name, age, gender, topic]):
        return jsonify({"error": "입력 누락"}), 400
    story, profile = generate_story_text(name, age, gender, topic, cost_mode=cost_mode)
    return jsonify({
        "title": story["title"],
        "character_profile": profile,
        "chapters": story["chapters"],
        "ending": story["ending"],
        "cost_mode": cost_mode
    })

@app.route("/generate-image", methods=["POST"])
def api_generate_image():
    data = request.get_json(force=True)
    profile = data.get("character_profile")
    chapter = data.get("chapter")  # 단일 챕터 JSON
    idx = int(data.get("index", 0))
    cost_mode = (data.get("cost_mode") or "preview").lower()
    if not profile or not chapter:
        return jsonify({"error": "프로필/챕터 누락"}), 400
    try:
        size = _valid_image_size(IMAGE_SIZE_PREVIEW if cost_mode == "preview" else IMAGE_SIZE_FULL)
        url = _generate_single_image(chapter, profile, idx, size)
        return jsonify({"index": idx, "image_url": url, "cost_mode": cost_mode})
    except Exception as e:
        logger.error(f"/generate-image 오류: {e}")
        return jsonify({"error": str(e)}), 500

# ───────── 레거시 일괄 엔드포인트 ─────────
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
        use_fast_mode = bool(data.get("fast_mode", True))       # 비용 절약 기본값 True
        image_limit = int(data.get("image_limit", IMAGE_LIMIT_DEFAULT))
        cost_mode = (data.get("cost_mode") or "preview").lower()  # preview | full

        if not all([name, age, gender, topic]):
            return jsonify({"error": "입력 누락"}), 400

        global USE_CHEAPER_MODEL
        USE_CHEAPER_MODEL = use_fast_mode  # True면 full도 mini 사용

        if generate_images:
            result = generate_story_with_images(name, age, gender, topic, image_limit, cost_mode=cost_mode)
        else:
            story, profile = generate_story_text(name, age, gender, topic, cost_mode=cost_mode)
            result = {
                "title": story.get("title"),
                "character_profile": profile,
                "chapters": story.get("chapters", []),
                "ending": story.get("ending", ""),
                "cost_mode": cost_mode
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

# ───────── 헬스/진단 ─────────
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route("/simple-test", methods=["GET", "POST"])
def simple_test():
    return jsonify({"message": "서버 정상", "timestamp": time.time(), "status": "success"})

@app.route("/diag", methods=["GET"])
def diag():
    return jsonify({
        "openai_version": openai_version,
        "image_model": IMAGE_MODEL,
        "supported_sizes": sorted(list(SUPPORTED_IMG_SIZES)),
        "image_size_preview": IMAGE_SIZE_PREVIEW,
        "image_size_full": IMAGE_SIZE_FULL,
        "cheap_mode_forced": USE_CHEAPER_MODEL,
        "openai_timeout": OPENAI_TIMEOUT,
        "openai_max_retries": OPENAI_MAX_RETRIES,
        "image_limit_default": IMAGE_LIMIT_DEFAULT,
        "img_workers": MAX_WORKERS
    })

if __name__ == "__main__":
    logger.info("🚀 MyTales AI 서버 시작")
    logger.info(f"💰 USE_CHEAPER_MODEL: {USE_CHEAPER_MODEL}")
    logger.info(f"🖼️ IMAGE_MODEL: {IMAGE_MODEL}, preview={IMAGE_SIZE_PREVIEW}, full={IMAGE_SIZE_FULL}")
    logger.info(f"⏱️ OpenAI timeout: {OPENAI_TIMEOUT}s, retries: {OPENAI_MAX_RETRIES}")
    logger.info(f"🖼️ image_limit default: {IMAGE_LIMIT_DEFAULT}, workers: {MAX_WORKERS}")
    # 개발 로컬 실행. Render는 gunicorn 사용 권장:
    # gunicorn -w 1 -k gthread --threads 8 -t 600 -b 0.0.0.0:$PORT mytales_api:app
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
