from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import os
import json
import re
import time
import logging
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI 클라이언트 초기화
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 전역 설정
USE_CHEAPER_MODEL = True  # 비용 절약을 위한 저렴한 모델 사용
SKIP_IMAGES_BY_DEFAULT = False  # 기본적으로 이미지 생성

# ───── 캐릭터 프로필 생성 ─────
def generate_character_profile(name, age, gender):
    """캐릭터의 시각적 프로필 생성"""
    logger.info(f"👶 캐릭터 프로필 생성: {name} - {age}세 {gender}")
    
    # 다양한 헤어스타일과 옷 스타일
    hair_styles = [
        "짧은 갈색 곱슬머리", "긴 검은 머리", "웨이브 밤색 머리", 
        "짧은 금발 머리", "포니테일 머리", "보브 스타일 머리"
    ]
    outfits = [
        "노란 셔츠와 파란 멜빵", "분홍 스웨터와 청바지", "하늘색 드레스",
        "빨간 후드티와 검은 바지", "초록 체크 셔츠와 카키 바지", "보라색 원피스"
    ]
    
    import random
    hair_style = random.choice(hair_styles)
    outfit = random.choice(outfits)
    
    character_profile = {
        "name": name,
        "age": age,
        "gender": gender,
        "visual_description": f"{hair_style}, 착용: {outfit}",
        "canonical": f"{name} is a {age}-year-old {gender} child with {hair_style}, wearing {outfit}. Round face with soft cheeks, warm brown almond eyes, childlike proportions, friendly and cute appearance. This exact same character must appear consistently in every scene with identical appearance."
    }
    
    logger.info(f"✅ 캐릭터 프로필 생성 완료: {name} - {hair_style}, 착용: {outfit}")
    return character_profile

# ───── 이미지 생성 (DALL-E 3 사용) ─────
def generate_image(chapter_content, character_profile, chapter_index):
    """DALL-E 3를 사용한 이미지 생성"""
    try:
        character_name = character_profile["name"]
        visual_desc = character_profile["canonical"]
        
        # 챕터 정보 추출
        title = chapter_content.get("title", f"챕터 {chapter_index + 1}")
        paragraphs = chapter_content.get("paragraphs", [])
        illustration = chapter_content.get("illustration", "")
        
        # 장면 설명 생성
        if illustration:
            scene_description = illustration
        else:
            story_text = " ".join(paragraphs)
            scene_description = f"{title}: {story_text[:100]}"
        
        # 프롬프트 생성
        full_prompt = f"""
        Children's book illustration for chapter {chapter_index + 1}: {scene_description}

        Main character: {character_name}, {visual_desc}

        Style: Wide-angle scene showing the story environment. Character should be small and distant in the scene, not a close-up portrait. Focus on the story setting, background, and situation. Consistent children's book illustration style. Warm, colorful, friendly art style. Soft lighting, bright colors, cute and adorable atmosphere. Perfect for ages 5-9.
        """.strip()
        
        logger.info(f"🖼️ 이미지 생성 시작 (챕터 {chapter_index + 1}): {title}")

        response = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        
        image_url = response.data[0].url
        logger.info(f"✅ 이미지 생성 완료 (챕터 {chapter_index + 1})")
        return image_url
    except Exception as e:
        logger.error(f"❌ 이미지 생성 오류 (챕터 {chapter_index + 1}): {e}")
        if "429" in str(e) or "quota" in str(e).lower():
            logger.warning(f"⚠️ DALL·E 3 할당량 초과, 챕터 {chapter_index + 1} 이미지 생략")
        return None

# ───── 스토리 생성 ─────
def generate_story_text(name, age, gender, topic):
    """훈육 동화봇을 사용한 스토리 생성"""
    logger.info(f"📝 스토리 생성 시작: {name}({age}세, {gender}) - {topic}")
    
    # API 연결 테스트
    try:
        # 간단한 API 연결 테스트
        test_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        logger.info("✅ API 연결 정상")
    except Exception as api_error:
        logger.error(f"❌ API 연결 실패: {api_error}")
        raise Exception(f"API 연결 실패: {api_error}")
    
    prompt = f"""
당신은 "훈육 동화봇"입니다. 5~9세 아동을 위한 훈육 중심의 동화를 제작하는 데 최적화되어 있습니다.

## 🎯 목적
사용자가 입력한 정보를 기반으로, 5~9세 어린이가 공감하고 이해할 수 있는 짧고 따뜻한 동화를 생성합니다.

## 📘 동화 구조
1. **도입** – 주인공 소개 및 상황 설명
2. **갈등** – 훈육 주제에 해당하는 문제 발생  
3. **도움** – 친구, 부모, 마법사 등 조력자 등장
4. **해결** – 주인공이 스스로 또는 도움을 받아 문제를 해결
5. **마무리** – 감정을 표현하고 교훈을 자연스럽게 전달

## 🎨 시각적 요소
각 챕터마다 구체적인 삽화 설명을 포함하세요:
- 배경과 환경을 자세히 설명 (방, 공원, 학교, 집 등)
- 캐릭터의 행동과 감정 상태
- 따뜻하고 귀여운 분위기

## ⚠️ 중요 지시사항
- 주인공 {name}은 모든 챕터에서 동일한 외모와 성격을 유지해야 합니다
- 각 챕터는 이전 챕터와 자연스럽게 연결되어야 합니다
- 삽화 설명은 해당 챕터의 핵심 장면을 정확히 반영해야 합니다

반드시 아래 JSON 형식만 응답하세요:

{{
  "title": "동화 제목",
  "character": "주인공 {name} 소개",
  "chapters": [
    {{
      "title": "챕터 제목",
      "paragraphs": ["문장1", "문장2", "문장3"],
      "illustration": "매우 구체적인 삽화 설명"
    }}
  ],
  "ending": "마무리 메시지"
}}

요구사항:
- 이름: {name}, 나이: {age}, 성별: {gender}, 훈육주제: {topic}
- 총 5개 챕터로 구성
- 각 챕터는 "paragraphs" 리스트 형태로 2~4문장 나눠서 작성
- "illustration" 필드는 해당 챕터의 핵심 장면을 매우 구체적으로 설명
- 친근하고 따뜻한 말투, 짧고 간결한 문장 사용
- 반드시 위 JSON 구조만 반환. 다른 텍스트나 설명 포함 금지.
""".strip()

    try:
        # 비용 절약을 위한 모델 선택
        model = "gpt-3.5-turbo" if USE_CHEAPER_MODEL else "gpt-4o"
        max_tokens = 1000 if USE_CHEAPER_MODEL else 1500
        
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON for a children's picture book."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=max_tokens,
        )

        raw = res.choices[0].message.content.strip()
        cleaned = re.sub(r'```(?:json)?', '', raw).strip()
        
        try:
            result = json.loads(cleaned)
            logger.info(f"✅ JSON 파싱 성공: {result.get('title', '제목 없음')}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON 파싱 실패: {e}")
            
            # JSON 부분만 추출
            try:
                json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    result = json.loads(json_str)
                    logger.info(f"✅ JSON 재파싱 성공: {result.get('title', '제목 없음')}")
                    return result
            except Exception as e2:
                logger.error(f"❌ JSON 재파싱도 실패: {e2}")
            
            raise Exception("API 응답 파싱 실패")
            
    except Exception as e:
        logger.error(f"❌ 스토리 생성 오류: {e}")
        raise Exception(f"스토리 생성 실패: {e}")

def generate_story_with_images(name, age, gender, topic, generate_images=True):
    """스토리와 이미지를 함께 생성"""
    logger.info(f"🎨 스토리+이미지 생성 시작: {name}({age}세, {gender}) - {topic}")
    
    # 캐릭터 프로필 생성
    character_profile = generate_character_profile(name, age, gender)
    
    # 스토리 생성
    story = generate_story_text(name, age, gender, topic)
    
    # 이미지 생성
    if generate_images and not SKIP_IMAGES_BY_DEFAULT:
        logger.info(f"📚 총 {len(story.get('chapters', []))}개 챕터에 이미지 생성 시작")
        for i, chapter in enumerate(story.get('chapters', [])):
            logger.info(f"🖼️ 챕터 {i+1} 이미지 생성 중...")
            image_url = generate_image(chapter, character_profile, i)
            if image_url:
                chapter['image_url'] = image_url
            else:
                logger.warning(f"⚠️ 챕터 {i+1} 이미지 생성 실패")
    
    # 결과 조합
    result = {
        "title": story.get("title"),
        "character_profile": character_profile,
        "chapters": story.get("chapters", []),
        "ending": story.get("ending", "")
    }
    
    logger.info(f"🎉 전체 동화+이미지 생성 완료: {result.get('title')}")
    return result

# ───── HTML 템플릿 라우트 ─────
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

# ───── API 엔드포인트 ─────
@app.route("/generate-full", methods=["POST", "OPTIONS"])
def generate_full():
    """Wix에서 호출하는 메인 API 엔드포인트"""
    
    # CORS preflight 요청 처리
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response
    
    try:
        logger.info("🚀 /generate-full 요청 시작")
        
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        age = data.get("age", "").strip()
        gender = data.get("gender", "").strip()
        topic = data.get("topic", data.get("education_goal", "")).strip()
        generate_images = data.get("generate_images", True)
        use_fast_mode = data.get("fast_mode", True)

        logger.info(f"📝 요청 데이터: {name}, {age}, {gender}, {topic}, 이미지생성: {generate_images}, 빠른모드: {use_fast_mode}")

        if not all([name, age, gender, topic]):
            logger.error("❌ 입력 데이터 누락")
            return jsonify({"error": "입력 누락"}), 400

        logger.info("🎨 동화 생성 시작...")
        
        # 빠른 모드 설정 적용
        if use_fast_mode:
            global USE_CHEAPER_MODEL
            USE_CHEAPER_MODEL = True
        
        # 이미지 생성 여부에 따라 다른 함수 사용
        if generate_images:
            result = generate_story_with_images(name, age, gender, topic, generate_images)
        else:
            character = generate_character_profile(name, age, gender)
            story = generate_story_text(name, age, gender, topic)
            result = {
                "title": story.get("title"),
                "character_profile": character,
                "chapters": story.get("chapters", []),
                "ending": story.get("ending", "")
            }

        logger.info(f"✅ 동화 생성 완료: {result.get('title')}")
        
        # CORS 헤더 추가
        response = jsonify(result)
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        
        return response

    except Exception as e:
        logger.error(f"❌ /generate-full 오류: {str(e)}")
        error_response = jsonify({"error": f"서버 오류: {str(e)}"})
        error_response.headers.add("Access-Control-Allow-Origin", "*")
        error_response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        error_response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        error_response.headers.add("Access-Control-Allow-Credentials", "true")
        return error_response, 500

@app.route("/health", methods=["GET", "OPTIONS"])
def health_check():
    """서버 상태 확인"""
    
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return response
    
    logger.info("🏥 Health check 요청")
    response = jsonify({"status": "healthy", "timestamp": time.time()})
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response

@app.route("/simple-test", methods=["GET", "POST", "OPTIONS"])
def simple_test():
    """간단한 테스트 엔드포인트"""
    
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return response
    
    logger.info("🧪 Simple test 요청")
    response = jsonify({
        "message": "서버가 정상 작동 중입니다!",
        "timestamp": time.time(),
        "status": "success"
    })
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response

if __name__ == "__main__":
    logger.info("🚀 MyTales AI 서버 시작")
    logger.info(f"💰 저렴한 모델 사용: {USE_CHEAPER_MODEL}")
    logger.info(f"🖼️ 이미지 생성 기본값: {not SKIP_IMAGES_BY_DEFAULT}")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
