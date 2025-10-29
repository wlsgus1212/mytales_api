# mytales_ai.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, logging, time, json

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Please set it in .env file")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mytales")

# ─────────────────────────────
# 주제별 시각 테마 매핑
# ─────────────────────────────
THEME_MAP = {
    "편식": {"palette": "soft green and orange", "lighting": "morning sunlight in a cozy kitchen"},
    "짜증": {"palette": "warm red and lilac purple", "lighting": "evening glow with soft sparkles"},
    "거짓말": {"palette": "gentle blue and gray", "lighting": "night moonlight reflection on floor"},
    "싸움": {"palette": "teal and golden yellow", "lighting": "playground sunset light"},
    "미루기": {"palette": "pastel pink and beige", "lighting": "soft morning light on desk"},
    "두려움": {"palette": "soft navy and mint", "lighting": "twilight gentle blue"},
    "불안": {"palette": "lavender and warm beige", "lighting": "early morning soft glow"},
    "자존감": {"palette": "sky blue and white", "lighting": "bright afternoon light"},
}
DEFAULT_THEME = {"palette": "pastel rainbow mix", "lighting": "warm daylight"}

# ─────────────────────────────
# 프롬프트 (훈육 주제별 상황 포함)
# ─────────────────────────────
PROMPT_TEMPLATE = """
너는 5~9세 어린이를 위한 **훈육 중심 감성 동화 작가**야.  
입력된 정보를 바탕으로, 아이가 공감하며 스스로 배우는 짧고 따뜻한 이야기를 만들어.  

─────────────────────────────
📥 입력 정보  
- 이름: {name}  
- 나이: {age}  
- 성별: {gender}  
- 훈육 주제: {goal}  
─────────────────────────────

🎯 이야기 목적  
- 훈육을 꾸짖음이 아닌 **공감과 상상**으로 표현한다.  
- 직접적인 해결(“짜증을 참았어요”, “맛있었어요”, “화해했어요”)은 금지.  
- 대신 아이의 감정이나 행동이 **상징적 변화·마법적 체험**을 통해 변한다.  
- 아이는 이야기 속 경험으로 ‘다시 해보고 싶다’는 느낌을 받는다.

─────────────────────────────
🧭 감정 흐름 (6단계 구조)
1. 공감 – 아이의 감정이나 불편함 묘사  
2. 고립 – 혼자 있는 순간  
3. 조력자 등장 – 상상 속 존재 등장 (요정·로봇·동물 등)  
4. 제안 – 조력자의 흥미로운 제안 또는 마법적 제시  
5. 시도 – 아이가 새로운 행동을 해봄  
6. 변화 – 직접적 해결 없이 상징적 변화나 신체감각으로 마무리  

─────────────────────────────
📖 표현 규칙
- 한 문장 12~15자, 한 장면 40~80자.
- 한자·추상어 금지 (“성실”, “용기” 대신 구체적 묘사)
- 감정은 몸짓으로 (“화났다” 대신 “볼이 빨개졌어요”)
- 훈육 주제 이름을 직접 말하지 않는다 (“편식”, “짜증” 등의 단어 사용 금지)
- 마무리는 다음 행동의 ‘기대감’으로.

─────────────────────────────
📸 시각 요소
각 장면은 동일한 캐릭터·색감·의상·조명으로 유지한다.
장면은 총 6장으로 구성된다.

─────────────────────────────
📘 출력 형식 (JSON)
{{
 "title": "동화 제목",
 "protagonist": "{name} ({age}살 {gender})",
 "global_style": {{
   "palette": "{palette}",
   "lighting": "{lighting}",
   "style": "pastel watercolor storybook"
 }},
 "scenes": [
   {{"text": "장면1 텍스트"}},
   {{"text": "장면2 텍스트"}},
   {{"text": "장면3 텍스트"}},
   {{"text": "장면4 텍스트"}},
   {{"text": "장면5 텍스트"}},
   {{"text": "장면6 텍스트"}}
 ],
 "ending": "따뜻하고 여운 있는 한 줄 마무리"
}}
─────────────────────────────
이제 {name}의 나이, 성별, 훈육 주제에 맞는
짧고 감성적인 동화를 만들어줘.
"""

# ─────────────────────────────
# GPT 요청 함수
# ─────────────────────────────
def generate_story(name, age, gender, goal):
    theme = THEME_MAP.get(goal, DEFAULT_THEME)
    palette, lighting = theme["palette"], theme["lighting"]

    prompt = PROMPT_TEMPLATE.format(
        name=name, age=age, gender=gender, goal=goal,
        palette=palette, lighting=lighting
    )

    logger.info(f"generate-story: {name}, {age}, {gender}, {goal}")
    start = time.time()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "You are a children’s story creator."},
                  {"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=1200
    )
    elapsed = time.time() - start
    logger.info(f"⏱ GPT 응답 시간: {elapsed:.1f}s")

    try:
        text = response.choices[0].message.content.strip()
        data = json.loads(text)
        return data
    except Exception:
        logger.warning("⚠️ JSON 파싱 실패, 원문 반환")
        return {"raw_text": response.choices[0].message.content}

# ─────────────────────────────
# 라우트
# ─────────────────────────────
@app.route("/generate-full", methods=["POST"])
def generate_full():
    payload = request.get_json()
    name = payload.get("name", "아이")
    age = payload.get("age", "6")
    gender = payload.get("gender", "아이")
    goal = payload.get("topic", "감정 표현")

    result = generate_story(name, age, gender, goal)
    return jsonify(result)

# ─────────────────────────────
# 메인
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
