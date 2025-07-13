from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import json
import os

# 🔐 환경 변수에서 OpenAI API 키 불러오기
openai.api_key = os.environ["OPENAI_API_KEY"]

app = Flask(__name__)

# ✅ CORS 전체 허용
CORS(app, resources={r"/*": {"origins": "*"}}, allow_headers="*", supports_credentials=True)


# ✅ 루트 헬스체크
@app.route("/", methods=["GET"])
def root():
    return "MyTales Flask API is running."


# ✅ 분석 요청 (GPT-4 기반)
@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json()

    name = data.get("name", "")
    age = data.get("age", "")
    gender = data.get("gender", "")
    favorite_color = data.get("favorite_color", "")
    education_goal = data.get("education_goal", "")
    answers = data.get("answers", [])

    if len(answers) != 20:
        return jsonify({"error": "20개의 응답이 필요합니다."}), 400

    prompt = f"""
부모가 유아 심리 테스트에 응답한 결과를 바탕으로, 아이의 성향을 해석하고 그 성향에 맞는 동화 방향과 이유를 설명한 뒤, 마지막에는 실제 동화 예시 본문을 10문장 정도 보여주세요.

아래 형식에 맞춰 JSON으로 출력하세요:

{{
  "character_name": "색+동물 아이",
  "character_summary": "한 줄 요약",
  "character_analysis": "성향 분석 결과 (10문장 이상, 부모가 응답했음을 반영)",
  "why_story_works": "왜 동화로 전달하는 것이 효과적인지 설명",
  "story_direction": "어떤 방향으로 동화를 구성하면 좋은지",
  "storybook_sample": "동화 본문 예시 (10문장 내외, 아이의 성별과 나이를 반영)",
  "character_image_description": "동화 주인공을 이미지로 표현한 설명 (Midjourney나 DALL·E 프롬프트로 사용할 수 있도록)"
}}

심리 테스트 응답: {answers}
부모가 훈육하고 싶은 주제: {education_goal}
아이 이름은 {name}, 나이는 {age}세, 성별은 {gender}, 좋아하는 색은 {favorite_color}입니다.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "너는 유아 심리 분석과 맞춤형 동화 제작 전문가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        result_text = response.choices[0].message.content.strip()
        structured = json.loads(result_text.encode("utf-8").decode("utf-8"))
        return jsonify({"result": structured})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ✅ 이미지 생성 요청 (DALL·E 3 API)
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return jsonify({"error": "이미지 프롬프트가 필요합니다."}), 400

    try:
        response = openai.Image.create(
            prompt=prompt,
            model="dall-e-3",
            size="1024x1024",
            response_format="url"
        )

        image_url = response["data"][0]["url"]
        retur

