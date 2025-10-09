# mytales_ai.py
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

        # ─────────────── 프롬프트 ───────────────
        prompt = f"""
너는 5~8세 어린이를 위한 감성 그림책 작가이자 일러스트 디렉터야.  
이야기의 목적은 아이가 감정을 이해하고, 따뜻한 상상 속에서 스스로 깨달음을 얻는 것이다.  
글은 짧고 리듬감 있게, 그림은 감정을 시각으로 전달해야 한다.  

📘 기본 정보  
- 주인공 이름: {name} ({name_particle})  
- 나이: {age}세  
- 성별: {gender}  
- 훈육 주제: '{goal}'  

---

### 🪄 이야기 설계 규칙
1. 총 6개의 장면(scene)으로 구성하되, 각 장면은 3~5문장으로 자연스럽게 이어져야 한다.  
2. 이야기는 현실적인 상황에서 시작해, 중간에는 상상·꿈·의인화·모험 등의 창의적 전환이 포함될 수 있다.  
3. 판타지적 요소가 등장할 경우, 반드시 주인공의 감정이나 문제 해결과 연결되어야 한다.  
4. {name}의 감정은 매 장면마다 이유를 가지고 변화해야 하며, 마지막 장면에서 처음과 대비되게 마무리하라.  
5. 결말은 교훈을 직접 말하지 말고, 행동이나 표정, 주변의 변화로 느껴지게 표현하라.  
6. 문장은 낭독했을 때 리듬이 느껴지도록 짧고 부드럽게 써라.  
7. 의태어·의성어(‘톡톡’, ‘반짝반짝’, ‘살금살금’)와 반복 리듬을 자연스럽게 활용하라.  
8. 감정은 형용사보다 행동과 묘사로 보여줘라.  
9. 조력자가 등장하더라도, 결말의 핵심은 반드시 {name}의 결정과 행동이어야 한다.  

---

### 🎨 삽화(image_prompt) 설계 지침
1. 각 장면마다 반드시 "image_prompt"를 포함해야 한다.  
2. image_prompt는 한 문장으로 작성하며, 다음 요소를 자연스럽게 포함하라:  
   - 등장인물(주인공 포함), 행동, 배경, 조명, 감정 분위기, 스타일.  
3. {name}의 외형(짧은 갈색 머리, 밝은 눈, 노란 셔츠)은 모든 장면에서 동일해야 한다.  
4. 각 장면의 배경은 같은 세계 안에서 시간대만 달라질 수 있다.  
   예: 아침빛 → 낮의 햇살 → 저녁 노을 → 밤의 반짝임.  
5. 감정 변화에 따라 색감 온도를 부드럽게 조정하라.  
   - 긴장감: 살짝 흐린 색,  
   - 깨달음: 밝은 빛,  
   - 마무리: 따뜻한 저녁빛.  
6. 스타일은 항상 “soft watercolor storybook style, pastel color palette, warm gentle light, consistent character design”.  
7. 첫 번째 장면에서 캐릭터의 머리색·의상·배경 주요 색을 명시하라.  
8. 모든 장면에 “same character as previous scene, consistent with previous scene illustration” 문구를 포함하라.  
9. The main character must always appear as a human child, not as an animal, object, or creature.  
10. All scenes must depict the same child character with identical face shape, hairstyle, clothing, and proportions.  
11. The background should evolve naturally within the same world (for example: the same home, school, or garden at different times of day).

---

### 🩵 톤앤매너 및 문체
- 문장은 5~8세 아이가 들었을 때 바로 그림을 떠올릴 수 있을 만큼 단순하게 써라.  
- 한 문장에는 한 감정 또는 한 행동만 담아라.  
- 대사는 한 장면에 한 줄 이하로만 사용하라.  
- 감정의 변화는 글보다 그림으로 표현하되, 글은 그 리듬을 받쳐주는 역할을 한다.  
- 이야기의 분위기는 따뜻하고, 아이가 “또 읽고 싶다”고 느낄 만큼 편안해야 한다.  

---

### 🚫 금지 규칙
- 불안하거나 폭력적이거나 어두운 소재는 절대 사용하지 마라.  
- 슬픔, 분노, 무서움이 등장해도 반드시 부드럽게 해소되어야 한다.  
- 음식, 음료, 알코올, 흡연, 공포, 싸움, 성인 소재는 절대 금지.  

---

### 📦 출력 형식
Do not add explanations, markdown, or commentary — output only valid JSON.

[
  {{
    "paragraph": "첫 번째 장면 내용 (3~5문장, 감정과 리듬 중심)",
    "image_prompt": "등장인물, 행동, 배경, 조명, 감정, 스타일을 포함한 한 문장 (soft watercolor storybook style, pastel color palette, warm gentle light, consistent character design, same character as previous scene)"
  }},
  ...,
  {{
    "paragraph": "여섯 번째 장면 내용 (3~5문장, 여운이 남는 따뜻한 마무리)",
    "image_prompt": "consistent character and background, soft watercolor storybook style, warm gentle light"
  }}
]
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
