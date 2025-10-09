from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging

# ───────────────────────────────
# 1️⃣ 초기 설정
# ───────────────────────────────
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ───────────────────────────────
# 2️⃣ 조사 자동 처리
# ───────────────────────────────
def with_particle(name: str) -> str:
    if not name:
        return name
    last_char = name[-1]
    code = ord(last_char) - 44032
    has_final = (code % 28) != 0
    return f"{name}은" if has_final else f"{name}는"

# ───────────────────────────────
# 3️⃣ 동화 생성 API
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        age = data.get("age", "")
        gender = data.get("gender", "").strip()
        goal = data.get("education_goal", "").strip()

        if not all([name, age, gender, goal]):
            return jsonify({"error": "모든 항목을 입력해주세요."}), 400

        name_particle = with_particle(name)

        # ─────────────── 프롬프트 (보완 버전) ───────────────
        prompt = f"""
너는 5~8세 어린이를 위한 감성 그림책 작가이자 일러스트 디렉터야.  
이야기의 목적은 아이가 자신의 감정과 행동을 이해하고,  
상상과 현실이 어우러진 따뜻한 경험 속에서 스스로 바른 선택을 배우는 것이다.  
글은 짧고 리듬감 있게, 그림은 감정과 사건을 생생하게 보여줘야 한다.  

📘 기본 정보  
- 주인공 이름: {name} ({name_particle})  
- 나이: {age}세  
- 성별: {gender}  
- 훈육 주제: '{goal}'  

---

### 🪄 이야기 설계 규칙
1. 이야기는 4~7개의 장면(scene)으로 구성하며, 각 장면은 3~5문장으로 자연스럽게 이어져야 한다.  
2. 첫 장면은 현실적인 상황에서 시작하되,  
   중간 이후에는 상상·의인화·꿈·모험 등 창의적 전환이 자연스럽게 등장해야 한다.  
3. 판타지적 요소가 등장할 경우, 반드시 주인공의 감정 변화나 문제 해결과 연결되어야 한다.  
4. {name}의 감정은 매 장면마다 이유가 있어야 하며, 마지막 장면에서 처음과 대비되는 따뜻한 변화로 마무리하라.  
5. 각 장면에는 {name}의 마음속 생각 한 줄을 포함해, 감정의 이유와 결과를 보여줘라.  
6. {name}이 올바른 행동을 선택했을 때는 **즐겁고 상징적인 보상 사건**이 일어나야 한다.  
   단, 보상은 과하지 않고 훈육 주제({goal})와 직접 관련되어야 한다.  
   예:  
   - 편식 → 브로콜리를 먹자 힘이 생겨 친구를 도왔다.  
   - 거짓말 → 솔직히 말하자 요정의 마법이 돌아왔다.  
   - 용기 → 두려움을 이기자 무지개 다리가 나타났다.  
7. 결말은 교훈을 직접 말하지 말고, 행동·표정·세상의 변화로 표현하라.  
8. 문장은 낭독했을 때 리듬이 느껴지게 짧고 부드럽게 써라.  
9. 의태어·의성어(‘톡톡’, ‘반짝반짝’, ‘살금살금’)와 반복 문장을 활용하라.  
10. 감정은 형용사보다 행동이나 묘사로 표현하라.  
11. 조력자가 등장할 수 있으나, 결말의 핵심은 반드시 {name}의 결정과 행동이어야 한다.  
12. 결말의 감정은 항상 따뜻하지만, 종류는 다양해야 한다.  
    (감동, 자신감, 웃음, 호기심 중 하나로 마무리하라.)  

---

### 🎨 삽화(image_prompt) 설계 지침
1. 각 장면마다 반드시 "image_prompt"를 포함해야 한다.  
2. image_prompt는 한 문장(30단어 이하)으로 작성하며, 아래 요소를 자연스럽게 포함해야 한다:  
   등장인물, 행동, 배경, 조명, 감정 분위기, 스타일.  
3. 모든 image_prompt에 다음 문구를 반드시 포함하라:  
   - "{gender} child named {name}, same appearance as previous scene"  
   - "hair color, hairstyle, outfit, and facial features remain identical"  
4. {name}의 외형(머리색, 머리 모양, 옷 색상, 표정)은 모든 장면에서 동일해야 한다.  
5. 첫 번째 장면에는 캐릭터의 외형과 배경 색감을 명시하라.  
6. 이후 장면의 image_prompt는 "consistent with previous scene illustration"을 포함하라.  
7. 배경은 같은 세계 안에서 시간대만 변할 수 있다 (아침 → 낮 → 저녁).  
8. 감정에 따라 색감 온도를 변화시켜라:  
   - 긴장: 부드러운 그림자,  
   - 깨달음/행동: 밝은 빛,  
   - 결말: 따뜻한 저녁빛.  
9. 스타일 지침:  
   - 첫 장면에만 전체 스타일 키워드를 포함:  
     “soft watercolor storybook style, pastel color palette, warm gentle light, consistent character design”  
   - 이후 장면에는 “same soft watercolor tone and lighting”으로 표현.  
10. 장면별 시각적 초점을 다르게 두라:  
   - 1장면: 넓은 구도 (소개)  
   - 2~3장면: 문제나 감정 클로즈업  
   - 4~5장면: 상상/전환/보상 장면  
   - 마지막 장면: 평온한 마무리  

---

### 🩵 톤앤매너 및 문체
- 문장은 아이가 듣자마자 장면을 그릴 수 있을 만큼 간결하고 따뜻해야 한다.  
- 한 문장에는 한 감정 또는 한 행동만 담아라.  
- 대사는 한 장면당 한 줄 이하로 제한하라.  
- 반복 문장이나 후렴구를 사용해 리듬을 살려라.  
- 감정의 변화는 글보다 그림에서 보여주고, 문장은 리듬과 감정의 박자 역할을 한다.  

---

### 🚫 금지 규칙
- 불안하거나 폭력적이거나 어두운 소재는 절대 사용하지 마라.  
- 슬픔, 분노, 두려움이 등장하더라도 반드시 부드럽게 해소되어야 한다.  

---

### 📦 출력 형식 (JSON 배열만)
[
  {{
    "paragraph": "첫 번째 장면 내용 (3~5문장, 감정 이유와 리듬 포함)",
    "image_prompt": "한 문장(30단어 이하)으로 구성된 삽화 설명. {gender} child named {name}, same appearance as previous scene, soft watercolor storybook style, pastel color palette, warm gentle light, consistent character design"
  }},
  ...
  {{
    "paragraph": "마지막 장면 내용 (3~5문장, 상징적 보상과 여운)",
    "image_prompt": "consistent with previous scene illustration, same soft watercolor tone and lighting"
  }}
]

⚠️ 주의  
- JSON 외의 설명, 텍스트, 코드블록(```)은 절대 포함하지 마라.  
- 모든 장면은 한 세계 안에서 시간과 감정의 흐름이 자연스럽게 이어져야 한다.  
- text와 image_prompt는 서로 정확히 대응되어야 한다.  
- 그림만 봐도 사건과 감정이 이해되어야 한다.
"""

        # ─────────────── GPT 요청 ───────────────
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )

        content = response.choices[0].message.content.strip()
        log.info("✅ GPT Response preview: %s", content[:250])

        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        story = []
        for i, item in enumerate(story_data):
            paragraph = item.get("paragraph", "").strip()
            image_prompt = item.get("image_prompt", "").strip()
            if not image_prompt:
                image_prompt = f"{name_particle}이 등장하는 장면: {paragraph[:60]}"
            story.append({
                "paragraph": paragraph,
                "image_prompt": image_prompt
            })

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story:\n%s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 4️⃣ 이미지 생성 API
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt", "").strip()

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        safe_prompt = (
            f"Children's storybook illustration, watercolor and pastel tones, "
            f"soft lighting, gentle atmosphere, consistent human child character, "
            f"avoid animals, monsters, or adult themes. {prompt}"
        )

        result = client.images.generate(
            model="dall-e-3",
            prompt=safe_prompt,
            size="1024x1024",
            quality="standard"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image returned by OpenAI"}), 500

        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("❌ Error generating image:\n%s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 5️⃣ 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
