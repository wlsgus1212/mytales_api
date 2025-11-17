# mytales_ai.py
# MyTales API (2025-11-18, patched)
# - /score-assessment : 40문항 채점 → 8영역 평균 → 64코드(6축) + 근거(rationale)
# - /generate-story   : 기존 프롬프트 유지 + 검사 결과/근거를 프롬프트 말미에 주입
# - /generate-image   : 단일 컷 일러스트 (변경 없음)
# - /health           : 헬스체크
#
# 변경 요지:
#  1) "검사 해석 로직"을 서버로 이동: 점수→초점도메인 2개→가이드→rationale 텍스트 생성
#  2) call_gpt_story()가 rationale/cdps_code를 받아 기존 PROMPT 뒤에 [검사 근거] 블록을 추가
#  3) /generate-story 가 payload.cdps(domain_avg, code 등)을 받아 프롬프트에 반영하고
#     응답에 story.meta.rationale / meta.focus_domains를 포함

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
# 금지 결말 패턴
# (완벽히 해결/교정 선언형 엔딩 차단)
# ─────────────────────────────────
BANNED_PATTERNS = [
    r"다시는\s*안\s*그랬[어요|다]",
    r"이제\s*혼자서\s*잘\s*해[요|졌어요]",
    r"완벽하게\s*(해냈어요|할\s*수\s*있었어요)",
    r"착한\s*아이가\s*되었어요",
    r"나쁜\s*행동이\s*사라졌어요",
    r"(바르게|올바르게)\s*행동했어요",
    r"이제\s*항상\s*잘해요",
]
def violates_banned_resolution(story_text: str) -> bool:
    if not story_text:
        return False
    return any(re.search(p, story_text) for p in BANNED_PATTERNS)


# ─────────────────────────────────
# 입력값 정규화
# ─────────────────────────────────
def normalize_gender(g):
    """
    성별 표현을 '남자아이' / '여자아이' / '아이' 로 통일
    """
    raw = (str(g or "").strip()).lower()
    if raw in ["남", "남자", "boy", "male", "m", "남자아이", "남자 아이"]:
        return "남자아이"
    if raw in ["여", "여자", "girl", "female", "f", "여자아이", "여자 아이"]:
        return "여자아이"
    return "아이"

def pick_goal(payload):
    """
    훈육 주제로 들어올 수 있는 여러 키 중 하나만 선택
    """
    for key in ["topic", "education_goal", "goal", "educationGoalInput"]:
        v = payload.get(key)
        if v:
            return str(v).strip()
    return "생활 습관"


# ─────────────────────────────────
# 검사(40문항) 채점/해석 유틸
# ─────────────────────────────────
REVERSE_ITEMS = {8, 9, 13, 14, 22}  # 1~40 역문항

DOMAINS = {
    "SOC": [1,2,3,4,5],        # 사회성·공감
    "EMO": [6,7,8,9,10],       # 감정 표현·조절
    "CON": [11,12,13,14,15],   # 자기조절·집중력
    "AUT": [16,17,18,19,20],   # 자율성·책임감
    "RES": [21,22,23,24,25],   # 적응력·회복탄력성
    "CRE": [26,27,28,29,30],   # 상상력·창의성
    "COG": [31,32,33,34,35],   # 사고·학습태도
    "HAB": [36,37,38,39,40],   # 생활 습관·자기관리
}
CODE_AXES = ["SOC","EMO","CON","AUT","RES","HAB"]  # 6축 → 64코드
BIN_THRESHOLD = 2.5

DOMAIN_LABELS = {
  "SOC":"사회성·공감","EMO":"감정표현·조절","CON":"자기조절·집중력",
  "AUT":"자율성·책임감","RES":"회복탄력성","CRE":"상상력·창의성",
  "COG":"사고·학습태도","HAB":"생활습관·자기관리"
}
DOMAIN_GUIDE = {
  "SOC": "친구 상호작용·나눔·차례·경청을 자연스럽게 체험하게 합니다.",
  "EMO": "감정을 말로 설명하지 않고 표정·몸 느낌으로 드러나며, 잦아드는 작은 신호를 보여줍니다.",
  "CON": "유혹 지연과 ‘작은 완주 경험’을 재미로 느끼게 합니다.",
  "AUT": "스스로 선택→작게 책임지는 흐름, 칭찬 대신 조용한 지지를 남깁니다.",
  "RES": "낯선 상황에서 당황→안정 회복의 짧은 호흡을 반복 경험하게 합니다.",
  "CRE": "일상 사물 변신·상상 장면으로 시도 자체를 즐겁게 합니다.",
  "COG": "호기심 단서를 놓고, 다른 방법을 스스로 찾는 순간을 만듭니다.",
  "HAB": "식사·정리·수면·기기 등 규칙을 ‘편안함/깔끔함’의 몸 느낌으로 체감하게 합니다."
}

def _assert(cond, msg):
    if not cond:
        raise ValueError(msg)

def _coerce_answer(v):
    MAP = {"①":1,"거의 그렇지 않다":1,"전혀 아니다":1,"1":1,
           "②":2,"가끔 그렇다":2,"2":2,
           "③":3,"자주 그렇다":3,"3":3,
           "④":4,"매우 자주 그렇다":4,"4":4}
    if isinstance(v, int): return v
    if isinstance(v, str):
        s = v.strip()
        if s in MAP: return MAP[s]
        if s.isdigit(): return int(s)
    raise ValueError("invalid answer value")

def score_answers(raw_answers):
    _assert(isinstance(raw_answers, list), "answers must be array")
    _assert(len(raw_answers) == 40, "answers length must be 40")
    coerced = [_coerce_answer(v) for v in raw_answers]
    for n in coerced: _assert(1 <= n <= 4, "answer out of range")
    scored = [(5 - v) if (i+1) in REVERSE_ITEMS else v for i, v in enumerate(coerced)]
    return coerced, scored

def domain_averages(scored):
    out = {}
    for k, idxs in DOMAINS.items():
        vals = [scored[i-1] for i in idxs]
        out[k] = round(sum(vals)/len(vals), 2)
    return out

def make_code(averages):
    bits = [1 if averages[ax] > BIN_THRESHOLD else 0 for ax in CODE_AXES]
    letters = list("ABCDEF")
    code = "-".join(f"{letters[i]}{bits[i]}" for i in range(len(CODE_AXES)))
    return code, bits

def select_focus_domains(domain_avg, k=2):
    return sorted(domain_avg.items(), key=lambda x: x[1])[:k]

def build_rationale_text(topic, focus):
    """
    topic: 훈육 주제 문자열
    focus: [("HAB", 2.3), ("CON", 2.4)] 형태
    """
    lines = []
    if topic:
        lines.append(f"선택 주제: {topic}")
    lines.append("검사 결과 기반 동화 설계 근거:")
    for key, score in focus:
        label = DOMAIN_LABELS.get(key, key)
        guide = DOMAIN_GUIDE.get(key, "")
        lines.append(f"- {label}({score}): {guide}")
    lines.append("구성 원리: 1장 현재 몸 느낌 → 작은 시도 → 즉각적이고 안전한 긍정 경험 → 조용한 여운.")
    lines.append("규칙: 명령/도덕 라벨 금지, 장면당 80~140자, 총 6장 구조.")
    return "\n".join(lines)


# ─────────────────────────────────
# 동화 프롬프트 (기존 HEADER/FOOTER 유지)
# + 검사 근거 블록을 뒤에 추가 주입
# ─────────────────────────────────

PROMPT_HEADER = """
너는 5~9세 아이에게 읽어주는 한국어 그림책 작가다.
너의 임무는 혼내거나 설교하는 게 아니라,
아이 스스로 '어? 이거 해보니까 신기한데?' 하고 느끼게 만드는 이야기다.

입력 정보:
- 아이 이름: {name}
- 나이: {age}살
- 성별: {gender}아이
- 훈육 주제: {goal}

────────────────
전체 톤
────────────────
1. '해야 해', '하지 마' 같은 명령 금지.
2. '나쁜 행동', '착한 아이', '올바른 선택' 같은 도덕 라벨 금지.
3. 상담실 말투 금지:
   '감정 조절', '훈육', '행동을 통제', '문제 행동', '잘 관리했어요',
   '습관 형성', '인내심', '책임감', '공감', '자신감'
4. 게임/스킬 말투 금지:
   '레벨업', '미션', '점수', '게이지', '기술', '스킬', '업그레이드'
5. 어려운 추상어 금지:
   '내면', '감정 상태', '해결책', '관계', '조절', '통제', '스트레스'
6. 무섭게 겁주거나 벌 주는 식 금지.
   위협이나 공포 대신 귀엽고 우스운 표현을 써라.

대신 이렇게 말해라.
- 몸 느낌과 표정으로만 표현.
  예: '입이 꽉 다물렸어요. 볼이 빨개졌어요. 발끝이 바닥을 톡톡 쳤어요.'
- 속마음은 짧고 솔직하게.
  예: '싫어. 그냥 싫어.'
- 과학적 사실은 상상 장면으로 눈앞에서 바로 보이게 만든다.
  예: '당근을 한 입 먹자 창밖 별이 또렷해졌어요.'
  예: '장난감을 하나 주우니까 먼지 세균 악당이 콜록 하며 도망갔어요.'
- 이 변화가 재밌어서 아이가 스스로 한 번 더 시도하고 싶게 만들어라.

엔딩:
- 아이가 '그 작은 변화'를 자기 물건처럼 마음속에 챙긴다.
- 부모는 옆에 조용히 있어도 된다. (미소, 머리 쓰다듬기 정도)
- 하지만 '착하네', '이제 다 됐어', '완벽해졌어', '다시는 안 그랬어요' 같은 말은 절대 금지.

중요:
- 이번 이야기의 주제는 "{goal}"이다.
- 1장부터 6장까지 전부 "{goal}"과 직접 연결된 상황만 다룬다.
- "{goal}"과 관계없는 다른 생활 문제(예: 방 청소, 양치, 잠자리, 숙제 등)는 넣지 않는다.
- 장면마다 "{goal}"과 연결된 감정, 몸 느낌, 결과만 보여준다.

────────────────
이야기 구조 (반드시 이 순서로 6장면)
────────────────

1장. 현실 문제
- 지금 {name}이 {goal}과 직접 연결된 행동을 하고 있다.
  (예: 편식 → '당근 싫어.'라고 말하며 고개를 홱 돌린다.)
- 싫어함 / 귀찮음 / 거부감을 몸짓으로 묘사.
- '혼나려고 했다' 같은 표현 금지.
- 아이 속말은 가능. '싫어. 그냥 싫어.'

2장. 불편/작은 위험 등장
- 그 행동 때문에 생기는 귀찮은 결과를 귀엽게 의인화.
- 예: 편식 → 눈이 흐릿해지고 창밖 불빛이 뿌옇게 보여요.
- 이건 무섭지 않고 장난스럽다.
- '벌'처럼 들리면 안 된다.

3장. 조력자 등장
- {gender}아이인 {name} 옆에 작은 친구가 나타난다.
  - 남자아이면 로봇/작은 공룡/번쩍 새 같은 존재.
  - 여자아이면 꽃 요정/다정한 새/부드러운 별/인형 같은 존재.
  - 성별 애매하면 부드러운 빛 덩어리.
- 조력자는 명령하지 않는다.
- '나 이거 해봤는데 진짜 신기했어.' / '나는 이런 걸 봤어.' 처럼 자기 경험만 말한다.
- 여기서 {goal}과 직접 연결된 '작은 시도' 아이디어를 자연스럽게 보여준다.
  예: '당근을 한 입만 꼭꼭 씹으면 창밖 불빛이 다시 또렷해져.'

4장. 작은 시도
- {name}이 아주 살짝 따라 한다.
- 즉시 귀엽고 신기한 변화가 눈앞에 나타난다.
  예: 창밖 불빛이 다시 맑아진다.
- '성공했다', '해결됐다', '바른 선택' 같은 표현 금지.
- 대신 '우와… 이거 뭐야?' 같은 놀람을 넣어라.

5장. 현실 감각
- 그 상상 변화가 {name}의 실제 몸 느낌으로도 살짝 이어진다.
  예: '눈이 맑아진 느낌이 들었어요.' / '입 안이 따뜻했어요.'
- 아이는 살짝 뿌듯하거나 재미있다.
- '훈육 성공', '이제 바르게 행동해요' 같은 말 금지.

6장. 여운
- 아직 모든 게 끝난 건 아니다.
- 그래도 {name}은 그 작고 신기한 변화를 자기 것처럼 마음속에 챙긴다.
- 부모는 조용히 곁에 있어도 된다. (미소나 가볍게 머리 쓰다듬기)
- 평가는 금지. 도덕 라벨 금지.
- 마무리는 조용하고 따뜻하게.

────────────────
문장 스타일
────────────────
- 각 장면은 3~5개의 짧은 문장으로 된 한 단락.
- 단락 하나는 80~140자 정도. 아이에게 읽어주기 편한 호흡.
- 어려운 단어 대신 눈앞 장면, 몸 느낌, 표정, 소리로만 설명.
- 무섭거나 어둡게 하지 말고, 건강하고 따뜻하게.

────────────────
그림(일러스트) 규칙
────────────────
- 각 장면마다 "image_guide"를 반드시 넣는다.
- "image_guide"에는 수채화 느낌의 한 장면 구성을 써라.
  - 머리 모양, 옷 색, 조명, 방/장소, 손 동작, 표정.
  - 조력자가 어디에 있는지.
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
- location_base: 주 배경 공간 ("식탁 있는 주방", "장난감 많은 방 바닥" 등)

────────────────
이제부터 아래 형식으로만, 불필요한 설명 없이 JSON만 출력해.
"""

PROMPT_FOOTER = r"""
{
 "title": "동화 제목",
 "protagonist": "<아이 이름> (<나이>살 <성별>아이)",
 "global_visual": {
   "hair": "예: 짧은 갈색 머리",
   "outfit": "예: 노란 셔츠와 파란 멜빵",
   "palette": "예: warm pastel orange and teal",
   "lighting": "예: 저녁 식탁의 부드러운 불빛",
   "location_base": "예: 식탁 있는 주방"
 },
 "scenes": [
   {
     "text": "1장 내용. 현실 문제 장면.",
     "image_guide": "1장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "2장 내용. 불편/작은 위험. 무섭지 않고 귀엽다.",
     "image_guide": "2장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "3장 내용. 조력자 등장. 명령 말투 금지.",
     "image_guide": "3장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "4장 내용. 아이의 아주 작은 시도. 바로 나타나는 신기한 변화.",
     "image_guide": "4장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "5장 내용. 몸으로 느끼는 작은 변화.",
     "image_guide": "5장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   },
   {
     "text": "6장 내용. 여운. 조용한 만족. 도덕 라벨 금지.",
     "image_guide": "6장 그림 설명.",
     "must_keep": { "hair": "...", "outfit": "...", "palette": "...", "lighting": "...", "location": "..." }
   }
 ],
 "ending": "아이의 조용한 깨달음. 부모는 옆에서 조용히 있다. '착하네' 같은 말 없이 따뜻하게 마무리."
}
"""

# 검사 근거(코드/포커스/라셔날)를 프롬프트 말미에 추가하기 위한 보조 텍스트
def build_assessment_block(cdps_code: str, focus_keys, rationale_text: str) -> str:
    fk = ", ".join(focus_keys or [])
    rt = rationale_text or "검사 근거 없음(테스트)."
    code_str = cdps_code or "없음"
    return f"""
[검사 근거]
- 성향 코드: {code_str}
- focus_domains: {fk}
- rationale:
{rt}
""".strip()


# ─────────────────────────────────
# GPT 호출
# ─────────────────────────────────
def call_gpt_story(name, age, gender_norm, goal, cdps_code=None, rationale_text=None, focus_keys=None, max_retries=2):
    """
    GPT에게 story(json) 생성 요청.
    기존 프롬프트(PROMPT_HEADER/FOOTER) 뒤에 검사 근거 블록을 추가 주입.
    금지된 엔딩 패턴 있으면 한 번 더 재요청.
    JSON 파싱 실패하면 fallback.
    """
    last_result_text = None
    assessment_block = build_assessment_block(cdps_code, focus_keys, rationale_text)

    for attempt in range(max_retries):
        start_t = time.time()

        prompt = (
            PROMPT_HEADER.format(name=name, age=age, gender=gender_norm, goal=goal)
            + "\n"
            + assessment_block
            + "\n"
            + PROMPT_FOOTER
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
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
# 이미지 생성 (변경 없음)
# ─────────────────────────────────
def call_image_generation(image_guide, must_keep, global_visual, scene_text):
    """
    한 장면 이미지를 생성해서 data URL 또는 직접 URL로 반환.
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
        "single watercolor illustration for a children's picture book. "
        "soft warm pastel tone. gentle safe mood. "
        "only ONE panel. do not split the page. no collage. no grid. no multiple frames. "
        "the child appears only once. no duplicates of the same child. "
        "show ONLY the current moment, not before or after.\n"
        f"scene_text (narration to visualize): {scene_text}\n"
        f"main child: hair = {hair}, outfit = {outfit}.\n"
        f"environment/background: {location}.\n"
        f"lighting: {lighting}. palette: {palette}.\n"
        f"extra visual detail for this moment: {image_guide}\n"
        "natural healthy child body proportions. "
        "no fear. no violence. no scary elements."
    )

    start_t = time.time()
    img_resp = client.images.generate(
        model="dall-e-3",
        prompt=full_prompt,
        size="1024x1024",
        quality="standard",
        n=1,
        response_format="b64_json",  # base64 직접 받기
    )
    took = round(time.time() - start_t, 2)
    logger.info(f"[call_image_generation] took={took}s")

    b64_data = getattr(img_resp.data[0], "b64_json", None)
    if b64_data:
        return f"data:image/png;base64,{b64_data}"

    img_url = getattr(img_resp.data[0], "url", None)
    if img_url:
        return img_url

    return None


# ─────────────────────────────────
# 라우트: /score-assessment  (신규)
# ─────────────────────────────────
@app.route("/score-assessment", methods=["POST"])
def score_api():
    """
    Request:
      {
        "name":"민준", "age":6, "gender":"남",
        "topic":"편식",
        "answers":[1..4] * 40  // 라벨/문자도 허용
      }
    Response:
      {
        "ok": true,
        "input": {...},
        "cdps": {
          "answers_raw":[...40],
          "answers_scored":[...40],
          "domain_avg":{"SOC":3.2,...},
          "code":"A1-B0-C1-D0-E1-F0",
          "bits":[...],
          "axes":["SOC","EMO","CON","AUT","RES","HAB"],
          "threshold":2.5,
          "focus":[{"key":"HAB","score":2.31},{"key":"CON","score":2.44}],
          "rationale":"선택 주제: ...\n검사 결과 기반 ..."
        }
      }
    """
    try:
        payload = request.get_json(force=True) or {}
        name   = str(payload.get("name","")).strip() or "아이"
        age    = int(str(payload.get("age","6")).strip())
        gender = str(payload.get("gender","아이")).strip()
        topic  = str(payload.get("topic","")).strip() or "생활 습관"
        answers = payload.get("answers", [])

        raw, scored = score_answers(answers)
        avgs = domain_averages(scored)
        code, bits = make_code(avgs)
        focus = select_focus_domains(avgs, k=2)
        rationale = build_rationale_text(topic, focus)

        return jsonify({
            "ok": True,
            "input": {"name":name,"age":age,"gender":gender,"topic":topic},
            "cdps": {
                "answers_raw": raw,
                "answers_scored": scored,
                "domain_avg": avgs,
                "code": code,
                "bits": bits,
                "axes": CODE_AXES,
                "threshold": BIN_THRESHOLD,
                "focus": [{"key":k,"score":s} for k,s in focus],
                "rationale": rationale
            }
        })
    except Exception as e:
        logger.exception("score-assessment error")
        return jsonify({"ok":False,"error":str(e)}), 400


# ─────────────────────────────────
# 라우트: /generate-story  (검사 근거 주입)
# ─────────────────────────────────
@app.route("/generate-story", methods=["POST"])
def generate_story():
    payload = request.get_json() or {}

    name = str(payload.get("name", "")).strip() or "아이"
    age = str(payload.get("age", "")).strip() or "6"
    gender_raw = payload.get("gender", "")
    gender_norm = normalize_gender(gender_raw)
    goal = pick_goal(payload)

    # 선택: 클라이언트가 /score-assessment 결과를 그대로 넘겨줄 수 있음
    cdps = payload.get("cdps") or {}
    domain_avg = cdps.get("domain_avg")
    cdps_code  = cdps.get("code")
    focus_arr  = cdps.get("focus") or []  # [{"key":"HAB","score":2.3}, ...]
    focus_keys = [f.get("key") for f in focus_arr if isinstance(f, dict) and f.get("key")]
    rationale  = cdps.get("rationale")

    # 만약 rationale 미제공이면 서버에서 즉석 계산(강건성)
    if not rationale and isinstance(domain_avg, dict):
        focus = select_focus_domains(domain_avg, k=2)
        rationale = build_rationale_text(goal, focus)
        focus_keys = [k for k,_ in focus]

    logger.info(
        f"[generate-story] name={name} age={age} gender_raw={gender_raw} "
        f"gender_norm={gender_norm} goal={goal} code={cdps_code} focus={focus_keys}"
    )

    story_dict = call_gpt_story(
        name, age, gender_norm, goal,
        cdps_code=cdps_code,
        rationale_text=rationale,
        focus_keys=focus_keys
    )

    # 프론트 표시용 메타
    story_dict.setdefault("meta", {})
    story_dict["meta"]["rationale"] = rationale or ""
    story_dict["meta"]["focus_domains"] = focus_keys or []

    return jsonify(story_dict)


# ─────────────────────────────────
# 라우트: /generate-image
# ─────────────────────────────────
@app.route("/generate-image", methods=["POST"])
def generate_image():
    payload = request.get_json() or {}

    image_guide = payload.get("image_guide", "")
    must_keep = payload.get("must_keep", {}) or {}
    global_visual = payload.get("global_visual", {}) or {}
    scene_text = payload.get("scene_text", "")  # Wix에서 넘겨줘야 함

    logger.info(
        "[generate-image] have_image_guide=%s mk_keys=%s gv_keys=%s",
        bool(image_guide),
        list(must_keep.keys()),
        list(global_visual.keys()),
    )

    if not image_guide:
        return jsonify({"error": "missing image_guide"}), 400

    img_data_url = call_image_generation(
        image_guide=image_guide,
        must_keep=must_keep,
        global_visual=global_visual,
        scene_text=scene_text,
    )

    if not img_data_url:
        return jsonify({"image_data_url": None}), 500

    return jsonify({"image_data_url": img_data_url})


# ─────────────────────────────────
# 헬스체크
# ─────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    logger.info("[health] ping")
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────
# 로컬 실행
# Render에서는 gunicorn mytales_ai:app 로 실행
# ─────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
