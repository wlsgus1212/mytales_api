from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/", methods=["GET"])
def root():
    return "MyTales Flask API is running."

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()

    answers = data.get("answers", [])
    education_goal = data.get("education_goal", "")

    if len(answers) != 20:
        return jsonify({"error": "20개의 응답이 필요합니다."}), 400

    prompt = f"""
다음은 유아의 심리 테스트 결과입니다:
- 응답 점수: {answers}
- 부모가 전달하고 싶은 훈육 주제: {education_goal}

이 정보를 바탕으로 아래 형식의 결과를 만들어주세요.

1. character_name: "색+동물 아이" 형태로 출력 (예: "분홍토끼 아이")
2. character_summary: 한 줄 요약
3. character_analysis: 10문장 이상의 성향 해석
4. why_story_works: 동화로 전달하면 좋은 이유
5. story_direction: 동화가 어떤 방향으로 구성되면 좋을지 요약

결과는 다음 JSON 형식으로 출력해주세요:
{{
  "character_name": "...",
  "character_summary": "...",
  "character_analysis": "...",
  "why_story_works": "...",
  "story_direction": "..."
}}
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "너는 유아 심리 분석 전문가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        result_text = response.choices[0].message.content

        try:
            structured = json.loads(result_text)
            return jsonify({"result": structured})
        except json.JSONDecodeError:
            return jsonify({
                "error": "GPT 응답을 JSON으로 파싱할 수 없습니다.",
                "raw": result_text
            }), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

