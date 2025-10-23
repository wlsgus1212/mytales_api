from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, json, time, base64, logging
from io import BytesIO
from PIL import Image
import requests

# ───── 로깅 설정 ─────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ───── 환경 설정 ─────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    logger.error("OPENAI_API_KEY not found!")
    raise RuntimeError("OPENAI_API_KEY not found.")

logger.info("🚀 MyTales 서버 시작 중...")
logger.info(f"OpenAI API Key 설정됨: {API_KEY[:10]}...")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
app.secret_key = 'mytales_secret_key_2024'  # 세션을 위한 시크릿 키

logger.info("✅ Flask 앱 초기화 완료")

# ───── 유틸 함수 ─────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face with soft cheeks; warm brown almond eyes; childlike proportions."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit,
            "face": "부드러운 볼의 둥근 얼굴",
            "eyes": "따뜻한 갈색 아몬드형 눈",
            "proportions": "아이 같은 비율"
        }
    }

# ───── 이미지 생성 함수 ─────
def generate_image(chapter_content, character_profile, chapter_index):
    """DALL-E를 사용하여 동화 이미지 생성"""
    try:
        # 챕터 내용 추출
        title = chapter_content.get("title", "")
        paragraphs = chapter_content.get("paragraphs", [])
        illustration_desc = chapter_content.get("illustration", "")
        
        # 캐릭터 정보
        character_name = character_profile.get("name", "")
        character_style = character_profile.get("style", "")
        
        # illustration 필드를 우선 사용하고, 없으면 스토리 내용 사용
        if illustration_desc and len(illustration_desc.strip()) > 10:
            scene_description = illustration_desc
        else:
            # 스토리 내용에서 핵심 키워드 추출
            story_text = " ".join(paragraphs)
            scene_description = story_text[:150]
        
        # 간단하고 명확한 프롬프트
        full_prompt = f"Children's book illustration: {scene_description}. Character: {character_name}, {character_style}. Bright, warm colors, friendly style."
        
        logger.info(f"🖼️ 이미지 생성 시작 (챕터 {chapter_index + 1}): {title}")
        logger.info(f"📖 장면 설명: {scene_description}")
        logger.info(f"🎨 프롬프트: {full_prompt}")
        
        response = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        logger.info(f"✅ 이미지 생성 완료 (챕터 {chapter_index + 1}): {image_url}")
        return image_url
    except Exception as e:
        logger.error(f"❌ 이미지 생성 오류 (챕터 {chapter_index + 1}): {e}")
        return None

# ───── 스토리 생성 ─────
def generate_story_text(name, age, gender, topic):
    logger.info(f"📝 스토리 생성 시작: {name}({age}세, {gender}) - {topic}")
    prompt = f"""
당신은 5~9세 어린이를 위한 따뜻하고 리드미컬한 동화 작가입니다.

반드시 아래 JSON 형식만 응답하세요:

{{
  "title": "",
  "character": "",
  "chapters": [
    {{
      "title": "",
      "paragraphs": ["", ""],
      "illustration": "구체적인 장면 설명 (예: 아이가 공원에서 친구와 놀고 있는 모습, 밝은 색깔의 나무와 꽃이 있는 배경)"
    }}
  ],
  "ending": ""
}}

요구사항:
- 이름: {name}, 나이: {age}, 성별: {gender}, 훈육주제: {topic}
- 총 5개 챕터
- 각 챕터는 "paragraphs" 리스트 형태로 2~4문장 나눠서 작성
- 각 챕터는 "title", "paragraphs", "illustration" 포함
- "illustration" 필드는 해당 챕터의 핵심 장면을 구체적으로 설명 (배경, 행동, 감정 등)
- 마지막에 "ending" 추가
- 반드시 위 JSON 구조만 반환. 다른 텍스트나 설명 포함 금지.
""".strip()

    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Respond only with valid JSON for a children's picture book."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1500,
        )

        raw = res.choices[0].message.content.strip()
        cleaned = re.sub(r'```(?:json)?', '', raw).strip()
        try:
            result = json.loads(cleaned)
            logger.info(f"✅ 스토리 생성 완료: {result.get('title', '제목 없음')}")
            return result
        except:
            m = re.search(r'(\{[\s\S]+\})', cleaned)
            result = json.loads(m.group(1)) if m else {}
            logger.warning("⚠️ JSON 파싱 재시도 성공")
            return result
    except Exception as e:
        logger.error(f"❌ 스토리 생성 오류: {e}")
        return {}

def generate_story_with_images(name, age, gender, topic):
    """스토리와 이미지를 함께 생성"""
    logger.info(f"🎨 스토리+이미지 생성 시작: {name}({age}세, {gender}) - {topic}")
    
    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)
    
    # 각 챕터에 이미지 생성
    chapters = story.get("chapters", [])
    logger.info(f"📚 총 {len(chapters)}개 챕터에 이미지 생성 시작")
    
    for i, chapter in enumerate(chapters):
        logger.info(f"🖼️ 챕터 {i+1} 이미지 생성 중...")
        image_url = generate_image(chapter, character, i)
        chapter["image_url"] = image_url
        
        if image_url:
            logger.info(f"✅ 챕터 {i+1} 이미지 생성 완료")
        else:
            logger.warning(f"⚠️ 챕터 {i+1} 이미지 생성 실패")
    
    result = {
        "title": story.get("title"),
        "character_profile": character,
        "chapters": chapters,
        "ending": story.get("ending", "")
    }
    
    logger.info(f"🎉 전체 동화+이미지 생성 완료: {result.get('title')}")
    return result

# ───── 라우트 정의 ─────
@app.route("/")
def home():
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

# ───── API 엔드포인트 ─────
@app.route("/generate-full", methods=["POST"])
def generate_full():
    """Wix에서 호출하는 메인 API 엔드포인트"""
    try:
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        age = data.get("age", "").strip()
        gender = data.get("gender", "").strip()
        topic = data.get("topic", data.get("education_goal", "")).strip()
        generate_images = data.get("generate_images", True)

        print(f"📝 요청 받음: {name}, {age}, {gender}, {topic}")

        if not all([name, age, gender, topic]):
            return jsonify({"error": "입력 누락"}), 400

        # 이미지 생성 여부에 따라 다른 함수 사용
        if generate_images:
            result = generate_story_with_images(name, age, gender, topic)
        else:
            character = generate_character_profile(name, age, gender)
            story = generate_story_text(name, age, gender, topic)
            result = {
                "title": story.get("title"),
                "character_profile": character,
                "chapters": story.get("chapters", []),
                "ending": story.get("ending", "")
            }

        print(f"✅ 동화 생성 완료: {result.get('title')}")
        return jsonify(result)

    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500

# ───── 추가 API 엔드포인트 ─────
@app.route("/api/get-story", methods=["GET"])
def get_story():
    story_data = session.get('story_result')
    if not story_data:
        return jsonify({"error": "스토리 데이터 없음"}), 404
    return jsonify(story_data)

@app.route("/health", methods=["GET"])
def health_check():
    """서버 상태 확인"""
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route("/test", methods=["POST"])
def test_generation():
    """테스트용 동화 생성 (이미지 없이)"""
    try:
        data = request.get_json(force=True)
        name = data.get("name", "테스트")
        age = data.get("age", "6")
        gender = data.get("gender", "남자")
        topic = data.get("topic", "친구와의 우정")
        
        character = generate_character_profile(name, age, gender)
        story = generate_story_text(name, age, gender, topic)
        
        return jsonify({
            "title": story.get("title"),
            "character_profile": character,
            "chapters": story.get("chapters", []),
            "ending": story.get("ending", "")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ───── 실행 ─────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
