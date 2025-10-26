from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, json, re, time, logging, random
from dotenv import load_dotenv

# ─────────────────────────────
# 환경
# ─────────────────────────────
load_dotenv()
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────
# 전역 옵션
# ─────────────────────────────
USE_CHEAPER_MODEL = False   # True: 저렴/빠름, False: 고품질
SKIP_IMAGES_BY_DEFAULT = False

# 모델 선택
def pick_model():
    return "gpt-4o-mini" if USE_CHEAPER_MODEL else "o4-mini"

# ─────────────────────────────
# 유틸
# ─────────────────────────────
def clean_json_blocks(s: str) -> str:
    s = re.sub(r"```(?:json)?", "", s).strip()
    s = s.strip("` \n\t")
    return s

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

# ─────────────────────────────
# 캐릭터 프로필
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    age = clamp_age(age)
    hair_styles = [
        "짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리",
        "짧은 금발 머리", "포니테일 머리", "보브 컷"
    ]
    outfits = [
        "노란 셔츠+파란 멜빵", "분홍 스웨터+청바지", "하늘색 원피스",
        "빨간 후드+검은 바지", "초록 체크 셔츠+카키 바지", "보라색 원피스"
    ]
    hair = random.choice(hair_styles)
    outfit = random.choice(outfits)

    # 일관성 앵커 토큰
    anchor = f"<<{name}-{age}-{gender}>>"

    canonical_ko = f"{hair}, {outfit} 착용. 둥근 얼굴, 부드러운 볼, 따뜻한 갈색 아몬드형 눈. 아이 체형. 친근하고 사랑스러운 인상. 모든 장면에서 동일한 외형 유지."
    canonical_en = (f"{anchor} is a {age}-year-old {gender} child. {hair}. Wearing {outfit}. "
                    "Round face with soft cheeks, warm brown almond eyes, childlike proportions. "
                    "The exact same character must appear consistently in every scene with identical appearance.")

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

# ─────────────────────────────
# 스토리 생성
# ─────────────────────────────
def story_prompt(name, age, gender, topic, anchor, lang="ko"):
    return f"""
당신은 5~9세 아동용 감성 그림책 작가 겸 편집자다.
목표: 아이가 스스로 깨닫는 교훈을 자연스럽게 체화하게 만든다. 설교 금지. 경험 통한 깨달음.

출력언어: 한국어.
주요 정보: 이름={name}, 나이={age}, 성별={gender}, 훈육주제='{topic}', 캐릭터앵커='{anchor}'.

작성 규칙:
- 총 5개 챕터. 각 챕터 paragraphs 2~4문장. 짧고 리듬감 있게.
- 도입→갈등→깨달음→변화→희망의 구조.
- {name}의 성격과 감정을 장면으로 보여주기. '느꼈다'보다 '보여주기'.
- 설교형 문장 금지. 대사와 행동으로 전달.
- 각 챕터에 일러스트 설명 'illustration' 필수: 장면, 구도(카메라), 배경, 소품, 빛, 색감, 상징, {anchor} 외형 유지 지시 포함.

반드시 아래 JSON만 반환:
{{
  "title": "짧고 상징적인 제목",
  "character": "주인공 {name}의 한 줄 소개",
  "chapters": [
    {{
      "title": "챕터 제목",
      "paragraphs": ["문장1", "문장2"],
      "illustration": "구체적 장면/구도/색/상징/감정/환경. '{anchor}' 외형 동일 지시 포함"
    }}
  ],
  "ending": "따뜻한 마무리 한 단락"
}}
""".strip()

def generate_story_text(name, age, gender, topic):
    logger.info(f"📝 스토리 생성: {name}/{age}/{gender}/{topic}")
    model = pick_model()
    prompt = story_prompt(name, clamp_age(age), gender, topic, anchor=generate_character_profile(name, age, gender)["anchor"])

    # system 메시지로 JSON 강제
    sys = (
        "You are a senior children's picture-book writer. "
        "Return only strict JSON that conforms exactly to the user's schema. "
        "No markdown fences. Korean output."
    )

    # 1회 시도 후 보정 1회
    for attempt in range(2):
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,   # 일관성↑
            max_tokens=1400,
            response_format={"type": "json_object"}
        )
        raw = clean_json_blocks(resp.choices[0].message.content)
        try:
            data = try_json_load(raw)
            # 간단 유효성 체크
            assert "chapters" in data and len(data["chapters"]) == 5
            for ch in data["chapters"]:
                assert "paragraphs" in ch and 2 <= len(ch["paragraphs"]) <= 4
                assert "illustration" in ch and len(ch["illustration"]) >= 30
            return data
        except Exception as e:
            logger.warning(f"JSON 보정 재시도 {attempt+1}: {e}")
            prompt += "\n\n주의: 스키마 불일치. 정확히 5개 챕터, 각 2~4문장, illustration 자세히."

    raise RuntimeError("스토리 JSON 생성 실패")

# ─────────────────────────────
# 이미지 생성
# ─────────────────────────────
def build_image_prompt(chapter_content, character_profile, chapter_index):
    title = chapter_content.get("title", f"챕터 {chapter_index+1}")
    illu = chapter_content.get("illustration", "")
    anchor = character_profile["anchor"]
    canonical = character_profile["canonical"]

    # 일관성 강제용 템플릿
    prompt = f"""
Children's picture book illustration, chapter {chapter_index+1}: "{title}"

Story beat:
{illu}

Main character:
{canonical}
Always include the hidden anchor token {anchor} in description for consistency.

Art direction:
- Wide composition that shows environment and context
- Character medium size, readable expression
- Soft lighting, warm palette, gentle textures, ages 5–9 friendly
- Clean silhouette, simple background clutter, clear focal point
- Subtle symbolic elements that reflect the moral theme
- Cohesive style across all scenes, same character appearance

Output: a single coherent illustration for the scene. No text, no collage, no split panels.
""".strip()
    return prompt

def generate_image(chapter_content, character_profile, chapter_index):
    try:
        prompt = build_image_prompt(chapter_content, character_profile, chapter_index)
        logger.info(f"🖼️ 이미지 생성: 챕터 {chapter_index+1}")
        img = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        return img.data[0].url
    except Exception as e:
        logger.error(f"이미지 생성 실패 {chapter_index+1}: {e}")
        return None

# ─────────────────────────────
# 스토리+이미지 파이프라인
# ─────────────────────────────
def generate_story_with_images(name, age, gender, topic, generate_images=True):
    # 캐릭터 먼저 확정
    character_profile = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)

    # 이미지
    if generate_images and not SKIP_IMAGES_BY_DEFAULT:
        for i, ch in enumerate(story.get("chapters", [])):
            url = generate_image(ch, character_profile, i)
            if url:
                ch["image_url"] = url

    return {
        "title": story.get("title"),
        "character_profile": character_profile,
        "chapters": story.get("chapters", []),
        "ending": story.get("ending", "")
    }

# ─────────────────────────────
# 템플릿 라우트
# ─────────────────────────────
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

# ─────────────────────────────
# API
# ─────────────────────────────
@app.route("/generate-full", methods=["POST", "OPTIONS"])
def generate_full():
    if request.method == "OPTIONS":
        r = jsonify({"status": "ok"})
        r.headers.add("Access-Control-Allow-Origin", "*")
        r.headers.add("Access-Control-Allow-Headers", "Content-Type")
        r.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return r

    try:
        logger.info("🚀 /generate-full")
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        age = (data.get("age") or "").strip()
        gender = (data.get("gender") or "").strip()
        topic = (data.get("topic") or data.get("education_goal") or "").strip()
        generate_images = bool(data.get("generate_images", True))
        use_fast_mode = bool(data.get("fast_mode", True))

        if not all([name, age, gender, topic]):
            return jsonify({"error": "입력 누락"}), 400

        # 모드 반영
        global USE_CHEAPER_MODEL
        USE_CHEAPER_MODEL = use_fast_mode

        if generate_images:
            result = generate_story_with_images(name, age, gender, topic, True)
        else:
            cp = generate_character_profile(name, age, gender)
            st = generate_story_text(name, age, gender, topic)
            result = {"title": st.get("title"), "character_profile": cp,
                      "chapters": st.get("chapters", []), "ending": st.get("ending", "")}

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

if __name__ == "__main__":
    logger.info("🚀 MyTales AI 서버 시작")
    logger.info(f"💰 저렴한 모델 사용: {USE_CHEAPER_MODEL}")
    logger.info(f"🖼️ 이미지 생성 기본값: {not SKIP_IMAGES_BY_DEFAULT}")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
