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
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 전역 설정
USE_CHEAPER_MODEL = True  # 비용 절약을 위한 저렴한 모델 사용
SKIP_IMAGES_BY_DEFAULT = False  # 기본적으로 이미지 생성
MAX_RETRIES = 3

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
    
    # 간단한 캐릭터 프로필 생성
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

# ───── 이미지 생성 ─────
def generate_image(chapter_content, character_profile, chapter_index):
    """DALL-E를 사용한 이미지 생성"""
    try:
        character_name = character_profile["name"]
        visual_desc = character_profile["canonical"]
        character_style = character_profile["visual_description"]
        
        # 챕터 정보 추출
        title = chapter_content.get("title", f"챕터 {chapter_index + 1}")
        paragraphs = chapter_content.get("paragraphs", [])
        illustration = chapter_content.get("illustration", "")
        
        # 장면 설명 생성
        if illustration:
            scene_description = illustration
        else:
            # 스토리 내용에서 핵심 키워드 추출
            story_text = " ".join(paragraphs)
            scene_description = f"{title}: {story_text[:100]}"
        
        # 매우 구체적이고 일관된 캐릭터 설명이 포함된 프롬프트
        full_prompt = f"""
        Children's book illustration for chapter {chapter_index + 1}: {scene_description}
        
        Main character: {character_name}, Canonical Visual Descriptor: {visual_desc}
        
        Style: Wide-angle scene showing the story environment. Character should be small and distant in the scene, not a close-up portrait. Focus on the story setting, background, and situation. Consistent children's book illustration style. Warm, colorful, friendly art style. Soft lighting, bright colors, cute and adorable atmosphere. Perfect for ages 5-9. Show the character from a distance as part of the larger scene, not as the main focus.
        """.strip()
        
        logger.info(f"🖼️ 이미지 생성 시작 (챕터 {chapter_index + 1}): {title}")
        logger.info(f"📖 장면 설명: {scene_description}")
        logger.info(f"👤 캐릭터: {character_name} - {character_style}")
        logger.info(f"🎨 프롬프트: {full_prompt}")
        logger.info(f"📝 이 이미지는 텍스트박스{6 + chapter_index}의 동화 내용을 반영합니다")
        
        # 비용 절약을 위한 설정
        size = "512x512" if USE_CHEAPER_MODEL else "1024x1024"
        
        response = client.images.generate(
            prompt=full_prompt,
            size=size,
            n=1,
        )
        
        image_url = response.data[0].url
        logger.info(f"✅ 이미지 생성 완료 (챕터 {chapter_index + 1}): {image_url}")
        logger.info(f"📝 이 이미지는 텍스트박스{6 + chapter_index}의 동화 내용을 반영합니다")
        return image_url
    except Exception as e:
        logger.error(f"❌ 이미지 생성 오류 (챕터 {chapter_index + 1}): {e}")
        # API 오류 시 이미지 없이 진행
        if "429" in str(e) or "quota" in str(e).lower():
            logger.warning(f"⚠️ 이미지 생성 API 할당량 초과, 챕터 {chapter_index + 1} 이미지 건너뜀")
        return None

# ───── 스토리 생성 ─────
def generate_story_text_fallback(name, age, gender, topic):
    """API 없이 테스트용 동화 생성"""
    logger.info(f"📝 테스트용 동화 생성: {name}({age}세, {gender}) - {topic}")
    
    # 간단한 테스트 동화 데이터
    test_story = {
        "title": f"{name}의 {topic} 이야기",
        "character": f"{name}는 {age}세 {gender} 아이입니다",
        "chapters": [
            {
                "title": "아침 식사 시간",
                "paragraphs": [
                    f"{name}는 아침에 일어나서 식탁에 앉았어요.",
                    "엄마가 준비한 음식을 보니 {topic} 때문에 고민이 되었어요.",
                    "하지만 용기를 내어 새로운 음식을 먹어보기로 했어요."
                ],
                "illustration": f"아침 식탁에 앉아 있는 {name}. 식탁에는 다양한 음식이 놓여 있고, 창문으로 따뜻한 햇살이 들어와요. {name}은 작고 멀리서 보이는 모습으로, 식탁의 전체적인 분위기가 따뜻해요."
            },
            {
                "title": "친구와의 만남",
                "paragraphs": [
                    f"학교에서 친구들과 함께 점심을 먹을 때였어요.",
                    f"{name}는 친구들이 {topic}에 대해 이야기하는 것을 들었어요.",
                    "친구들의 조언을 듣고 마음을 바꾸기로 했어요."
                ],
                "illustration": f"학교 식당에서 친구들과 함께 점심을 먹고 있는 {name}. 식당에는 많은 학생들이 있고, 밝은 조명이 켜져 있어요. {name}은 작고 멀리서 보이는 모습으로, 식당의 활기찬 분위기가 느껴져요."
            },
            {
                "title": "도전의 순간",
                "paragraphs": [
                    f"집에 돌아온 {name}는 엄마에게 말했어요.",
                    f"'{topic}을 극복하고 싶어요!'라고 용감하게 말했어요.",
                    "엄마는 {name}의 용기를 칭찬해주었어요."
                ],
                "illustration": f"집 거실에서 엄마와 이야기하고 있는 {name}. 거실에는 소파와 테이블이 있고, 따뜻한 조명이 켜져 있어요. {name}은 작고 멀리서 보이는 모습으로, 가정의 따뜻한 분위기가 느껴져요."
            },
            {
                "title": "성공의 기쁨",
                "paragraphs": [
                    f"다음 날, {name}는 새로운 음식을 맛있게 먹었어요.",
                    f"{topic}을 극복한 {name}는 정말 기뻤어요.",
                    "엄마도 {name}의 성장을 자랑스러워했어요."
                ],
                "illustration": f"식탁에서 맛있게 식사하고 있는 {name}. 식탁에는 다양한 음식이 놓여 있고, 창문으로 밝은 햇살이 들어와요. {name}은 작고 멀리서 보이는 모습으로, 행복한 식사 시간의 분위기가 느껴져요."
            },
            {
                "title": "새로운 시작",
                "paragraphs": [
                    f"이제 {name}는 {topic}에 대해 두려워하지 않아요.",
                    "새로운 것에 도전하는 용기를 배웠어요.",
                    "앞으로도 계속 성장해 나갈 거예요!"
                ],
                "illustration": f"공원에서 친구들과 함께 놀고 있는 {name}. 공원에는 나무와 꽃이 있고, 밝은 햇살이 비치고 있어요. {name}은 작고 멀리서 보이는 모습으로, 즐거운 놀이 시간의 분위기가 느껴져요."
            }
        ],
        "ending": f"{name}는 {topic}을 극복하며 용기와 성장을 배웠어요. 앞으로도 새로운 도전을 두려워하지 않을 거예요!"
    }
    
    logger.info(f"✅ 테스트용 동화 생성 완료: {test_story.get('title')}")
    return test_story

def generate_story_text(name, age, gender, topic):
    """훈육 동화봇을 사용한 스토리 생성"""
    logger.info(f"📝 스토리 생성 시작: {name}({age}세, {gender}) - {topic}")
    prompt = f"""
당신은 "훈육 동화봇"입니다. 5~9세 아동을 위한 훈육 중심의 동화를 제작하는 데 최적화되어 있습니다.

## 🎯 목적
사용자가 입력한 정보를 기반으로, 5~9세 어린이가 공감하고 이해할 수 있는 짧고 따뜻한 동화를 생성합니다.
이야기는 재미와 감정, 교육적 가치를 담고 있으며, 훈육 주제에 대해 아이가 자연스럽게 공감하고 배울 수 있도록 구성됩니다.

## 📘 동화 구조
1. **도입** – 주인공 소개 및 상황 설명
2. **갈등** – 훈육 주제에 해당하는 문제 발생  
3. **도움** – 친구, 부모, 마법사 등 조력자 등장
4. **해결** – 주인공이 스스로 또는 도움을 받아 문제를 해결
5. **마무리** – 감정을 표현하고 교훈을 자연스럽게 전달

## 🎨 시각적 요소
각 챕터마다 구체적인 삽화 설명을 포함하세요:
- 예: "노란색 오리 인형을 안고 있는 아이가 방 한가운데 앉아 있어요. 방에는 책상과 침대가 있고, 창문으로 햇살이 들어와요"
- 배경과 환경을 자세히 설명 (방, 공원, 학교, 집 등)
- 캐릭터의 행동과 감정 상태
- 따뜻하고 귀여운 분위기
- 친숙한 동물, 장난감, 자연 배경 등 상상력을 자극하는 요소 활용

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
      "illustration": "매우 구체적인 삽화 설명 (예: 햇살이 비치는 창가에 혼자 앉아 있는 {name}, 곰 인형을 꼭 안고 있어요. 방에는 책상과 침대가 있고, 창문으로 밝은 햇살이 들어와요. {name}은 작고 멀리서 보이는 모습으로, 방의 전체적인 분위기가 슬픈 느낌이에요)"
    }}
  ],
  "ending": "마무리 메시지"
}}

요구사항:
- 이름: {name}, 나이: {age}, 성별: {gender}, 훈육주제: {topic}
- 총 5개 챕터로 구성
- 각 챕터는 "paragraphs" 리스트 형태로 2~4문장 나눠서 작성
- "illustration" 필드는 해당 챕터의 핵심 장면을 매우 구체적으로 설명 (배경, 환경, 캐릭터의 행동과 위치, 감정, 색깔, 표정 등). 캐릭터는 작고 멀리서 보이는 모습으로, 전체 장면의 분위기와 상황을 중심으로 설명
- 친근하고 따뜻한 말투, 짧고 간결한 문장 사용
- 반복과 리듬감을 살린 이야기체
- 아이의 눈높이에 맞춘 단어 선택
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
        
        logger.info(f"📝 원본 응답: {raw[:200]}...")
        logger.info(f"🧹 정리된 응답: {cleaned[:200]}...")
        
        try:
            result = json.loads(cleaned)
            logger.info(f"✅ JSON 파싱 성공: {result.get('title', '제목 없음')}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON 파싱 실패: {e}")
            logger.info(f"🔍 문제 위치: {cleaned[max(0, e.pos-50):e.pos+50]}")
            
            # 더 강력한 JSON 추출 시도
            try:
                # JSON 부분만 추출
                json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    logger.info(f"🔧 JSON 부분 추출 시도: {json_str[:200]}...")
                    result = json.loads(json_str)
                    logger.info(f"✅ JSON 재파싱 성공: {result.get('title', '제목 없음')}")
                    return result
            except Exception as e2:
                logger.error(f"❌ JSON 재파싱도 실패: {e2}")
            
            logger.warning("⚠️ API 응답 파싱 실패, 테스트용 동화 사용")
            return generate_story_text_fallback(name, age, gender, topic)
            
    except Exception as e:
        logger.error(f"❌ 스토리 생성 오류: {e}")
        if "429" in str(e) or "quota" in str(e).lower():
            logger.warning("⚠️ API 할당량 초과, 테스트용 동화 사용")
            return generate_story_text_fallback(name, age, gender, topic)
        else:
            logger.error(f"❌ 예상치 못한 오류: {e}")
            return generate_story_text_fallback(name, age, gender, topic)

def generate_story_with_images(name, age, gender, topic, generate_images=True):
    """스토리와 이미지를 함께 생성"""
    logger.info(f"🎨 스토리+이미지 생성 시작: {name}({age}세, {gender}) - {topic}")
    
    # 캐릭터 프로필 생성
    character_profile = generate_character_profile(name, age, gender)
    logger.info(f"👶 캐릭터 프로필 생성: {character_profile['name']} - {character_profile['visual_description']}")
    
    # 스토리 생성
    story = generate_story_text(name, age, gender, topic)
    logger.info(f"📝 스토리 생성 시작: {name}({age}세, {gender}) - {topic}")
    
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
    logger.info(f"📋 매칭 정보: 텍스트박스6↔이미지1, 텍스트박스7↔이미지2, ...")
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
        generate_images = data.get("generate_images", True)  # 기본적으로 이미지 생성
        use_fast_mode = data.get("fast_mode", True)  # 빠른 모드 옵션 추가

        logger.info(f"📝 요청 데이터: {name}, {age}, {gender}, {topic}, 이미지생성: {generate_images}, 빠른모드: {use_fast_mode}")

        if not all([name, age, gender, topic]):
            logger.error("❌ 입력 데이터 누락")
            return jsonify({"error": "입력 누락"}), 400

        logger.info("🎨 동화 생성 시작...")
        
        # 빠른 모드 설정 적용 (저렴한 모델 사용하되 이미지는 유지)
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

# ───── 추가 API 엔드포인트 ─────
@app.route("/api/get-story", methods=["GET"])
def get_story():
    story_data = session.get('story_result')
    if not story_data:
        return jsonify({"error": "스토리 데이터 없음"}), 404
    return jsonify(story_data)

@app.route("/health", methods=["GET", "OPTIONS"])
def health_check():
    """서버 상태 확인"""
    
    # CORS preflight 요청 처리
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
    
    # CORS preflight 요청 처리
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

@app.route("/test", methods=["GET", "POST", "OPTIONS"])
def test_endpoint():
    """테스트용 엔드포인트"""
    
    # CORS preflight 요청 처리
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return response
    
    logger.info("🔬 Test endpoint 요청")
    
    if request.method == "POST":
        data = request.get_json(force=True)
        logger.info(f"📝 POST 데이터: {data}")
    
    response = jsonify({
        "message": "테스트 성공!",
        "method": request.method,
        "timestamp": time.time(),
        "data": request.get_json(force=True) if request.method == "POST" else None
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