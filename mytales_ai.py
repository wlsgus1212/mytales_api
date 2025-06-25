from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import json
import os

openai.api_key = os.environ["OPENAI_API_KEY"]

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/", methods=["GET"])
def root():
    return "MyTales Flask API is running."

@app.route("/analyze", methods=["POST"])
def analyze():
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
  "storybook_sample": "동화 본문 예시 (10문장 내외, 아이의 성별과 나이를 반영)"
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
        result_text = result_text.encode("utf-8").decode("utf-8")
        structured = json.loads(result_text)

        return jsonify({"result": structured})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
