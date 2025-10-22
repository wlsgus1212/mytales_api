from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import base64

app = Flask(__name__)
CORS(app)

# ─────────────────────────────
# 캐릭터 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face; warm brown eyes; childlike proportions; gender: {gender}; age: {age}."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit,
            "eyes": "따뜻한 갈색 눈",
            "proportions": "아이 같은 비율"
        }
    }

# ─────────────────────────────
# 이미지 더미 생성 (Base64 placeholder)
# ─────────────────────────────
def dummy_base64_image(text="Sample"):
    text_bytes = text.encode("utf-8")
    b64 = base64.b64encode(text_bytes).decode("utf-8")
    return f"data:text/plain;base64,{b64}"

# ─────────────────────────────
# 동화 + 이미지 통합 생성 API
# ─────────────────────────────
@app.route("/generate-story-full", methods=["POST"])
def generate_story_full():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = data.get("education_goal", data.get("topic", "")).strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic required"}), 400

    # 캐릭터 정보
    character = generate_character_profile(name, age, gender)

    # 동화 기본 요소
    title = f"{name}와 마법의 {topic} 여행"
    toc = ["마법의 시작", f"{name}의 고민", "신비한 친구들", f"{topic}의 비밀", "행복한 마무리"]
    paragraphs = [
        f"{name}는 {age}살 {gender} 아이예요. 요즘 {topic} 때문에 고민이 많았어요.",
        f"그래서 {name}는 마법의 숲으로 여행을 떠났어요. 길을 따라 걷다 보니 반짝이는 호수가 나왔어요.",
        f"그곳에서 여우, 토끼, 다람쥐 친구들이 나타나 인사를 했어요. '어서 와!'",
        f"{name}는 친구들과 함께 놀며 {topic}이 무엇인지 하나씩 배웠어요.",
        f"마지막엔 커다란 나무가 나타나 이렇게 말했어요. '너는 이미 잘하고 있단다.'"
    ]
    illustrations = [
        "아이 방 안에서 인형을 안고 있는 아이",
        "숲길을 걷는 아이, 햇살이 내리쬠",
        "여우와 토끼가 웃으며 아이를 맞이함",
        "세 친구가 함께 놀고 있는 장면",
        "반짝이는 나무가 말을 거는 환상적인 장면"
    ]

    # 이미지 생성 (Base64 더미 생성 또는 실제 생성기와 연결 가능)
    image_urls = [dummy_base64_image(desc) for desc in illustrations]

    return jsonify({
        "title": title,
        "table_of_contents": toc,
        "character_profile": character,
        "story_paragraphs": paragraphs,
        "image_descriptions": illustrations,
        "image_urls": image_urls,
        "ending": "작은 용기와 따뜻한 마음이 {name}를 더 멋지게 만들었어요."
    })

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
