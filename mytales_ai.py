from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, logging, traceback

# ────────────────────────────────────────────────
# 1️⃣ 환경 설정
# ────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")


# ────────────────────────────────────────────────
# 2️⃣ 조사 자동 보정 함수 (자연스러운 구어체)
# ────────────────────────────────────────────────
def with_particle(name: str) -> str:
    """이름 뒤에 자연스러운 조사 '은/는/이는'을 붙인다."""
    if not name:
        return name

    last_char = name[-1]
    code = ord(last_char) - 44032
    has_final = (code % 28) != 0  # 받침 여부

    # 받침이 있지만 '이는'으로 자연스럽게 발음되는 이름 목록
    soft_sound_names = [
        "현", "민", "진", "윤", "린", "빈", "원", "연", "훈", "준", "은", "선", "안", "환"
    ]

    if last_char in soft_sound_names:
        return f"{name}이는"
    elif not has_final:  # 받침 없음
        return f"{name}는"
    else:
        return f"{name}은"


# ────────────────────────────────────────────────
# 3️⃣ /generate-story : 자유 구조 + 감정 리듬 동화 생성
# ────────────────────────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = data.get("name", "").strip()
    age = data.get("age", "")
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    name_particle = with_particle(name)

    # 🧠 창의 확장형 V13 프롬프트
    prompt = f"""
너는 5~8세 어린이를 위한 감성적이고 상상력 넘치는 동화 작가이자 유아 그림책 일러스트 디렉터야.  
이야기의 목표는 아이가 훈육 주제인 '{goal}'를 스스로 깨닫게 하는 감정적이고 창의적인 이야기를 만드는 것이다.  
이야기는 현실, 판타지, 미래, 공주 이야기, 동물 세계 등 어떤 세계관으로도 시작할 수 있다.  
중요한 것은 감정의 흐름과 따뜻한 교훈이 자연스럽게 이어지는 것이다.  

---

📘 기본 정보
- 주인공 이름: {name} ({name_particle})
- 나이: {age}세
- 성별: {gender}
- 훈육 주제: '{goal}'

---

🪄 서사 지침 (형식 자유 + 감정 리듬 필수)
1. 이야기는 자유로운 배경에서 시작해도 된다.  
   예: "{name}이라는 공주가 살았어요.", "달 위의 아이 {name}은 매일 별을 닦았어요."
2. 다만 다음 감정 리듬은 반드시 포함되어야 한다.  
   - 시작: 평화롭거나 호기심 많은 상태  
   - 중간: 문제·갈등·감정의 혼란  
   - 절정: 시련 혹은 깨달음  
   - 결말: 성찰·변화·따뜻한 여운  
3. 교훈은 설교식이 아니라 상징적 사건이나 행동으로 표현하라.  
4. 전체 톤은 부드럽고 따뜻하며, 문장은 짧고 낭독감 있게 구성하라.  
5. 한두 번 정도 리듬 문장을 반복하여 아이가 기억하기 쉽게 만들어라.  
   예: “후우, 바람이 속삭였어요.”, “토도독, 별들이 웃었어요.”

---

🎨 삽화 지침 (시각 일관성 + 상징적 연출)
1. 각 장면은 “paragraph”와 “image_prompt” 한 세트로 구성한다.  
2. 주인공 {name}의 외형은 모든 장면에서 동일해야 하며, 다음 문구를 포함한다.  
   "same appearance as previous scene, identical hairstyle, hair color, outfit, and facial features"
3. 첫 장면에는 {age}세 {gender} 아동의 외형을 구체적으로 묘사하라.  
   (예: shoulder-length brown hair, light pink dress, curious expression, early morning sunlight)  
4. 삽화 스타일: “soft watercolor storybook style, pastel colors, cinematic lighting, warm emotion”  
5. 장면마다 색조 변화로 감정을 시각적으로 표현하라.  
   - 혼란/불안: 차가운 푸른빛  
   - 깨달음/행복: 따뜻한 노을빛  
6. 마지막 장면에는 상징적 변화(바람, 빛, 나뭇잎, 별 등)를 포함하라.  

---

💭 감정 및 교훈 표현
- '{goal}'은 직접 말로 설명하지 않고, 상징적 경험으로 느끼게 하라.  
- {name_particle}은 마지막에 행동으로 변화해야 한다. (사과, 도전, 나눔 등)  
- 아이의 감정을 한 문장씩 명시하라. (“{name_particle}의 마음은 따뜻해졌어요.”)  
- 결말은 한 줄의 시적 여운으로 끝내라.  
  예: “그날 이후, {name_particle}의 마음에는 햇살이 머물렀어요.”

---

🚫 금지 및 주의
- 폭력, 공포, 죽음, 절망, 슬픔 중심의 서사 금지.  
- 성인적 유머, 사회비판, 비극적 결말 금지.  
- 설명문이나 코드블록, JSON 외 텍스트 출력 금지.  

---

📦 출력 형식(JSON 배열)
[
  {{
    "paragraph": "이야기의 첫 장면 (자유로운 세계관에서 시작, 주인공과 배경, 감정 도입)",
    "image_prompt": "{age}-year-old {gender} child named {name}, described appearance and setting, soft watercolor storybook style"
  }},
  {{
    "paragraph": "이야기의 중간 장면들 (문제 발생, 감정 변화, 상징적 사건, 리듬 문장 포함)",
    "image_prompt": "consistent with previous scene, showing symbolic or magical event, same character appearance, cinematic watercolor tone"
  }},
  {{
    "paragraph": "마지막 장면 (감정의 해소, 교훈의 상징, 따뜻한 여운으로 마무리)",
    "image_prompt": "same appearance as previous scene, warm lighting, gentle smile, symbolic motif of change (light, wind, stars, or flowers)"
  }}
]
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 어린이를 위한 감성적인 동화를 쓰는 전문가이자 일러스트 디렉터야."},
                {"role": "user", "content": prompt.strip()},
            ],
            temperature=0.85,
            max_tokens=1600,
        )

        content = response.choices[0].message.content.strip()
        content = re.sub(r"```json|```", "", content).strip()
        log.info("✅ GPT Response preview: %s", content[:250])

        story_data = json.loads(content)
        if isinstance(story_data, dict):
            story_data = [story_data]

        story = []
        for i, item in enumerate(story_data):
            paragraph = item.get("paragraph", "").strip() if isinstance(item, dict) else str(item)
            image_prompt = item.get("image_prompt", "").strip() if isinstance(item, dict) else ""

            if not image_prompt and paragraph:
                image_prompt = f"유아 그림책 스타일로, {name_particle}이 등장하는 장면. {paragraph[:40]}"

            story.append({
                "paragraph": paragraph or f"{i+1}번째 장면: 내용 누락",
                "image_prompt": image_prompt or f"{name_particle}이 등장하는 장면."
            })

        return Response(json.dumps({"story": story}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────────
# 4️⃣ /generate-image : DALL·E 3 삽화 생성
# ────────────────────────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        result = client.images.generate(
            model="dall-e-3",
            prompt=f"soft watercolor storybook illustration, warm pastel tones, {prompt}",
            size="1024x1024",
            quality="standard"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image returned by OpenAI"}), 500

        log.info("🖼️ Image generated successfully: %s", image_url)
        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("❌ Error generating image: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────────
# 5️⃣ 앱 실행
# ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
