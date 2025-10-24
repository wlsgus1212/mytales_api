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
        
        # DALL-E 3용 프롬프트 생성 (더 상세하고 구체적으로)
        full_prompt = f"""
        A beautiful, high-quality children's book illustration for chapter {chapter_index + 1}: {scene_description}

        CHARACTER DETAILS:
        - Main character: {character_name}
        - Character appearance: {visual_desc}
        - Character must be clearly visible but not dominating the scene

        SCENE REQUIREMENTS:
        - Show the specific story situation described: {scene_description}
        - Include all relevant story elements and objects mentioned
        - Create a warm, inviting atmosphere suitable for children ages 5-9
        - Use bright, cheerful colors with soft lighting
        - Include detailed background elements that support the story

        ARTISTIC STYLE:
        - High-quality children's book illustration style
        - Clean, detailed artwork with clear composition
        - Professional digital art quality
        - Warm and friendly color palette
        - Soft shadows and gentle lighting
        - Character should be medium-sized in the scene, not tiny or huge

        COMPOSITION:
        - Wide-angle view showing the story environment
        - Character positioned naturally within the scene
        - Background elements that enhance the story context
        - Balanced composition with clear focal points
        - Professional book illustration quality

        The illustration must accurately reflect the story content and create an engaging visual narrative that complements the text.
        """.strip()
        
        logger.info(f"🖼️ 이미지 생성 시작 (챕터 {chapter_index + 1}): {title}")

        response = client.images.generate(
            prompt=full_prompt,
            size="1024x1024",
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
당신은 "교훈 중심 훈육 동화봇"입니다. 5~9세 아동을 위한 가치관과 교훈을 통해 근본적인 변화를 이끌어내는 동화를 제작하는 데 최적화되어 있습니다.

## 🎯 목적
사용자가 입력한 훈육 주제를 통해 아이들이 근본적으로 바뀌도록, 교훈과 가치관을 자연스럽게 전달하는 동화를 생성합니다. 단순한 문제 해결이 아닌, 내면의 성장과 변화를 이끌어냅니다.

## 🌟 교훈 중심 접근법
- **가치관 전달**: 올바른 가치관과 태도를 자연스럽게 전달
- **감정적 공감**: 아이들이 공감할 수 있는 감정적 경험 제공
- **성장의 과정**: 문제 해결 과정에서의 내면적 성장 강조
- **의미 있는 교훈**: 단순한 해결책이 아닌 깊이 있는 교훈 전달

## 📘 동화 구조 (교훈 중심)
1. **도입** – 주인공의 현재 상태와 내면의 갈등 소개
2. **갈등과 깨달음** – 문제 상황을 통해 주인공이 깨닫는 과정
3. **교훈과 가치관** – 올바른 가치관과 태도를 배우는 과정
4. **내면의 변화** – 주인공의 마음과 태도가 근본적으로 바뀌는 과정
5. **성장과 희망** – 새로운 가치관으로 더 나은 미래를 향하는 희망적 마무리

## 🎨 시각적 요소
각 챕터마다 구체적인 삽화 설명을 포함하세요:
- 주인공의 감정과 내면 상태를 보여주는 배경
- 교훈과 가치관을 상징하는 요소들
- 성장과 변화를 나타내는 시각적 요소
- 따뜻하고 감동적인 분위기

## ⚠️ 중요 지시사항
- 주인공 {name}은 모든 챕터에서 동일한 외모와 성격을 유지해야 합니다
- 각 챕터는 이전 챕터와 자연스럽게 연결되어야 합니다
- 삽화 설명은 해당 챕터의 핵심 장면을 정확히 반영해야 합니다
- 교훈과 가치관은 훈육 주제와 자연스럽게 연결되어야 합니다

## 🌟 훈육 주제별 교훈 중심 접근법
- **편식**: "다양한 음식의 소중함과 건강한 몸의 중요성"을 깨닫는 과정
- **정리정돈**: "정리된 공간의 편안함과 질서의 가치"를 이해하는 과정
- **예의**: "예의바른 태도가 주는 따뜻함과 소중함"을 경험하는 과정
- **용기**: "용기를 내면 얻을 수 있는 새로운 경험과 성장"을 깨닫는 과정

## 💡 교훈 전달 방법
- **직접적 설교 금지**: "해야 한다"는 식의 직접적 지시 금지
- **경험을 통한 깨달음**: 주인공이 직접 경험하며 깨닫는 과정 강조
- **감정적 공감**: 아이들이 공감할 수 있는 감정적 경험 제공
- **자연스러운 교훈**: 이야기 속에서 자연스럽게 교훈이 전달되도록

반드시 아래 JSON 형식만 응답하세요:

{{
  "title": "동화 제목",
  "character": "주인공 {name} 소개",
  "chapters": [
    {{
      "title": "챕터 제목",
      "paragraphs": ["문장1", "문장2", "문장3"],
      "illustration": "매우 구체적인 삽화 설명 (교훈과 가치관을 상징하는 요소 포함)"
    }}
  ],
  "ending": "마무리 메시지 (교훈과 희망적 메시지 포함)"
}}

요구사항:
- 이름: {name}, 나이: {age}, 성별: {gender}, 훈육주제: {topic}
- 총 5개 챕터로 구성
- 각 챕터는 "paragraphs" 리스트 형태로 2~4문장 나눠서 작성
- "illustration" 필드는 해당 챕터의 핵심 장면을 매우 구체적으로 설명 (교훈과 가치관을 상징하는 요소 포함)
- 친근하고 따뜻한 말투, 짧고 간결한 문장 사용
- 교훈과 가치관을 자연스럽게 전달하는 스토리 구성
- 반드시 위 JSON 구조만 반환. 다른 텍스트나 설명 포함 금지.
""".strip()

    try:
        # 비용 절약을 위한 모델 선택
        model = "gpt-3.5-turbo" if USE_CHEAPER_MODEL else "gpt-4o"
        max_tokens = 1000 if USE_CHEAPER_MODEL else 1500
        
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON for a children's picture book with meaningful lessons."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,  # 교훈 전달을 위해 적절한 창의성
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
