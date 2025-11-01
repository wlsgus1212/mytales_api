# mytales_ai.py

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os
import time
import logging
import re

# ─────────────────────
# 환경 설정
# ─────────────────────
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    # 서비스 배포 전 .env 설정 필수
    # mock 모드만 쓸 거면 여기서 죽이지 않고 넘어가도 됨
    logging.warning("OPENAI_API_KEY not found. Only mock mode will work.")
client = OpenAI(api_key=API_KEY) if API_KEY else None

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s"
)
logger = logging.getLogger("mytales")

# ─────────────────────
# 금지 결말 패턴 필터
# 직접 해결/즉시 교정/즉시 착해짐/즉시 화해 등을 막는다
# ─────────────────────
BANNED_PATTERNS = [
    "맛있었", "괜찮았어요", "이제 혼자서 잘 해요",
    "짜증을 안 내", "짜증을 안냈", "짜증을 참았", "짜증을 참고",
    "화해해서 행복했어요", "둘은 다시는 싸우지 않았어요",
    "착한 아이가 되었어요", "칭찬을 받았어요",
    "엄마가 칭찬했어요", "엄마가 기뻐했어요",
    "아빠가 칭찬했어요", "선생님이 칭찬했어요",
    "다시는 안 그랬어요"
]

def violates_banned_resolution(story_text: str) -> bool:
    if not story_text:
        return False
    for pat in BANNED_PATTERNS:
        if pat in story_text:
            return True
    return False

# ─────────────────────
# 프롬프트 템플릿
# 설명:
# - 어떤 훈육 주제든 적용 가능
# - 해결을 "바로 행동 교정 성공"으로 끝내지 말고
#   상징/상상/감각/뱃지 같은 간접 보상으로 마무리
# - 각 scene은 text와 image_guide를 동시에 낸다
# - image_guide 안에 캐릭터 외형, 옷, 조명, 공간, 포즈, 감정까지 고정
# - must_keep은 다음 장면에서도 유지해야 하는 시각적 요소
#   (캐릭터 얼굴/머리/옷/팔레트/조명 등)
# - 한 문장은 짧게. 어려운 단어 금지.
# - 부모의 설교나 "하지마" 금지.
# - 부모 칭찬 엔딩 금지.
# - 직접적 해결 선언 금지.
# 출력은 반드시 유효한 JSON 형태로.
# ─────────────────────
PROMPT_TEMPLATE = """
너는 5~9세 어린이를 위한 훈육 중심 감성 동화 작가이자 그림책 연출가다.
입력 정보:
- 아이 이름: {name}
- 나이: {age}살
- 성별: {gender}아이
- 훈육 주제: {goal}

목표:
- 아이를 혼내지 않는다.
- "하지 마" "그만해" 같은 직접 통제 금지.
- 부모의 칭찬으로 끝내지 않는다.
- "바로 고쳐졌어요" 같은 즉시 해결 금지.
- 대신 아이가 새로운 느낌, 이미지, 상상, 상징적 보상을 얻게 한다.
  예: 조용히 숨을 쉬면 짜증 요정이 잠든다.
      채소를 한입 보면 눈 속에 반짝 게이지가 생긴다.
      친구와 싸우면 싸움 괴물이 꿈에 나타나서 시끄럽다 등.
- 아이는 "다음에 또 해볼까?" 또는 "이건 내가 가진 힘일 수도 있어" 수준의
  조용한 호기심으로 마무리한다.
- 두려움 공포 협박식 표현 금지. 무서운 벌 금지.
- 너무 어려운 단어 금지. 몸짓/표정으로 감정 표현.

장면 구성 규칙:
- 총 6장면.
- 장면1: 공감. 아이가 실제로 느끼는 불편함, 짜증, 거부감, 마음 상태.
- 장면2: 고립. 혼자 속상하거나 생각하는 순간.
- 장면3: 조력자 등장. (성별에 따른 선호 반영. 여자아이면 요정/작은 동물/별/꽃/인형.
  남자아이면 로봇/공룡/번개 요정/탈것/하늘 새 등)
  조력자는 명령하지 않고 "같이 보자" "나는 이런 걸 봤어" 식으로 제안.
- 장면4: 상징적 제안. 조력자가 특별한 비유나 힘을 알려준다
  (예: 숨을 천천히 쉬면 마음 안의 붉은 불꽃이 작아진다,
        당근은 눈 속에 반짝힘 게이지를 채운다 등)
- 장면5: 아이의 작은 시도. 아주 작은 행동. 완벽하지 않아도 된다.
  결과를 "성공"이라 부르지 말고, "몸에서 조금 다른 느낌"으로 묘사.
- 장면6: 여운. 아직 문제는 100% 안 끝났다. 하지만 아이 안에
  새로운 상징(뱃지, 빛, 조용한 힘)이 생겼다. 그걸 아이가 알아챈다.
  부모 칭찬 없이 아이 스스로 느끼는 조용한 만족감.

문체 규칙:
- 5~9세가 이해 가능한 말.
- 추상어 금지. (예: "성실", "인내심", "배려" 이런 단어 쓰지 말기)
- 감정은 행동/표정으로만. ("화났다" 대신 "입이 꾹 다물렸어요. 볼이 빨갰어요.")
- 한 문장은 짧게. 부드럽게.
- 과격/공포/혐오 묘사 금지.
- 거친 폭력 금지.
- "너는 나쁜 아이가 아니야" "착한 아이지" 같은 도덕 라벨 금지.

이미지 연출 가이드:
- 우리는 장면마다 그림도 만들 것이다.
- 그래서 각 장면마다 "image_guide"를 함께 만든다.
- image_guide는 수채화 풍 그림 한 장에 들어갈 요소를 구체적으로 쓴다.
- 아이의 머리 모양, 옷, 조명, 방/장소를 반복해서 일관되게 써라.
- 매 장면마다 같은 아이, 같은 옷, 같은 헤어, 같은 색감.
- 톤: 파스텔 수채화 그림책.
- 잔혹하거나 무서운 표현 금지.
- 인체는 자연스럽고 건강하게.

전역 비주얼( global_visual ):
- hair: 아이 머리 스타일과 색
- outfit: 아이 옷
- palette: 전체 색감 (예 "soft orange and teal")
- lighting: 빛 분위기 (예 "부드러운 저녁 부엌 조명", "따뜻한 오후 햇살")
- location_base: 주 배경 공간 (예 "식탁 있는 주방", "아이 방 바닥에 앉아 있는 장난감 주변")
이 전역 비주얼은 모든 장면이 공유해야 한다.

각 장면 정보 형식:
- "text": 아이에게 읽어줄 짧은 동화 문단. 40~80자 정도. 문장 여러 개 가능.
- "image_guide": 그 장면 그림에 들어갈 구체 묘사. 누가 어디 앉아 있는지, 표정, 손, 주변 사물, 조력자 위치.
- "must_keep": 반복 유지해야 할 시각 요소들. hair, outfit, palette, lighting 은 반드시 포함.

엔딩:
- 부모 칭찬 없음.
- "다시는 안 그랬어요" 금지.
- "이제 잘 해요" 금지.
- 그냥 아이가 자기 안에 새로 생긴 감각이나 작은 힘을 살짝 느끼는 상태.

출력 형식:
아래 JSON 형식 그대로 출력해라. 불필요한 설명 금지. 키 이름 바꾸지 마라.

{{
 "title": "동화 제목",
 "protagonist": "{name} ({age}살 {gender}아이)",
 "global_visual": {{
   "hair": "예: 갈색 곱슬 단발",
   "outfit": "예: 노란 셔츠와 파란 멜빵",
   "palette": "예: soft orange and teal",
   "lighting": "예: 따뜻한 부엌 불빛",
   "location_base": "예: 식탁 있는 주방"
 }},
 "scenes": [
   {{
     "text": "장면1(공감).",
     "image_guide": "장면1 그림 설명.",
     "must_keep": {{
       "hair": "...",
       "outfit": "...",
       "palette": "...",
       "lighting": "...",
       "location": "..."
     }}
   }},
   {{
     "text": "장면2(고립).",
     "image_guide": "장면2 그림 설명.",
     "must_keep": {{
       "hair": "...",
       "outfit": "...",
       "palette": "...",
       "lighting": "...",
       "location": "..."
     }}
   }},
   {{
     "text": "장면3(조력자 등장).",
     "image_guide": "장면3 그림 설명.",
     "must_keep": {{
       "hair": "...",
       "outfit": "...",
       "palette": "...",
       "lighting": "...",
       "location": "..."
     }}
   }},
   {{
     "text": "장면4(상징 제안).",
     "image_guide": "장면4 그림 설명.",
     "must_keep": {{
       "hair": "...",
       "outfit": "...",
       "palette": "...",
       "lighting": "...",
       "location": "..."
     }}
   }},
   {{
     "text": "장면5(아이의 작은 시도).",
     "image_guide": "장면5 그림 설명.",
     "must_keep": {{
       "hair": "...",
       "outfit": "...",
       "palette": "...",
       "lighting": "...",
       "location": "..."
     }}
   }},
   {{
     "text": "장면6(여운).",
     "image_guide": "장면6 그림 설명.",
     "must_keep": {{
       "hair": "...",
       "outfit": "...",
       "palette": "...",
       "lighting": "...",
       "location": "..."
     }}
   }}
 ],
 "ending": "조용한 여운. 직접 해결 선언 금지."
}}
"""

# ─────────────────────
# OpenAI 호출 유틸
# ─────────────────────
def call_gpt_story(name, age, gender, goal, max_retries=2):
    """
    GPT에게 story+image_guide까지 한 번에 받아온다.
    금지 결말 패턴 검증. 필요하면 한 번 재시도.
    반환: dict (이미 JSON 파싱된 형태 기대. 파싱 실패하면 빈 값)
    """
    if not client:
        return None

    last_result_text = None
    for attempt in range(max_retries):
        start_t = time.time()

        prompt = PROMPT_TEMPLATE.format(
            name=name,
            age=age,
            gender=gender,
            goal=goal,
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # 속도/비용 밸런스. 필요시 상향 가능.
            temperature=0.7,
            max_tokens=1800,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw_text = resp.choices[0].message.content.strip()
        took = round(time.time() - start_t, 2)
        logger.info(f"GPT story gen {attempt+1} try {took}s")

        # 필터 검사
        if not violates_banned_resolution(raw_text):
            last_result_text = raw_text
            break
        else:
            logger.info("banned resolution detected. retrying...")

        last_result_text = raw_text

    # raw_text는 JSON 문자열 형태여야 한다.
    # 안전하게 JSON 파싱 시도.
    import json
    try:
        parsed = json.loads(last_result_text)
    except Exception as e:
        logger.warning(f"JSON parse fail: {e}")
        parsed = {}

    return parsed


def call_image_generation(image_guide, must_keep, global_visual):
    """
    한 장면 이미지를 생성.
    must_keep과 global_visual 정보를 합쳐서 DALL·E 계열 모델에 프롬프트.
    base64 data URL 반환.
    """
    if not client:
        return None

    # 전역 비주얼에서 안전하게 값 뽑기
    hair = (must_keep.get("hair") or global_visual.get("hair") or "")
    outfit = (must_keep.get("outfit") or global_visual.get("outfit") or "")
    palette = (must_keep.get("palette") or global_visual.get("palette") or "")
    lighting = (must_keep.get("lighting") or global_visual.get("lighting") or "")
    location = (must_keep.get("location") or global_visual.get("location_base") or global_visual.get("location") or "")

    # 이미지 프롬프트
    full_prompt = (
        f"pastel watercolor storybook illustration. "
        f"soft gentle tone. palette: {palette}. lighting: {lighting}. "
        f"same child every scene. hair: {hair}. outfit: {outfit}. "
        f"main location: {location}. "
        f"scene detail: {image_guide}. "
        f"keep proportions childlike and kind. no scary content. "
        f"do not add new characters that are not described."
    )

    start_t = time.time()
    img_resp = client.images.generate(
        model="dall-e-3",
        prompt=full_prompt,
        size="1024x1024",
        n=1
    )
    took = round(time.time() - start_t, 2)
    logger.info(f"image gen took {took}s")

    # DALL·E 3 응답은 base64 data URL 또는 url 중 하나.
    # openai.Images.generate (dall-e-3) 보통 data[0].b64_json 제공.
    b64_data = img_resp.data[0].b64_json
    data_url = f"data:image/png;base64,{b64_data}"
    return data_url


# ─────────────────────
# 라우트: /generate-story
# - 텍스트+장면별 image_guide까지만 만든다
# - 이미지 자체는 생성 안 함
# - mock: true 면 과금 없이 가짜 JSON을 돌려준다
# ─────────────────────
@app.route("/generate-story", methods=["POST"])
def generate_story():
    payload = request.get_json() or {}

    name = str(payload.get("name", "")).strip() or "아이"
    age = str(payload.get("age", "")).strip() or "6"
    gender = str(payload.get("gender", "")).strip() or "아이"
    goal = str(payload.get("topic", "")).strip() or "감정 다루기"
    mock_mode = bool(payload.get("mock", False))

    logger.info(f"generate-story: {name}, {age}, {gender}, {goal}, mock={mock_mode}")

    # mock 모드: OpenAI 호출 없이 구조만 검증
    if mock_mode or not client:
        fake = {
            "title": f"{name}의 작은 연습 이야기",
            "protagonist": f"{name} ({age}살 {gender}아이)",
            "global_visual": {
                "hair": "갈색 곱슬 단발",
                "outfit": "노란 셔츠와 파란 멜빵",
                "palette": "soft orange and teal",
                "lighting": "부드러운 저녁 불빛",
                "location_base": "식탁 있는 주방"
            },
            "scenes": [
                {
                    "text": f"{name}는 오늘 {goal} 때문에 입을 꾹 다물었어요. 볼이 빨갰어요.",
                    "image_guide": f"{name}가 식탁에 앉아 팔짱. 부드러운 주황빛 조명. 작은 요정이 접시 옆에서 서서 두 손을 허리에 올림.",
                    "must_keep": {
                        "hair": "갈색 곱슬 단발",
                        "outfit": "노란 셔츠와 파란 멜빵",
                        "palette": "soft orange and teal",
                        "lighting": "부드러운 저녁 불빛",
                        "location": "식탁 있는 주방"
                    }
                }
            ] + [
                {
                    "text": f"{name}는 조용히 생각했어요. 마음 안에 작은 불빛이 켜졌어요.",
                    "image_guide": f"{name}가 턱을 괴고 생각. 같은 방. 같은 조명. 작은 빛 방울이 옆에 둥실.",
                    "must_keep": {
                        "hair": "갈색 곱슬 단발",
                        "outfit": "노란 셔츠와 파란 멜빵",
                        "palette": "soft orange and teal",
                        "lighting": "부드러운 저녁 불빛",
                        "location": "식탁 있는 주방"
                    }
                }
                for _ in range(5)
            ],
            "ending": f"{name}는 자기 안에 남은 조용한 힘을 살짝 느꼈어요."
        }
        return jsonify(fake)

    # 실제 모드: GPT 호출
    story_dict = call_gpt_story(name, age, gender, goal)
    return jsonify(story_dict)


# ─────────────────────
# 라우트: /generate-image
# - 특정 장면 하나만 이미지로 변환
# - 프런트에서 scene의 image_guide / must_keep / global_visual 넘겨줘야 한다
# - mock: true 면 placeholder URL 반환
# ─────────────────────
@app.route("/generate-image", methods=["POST"])
def generate_image():
    payload = request.get_json() or {}

    mock_mode = bool(payload.get("mock", False))
    image_guide = payload.get("image_guide", "")
    must_keep = payload.get("must_keep", {}) or {}
    global_visual = payload.get("global_visual", {}) or {}

    logger.info(f"generate-image request. mock={mock_mode}")

    if mock_mode or not client:
        # placeholder (무료 테스트용)
        return jsonify({
            "image_data_url": "https://placehold.co/600x600?text=Scene+Preview"
        })

    img_data_url = call_image_generation(
        image_guide=image_guide,
        must_keep=must_keep,
        global_visual=global_visual
    )

    return jsonify({
        "image_data_url": img_data_url
    })


# ─────────────────────
# 헬스체크
# ─────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ─────────────────────
# 로컬 실행용
# Render에서는 gunicorn mytales_ai:app 사용
# ─────────────────────
if __name__ == "__main__":
    # 개발용 로컬 서버
    app.run(host="0.0.0.0", port=10000, debug=True)
