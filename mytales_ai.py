# mytales_ai.py
# mock 모드 제거 최종본

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os
import time
import logging
import json
import re

# ─────────────────────────────────
# 환경 설정 / 로깅
# ─────────────────────────────────
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Server requires a valid key.")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)

# Wix → Render 호출 시 CORS / OPTIONS 프리플라이트 허용
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Content-Type"],
    methods=["GET", "POST", "OPTIONS"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s"
)
logger = logging.getLogger("mytales")


# ─────────────────────────────────
# 금지 결말(즉시 완벽 교정) 필터
# (너무 교육용/훈육성 결말 나오면 한 번 더 재시도)
# ─────────────────────────────────
BANNED_PATTERNS = [
    "다시는 안 그랬어요",
    "이제 혼자서 잘 해요",
    "완벽하게 해냈어요",
    "완벽하게 할 수 있었어요",
    "착한 아이가 되었어요",
    "나쁜 행동을 하지 않았어요",
    "엄마가 아주 크게 칭찬했어요",
    "아빠가 자랑스러워했어요",
    "선생님이 칭찬했어요",
    "문제 행동이 사라졌어요",
    "바르게 행동했어요",
    "올바르게 행동했어요",
    "이제 항상 잘해요",
]

def violates_banned_resolution(story_text: str) -> bool:
    if not story_text:
        return False
    for pat in BANNED_PATTERNS:
        if pat in story_text:
            return True
    return False


# ─────────────────────────────────
# 입력값 정규화 유틸
# ─────────────────────────────────
def normalize_gender(g):
    """
    자유 입력된 성별을 '남자아이' / '여자아이' / '아이' 로 정리
    """
    raw = (str(g or "").strip()).lower()
    if raw in ["남", "남자", "boy", "male", "m", "남자아이", "남자 아이"]:
        return "남자아이"
    if raw in ["여", "여자", "girl", "female", "f", "여자아이", "여자 아이"]:
        return "여자아이"
    return "아이"


def pick_goal(payload):
    """
    프런트가 어떤 키로 보내든 훈육 주제 뽑기
    """
    for key in ["topic", "education_goal", "goal", "educationGoalInput"]:
        v = payload.get(key)
        if v:
            return str(v).strip()
    return "생활 습관"


# ─────────────────────────────────
# 동화 프롬프트
#
# 요구사항 반영:
# - 아이가 이해 가능한 어휘만 사용
# - "해야 해 / 하지 마" 금지
# - 훈육/조절/스킬/게이지/평가 금지
# - 행동 → 귀여운 원인(요정, 먼지악당 등) → 즉시 체감되는 변화 → 아이가 '오 신기하네' 하고 자기 동기로 움직이게
# - 마지막은 '아이의 조용한 깨달음 + 부모의 따뜻한 존재감은 가능' (하지만 "착한 아이네" 같은 도덕 라벨 금지)
# - 6장면 고정, 장면별 image_guide + must_keep 포함
# ─────────────────────────────────
PROMPT_TEMPLATE = """
너는 5~9세 아이에게 읽어주는 한국어 그림책 작가다.
너의 임무는 혼내거나 설명하는 게 아니라,
아이 스스로 "오, 이거 하면 신기하네" 하고 느끼게 만드는 이야기다.

입력 정보:
- 아이 이름: {name}
- 나이: {age}살
- 성별: {gender}아이
- 훈육 주제: {goal}

────────────────
전체 톤
────────────────
1. "해야 해", "하지 마" 같은 명령 금지.
2. "나쁜 행동", "착한 아이", "올바른 선택" 같은 도덕 라벨 금지.
3. 상담실 말투 금지:
   "감정 조절", "훈육", "행동을 통제", "문제 행동", "잘 관리했어요",
   "습관 형성", "인내심", "책임감", "공감", "자신감"
4. 게임/스킬 말투 금지:
   "레벨업", "미션", "점수", "게이지", "기술", "스킬", "업그레이드"
5. 어려운 추상어 금지:
   "내면", "감정 상태", "해결책", "관계", "조절", "통제", "스트레스"
6. 무섭게 벌 주거나 겁 주는 전개 금지.
   귀여운 장난처럼 느껴져야 한다. (먼지 악당은 콜록거리며 우스워야 한다)

대신 이렇게 말해.
- 몸 느낌과 감각으로 표현해.
  예: "입이 꽉 다물렸어요. 볼이 빨개졌어요. 발끝이 바닥을 톡톡 쳤어요."
- 아이의 속마음은 아주 짧고 솔직하게.
  예: "싫어. 그냥 싫어."
- 과학적 사실은 상상 장면으로 바꿔서 바로 눈앞에서 일어난 결과처럼 보여줘.
  예: "당근을 한 입 먹자 창밖 별이 또렷해졌어요."
  예: "장난감을 주웠더니 먼지 세균 악당이 콜록 하며 도망쳤어요."
- 이 신기한 변화 때문에 아이가 스스로 조금 더 시도하고 싶어지는 느낌으로 가.

엔딩:
- 아이가 '그 작은 변화'를 자기 거처럼 소중히 여긴다.
- 부모는 옆에 조용히 있어도 된다. (살짝 웃는다, 머리를 쓰다듬는다)
- 하지만 "착하네", "이제 다 됐어", "완벽해졌어", "다시는 안 그랬어요" 이런 말 금지.

────────────────
이야기 구조 (반드시 이 순서로 6장면)
────────────────

1장. 현실 문제
- 지금 {name}이 {goal}과 관련해 실제로 하고 있는 행동 장면.
- 예: 편식 → "당근 안 먹어." 방청소 → "장난감 바닥에 가득."
- 싫어함 / 귀찮음 / 거부감을 몸짓으로 묘사.
- "혼나려고 했다" 같은 말 넣지 말 것.
- 아이 입장에서 "그냥 싫어." 같은 속말은 가능.

2장. 불편/작은 위험 등장
- 그 행동 때문에 생기는 귀찮은 결과를 귀엽게 의인화.
- 예: 방이 지저분 → 먼지 세균 악당이 콜록 가루 뿌림 (근데 우스꽝스럽고 약간 바보같이)
- 예: 채소 거부 → 창밖 불빛이 흐릿해지고, 아이 눈 안의 별이 흐려짐.
- 무섭게 하지 말 것. 장난스럽게 표현.

3장. 조력자 등장
- {gender}아이인 {name} 옆에 작은 동료/친구가 나타남.
  - 남자아이면 로봇/작은 공룡/번쩍 새 같은 존재.
  - 여자아이면 꽃 요정/다정한 새/부드러운 별/인형 같은 존재.
  - 성별이 애매하면 부드러운 빛 덩어리.
- 조력자는 명령하지 않는다.
- "나 이거 해봤는데 신기했어." / "나는 이런 걸 봤어." 처럼 자기 경험만 들려준다.
- 여기서 과학적 사실을 상상으로 연결해.
  (당근 → 눈이 또렷 / 청소 → 공기가 맑아짐 / 양치 → 이빨 반짝 돌 지킴 등)

4장. 작은 시도
- {name}이 살짝 따라 한다. (당근 한 입 베어문다 / 장난감 하나 상자에 넣는다 / 칫솔 한 번 슥 문댄다)
- 그 즉시 상상 속 변화가 눈앞에서 일어난다.
- 이 변화는 '상'이다. 벌이 아니다.
- 예: 먼지 악당이 "에취!" 하며 달아난다.
- 예: 아이 눈 속 별이 다시 반짝 켜진다.
- "성공했다" / "해결됐다" / "바른 선택" 같은 말 금지.
- 대신 "우와… 이거 뭐야?" 같은 놀람을 넣어라.

5장. 현실 감각
- 상상 속 변화가 실제 몸 느낌으로도 조금 이어진다.
- 예: "코가 시원해졌어요." / "방 공기가 가볍게 느껴졌어요."
- 아이는 살짝 뿌듯하거나 재미있다.
- "훈육 성공" "이제 바르게 행동해요" 같은 표현 금지.
- 그냥 "조금 좋다" 느낌.

6장. 여운
- 아직 끝은 아니다. 그래도 {name}은 그 작고 신기한 변화를 자기 것처럼 마음에 넣는다.
- 부모는 조용히 곁에 있어도 된다. (미소, 머리 쓰다듬기)
- 평가는 금지. 도덕 라벨 금지.
- 마무리는 조용하고 따뜻하게.

────────────────
문장 스타일
────────────────
- 각 장면은 3~5개의 짧은 문장으로 이뤄진 한 단락.
- 단락 하나는 80~140자 정도. (아이에게 읽기 편하게 이어지는 리듬)
- 어려운 단어 대신 눈앞 장면, 몸 느낌, 표정, 소리로만 설명.
- 아이 이름만 계속 쓰지 말고 "그는", "그녀는", "아이", 이런 식으로 자연스럽게 돌려 써라.
- 무섭거나 어둡게 하지 말고, 건강하고 따뜻한 몸.

────────────────
그림(일러스트) 규칙
────────────────
- 각 장면마다 "image_guide"를 반드시 넣어.
- "image_guide"에는 수채화 느낌의 한 장면 구성을 써.
  - 아이 머리 모양, 옷, 조명, 방/장소, 손 동작, 표정.
  - 조력자가 어디 있는지.
- 모든 장면에서 같은 아이, 같은 옷, 같은 색감, 같은 조명을 유지해야 한다.
- 잔혹/공포 절대 금지. 부드러운 파스텔.

────────────────
전역 비주얼 (global_visual)
────────────────
모든 장면이 공유해야 하는 시각 정보:
- hair: 아이 머리 스타일과 색
- outfit: 아이 옷
- palette: 전체 색감 (예: "warm pastel orange and teal")
- lighting: 빛 분위기 ("저녁 식탁의 부드러운 노란 불빛")
- location_base: 주 배경 공간 ("식탁 있는 주방", "장난감으로 가득한 아이 방 바닥")

────────────────
출력 형식 (JSON만 출력. 설명 추가 금지. 키 이름 절대 바꾸지 마.)
────────────────

{
 "title": "동화 제목",
 "protagonist": "{name} ({age}살 {gender}아이)",
 "global_visual": {
   "hair": "예: 짧은 갈색 머리",
   "outfit": "예: 노란 셔츠와 파란 멜빵",
   "palette": "예: warm pastel orange and teal",
   "lighting": "예: 저녁 식탁의 부드러운 불빛",
   "location_base": "예: 식탁 있는 주방"
 },
 "scenes": [
   {
     "text": "1장. 현실 문제.",
     "image_guide": "1장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "2장. 불편/작은 위험 등장. 귀엽고 살짝 웃긴 식으로.",
     "image_guide": "2장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "3장. 조력자 등장. '명령' 대신 '나 이거 봤어' 톤.",
     "image_guide": "3장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "4장. 아이의 아주 작은 시도. 그리고 즉시 나타나는 귀엽고 신기한 변화.",
     "image_guide": "4장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "5장. 그 변화가 몸 느낌으로도 살짝 이어진다.",
     "image_guide": "5장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "6장. 여운. 아이가 그 느낌을 자기 것처럼 조용히 간직한다. 부모는 조용히 곁에 있다.",
     "image_guide": "6장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   }
 ],
 "ending": "아이의 조용한 깨달음과 부모의 따뜻한 존재감(미소나 쓰다듬기)은 괜찮지만, 평가나 점수식 칭찬은 절대 금지."
}
"""


# ─────────────────────────────────
# GPT 호출
# ─────────────────────────────────
def call_gpt_story(name, age, gender_norm, goal, max_retries=2):
    """
    GPT에게 story(json) 생성 요청.
    금지된 '완벽 교정' 패턴 있으면 한 번 더 재시도.
    JSON 파싱 실패하면 최소한의 fallback 구조 리턴.
    """
    last_result_text = None

    for attempt in range(max_retries):
        start_t = time.time()

        prompt = PROMPT_TEMPLATE.format(
            name=name,
            age=age,
            gender=gender_norm,
            goal=goal,
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw_text = (resp.choices[0].message.content or "").strip()
        took = round(time.time() - start_t, 2)
        logger.info(f"[call_gpt_story] try={attempt+1} took={took}s chars={len(raw_text)}")

        if not violates_banned_resolution(raw_text):
            last_result_text = raw_text
            break
        else:
            logger.info("[call_gpt_story] banned-style ending detected. retrying...")
            last_result_text = raw_text

    try:
        parsed = json.loads(last_result_text)
    except Exception as e:
        logger.warning(f"[call_gpt_story] JSON parse fail: {e}")
        parsed = {
            "title": f"{name}의 작은 이야기",
            "protagonist": f"{name} ({age}살 {gender_norm})",
            "global_visual": {
                "hair": "짧은 갈색 머리",
                "outfit": "노란 셔츠와 파란 멜빵",
                "palette": "warm pastel orange and teal",
                "lighting": "저녁 식탁의 부드러운 불빛",
                "location_base": "식탁 있는 주방"
            },
            "scenes": [],
            "ending": f"{name}은(는) 자기 안에 남은 조용한 느낌을 살짝 아꼈어요."
        }

    return parsed


# ─────────────────────────────────
# 이미지 생성 호출
# ─────────────────────────────────
def call_image_generation(image_guide, must_keep, global_visual):
    """
    장면 이미지를 pastel watercolor 스타일로 생성.
    반환: data:image/png;base64,.... 형태
    """

    hair = (must_keep.get("hair") or global_visual.get("hair") or "")
    outfit = (must_keep.get("outfit") or global_visual.get("outfit") or "")
    palette = (must_keep.get("palette") or global_visual.get("palette") or "")
    lighting = (must_keep.get("lighting") or global_visual.get("lighting") or "")
    location = (
        must_keep.get("location")
        or global_visual.get("location_base")
        or global_visual.get("location")
        or ""
    )

    full_prompt = (
        "soft pastel watercolor children storybook illustration. "
        "gentle, warm, kind tone. "
        f"child hair: {hair}. outfit: {outfit}. "
        f"color palette: {palette}. lighting: {lighting}. "
        f"main location: {location}. "
        f"scene detail: {image_guide}. "
        "same child across scenes. healthy body proportions. "
        "cozy, safe, not scary, no gore. "
        "do not introduce new characters that were not described."
    )

    start_t = time.time()
    img_resp = client.images.generate(
        model="dall-e-3",
        prompt=full_prompt,
        size="1024x1024",
        n=1
    )
    took = round(time.time() - start_t, 2)
    logger.info(f"[call_image_generation] took={took}s")

    b64_data = img_resp.data[0].b64_json
    data_url = f"data:image/png;base64,{b64_data}"
    return data_url


# ─────────────────────────────────
# 라우트: /generate-story
#  - Wix 입력 페이지에서 name/age/gender/topic 보내면
#    동화 JSON(6장면, image_guide 포함) 생성해서 그대로 반환
# ─────────────────────────────────
@app.route("/generate-story", methods=["POST"])
def generate_story():
    payload = request.get_json() or {}

    name = str(payload.get("name", "")).strip() or "아이"
    age = str(payload.get("age", "")).strip() or "6"
    gender_raw = payload.get("gender", "")
    gender_norm = normalize_gender(gender_raw)
    goal = pick_goal(payload)

    logger.info(
        f"[generate-story] name={name} age={age} gender_raw={gender_raw} "
        f"gender_norm={gender_norm} goal={goal}"
    )

    story_dict = call_gpt_story(name, age, gender_norm, goal)
    return jsonify(story_dict)


# ─────────────────────────────────
# 라우트: /generate-image
#  - Wix 결과 페이지에서 장면마다 그림 따로 요청
#  - 기대 입력: { image_guide, must_keep, global_visual }
#  - 반환: { "image_data_url": "data:image/png;base64,...." }
# ─────────────────────────────────
@app.route("/generate-image", methods=["POST"])
def generate_image():
    payload = request.get_json() or {}

    image_guide = payload.get("image_guide", "") or ""
    must_keep = payload.get("must_keep", {}) or {}
    global_visual = payload.get("global_visual", {}) or {}

    logger.info(
        f"[generate-image] have_image_guide={bool(image_guide)} "
        f"mk_keys={list(must_keep.keys())} "
        f"gv_keys={list(global_visual.keys())}"
    )

    img_data_url = call_image_generation(
        image_guide=image_guide,
        must_keep=must_keep,
        global_visual=global_visual
    )

    return jsonify({
        "image_data_url": img_data_url
    })


# ─────────────────────────────────
# 헬스체크
# ─────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    logger.info("[health] ping")
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────
# 로컬 실행
# Render에서는 gunicorn mytales_ai:app 로 구동
# ─────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
