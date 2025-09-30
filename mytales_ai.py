from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json

# ✅ 환경 변수에서 OpenAI API 키 가져오기
openai.api_key = os.environ["sk-proj-EfehanBccXc5jivKsSzx3Y0xDX07hMeg4OboUYA_zYAFZoCA3CSZen7q9rLfBVsXDFRlxJy4wkT3BlbkFJcN-puU4r1Ts2KOXcJVNrG2LZYEXnocpM2CwfzusD548kkntgZdMYGmLz1HQLM7e5C21SjMgQsAY"]

app = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
def root():
    return "MyTales Flask API is running."


# ✅ [1] 무료 동화 생성용 API (슬라이드 6장용)
@app.route("/generate-story", methods=["POST"])
def generate_story():
    data = request.get_json()

    name = data.get("name", "")
    age = data.get("age", "")
    gender = data.get("gender", "")
    education_goal = data.get("education_goal", "")

    if not all([name, age, gender, education_goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    # 🔮 GPT 프롬프트 구성
    prompt = f"""
아이의 이름은 {name}, 나이는 {age}세, 성별은 {gender}입니다.
부모가 훈육하고 싶은 주제는 "{education_goal}"입니다.

이 아이에게 적합한 맞춤형 동화를 만들어 주세요.
총 6개의 문단으로 나눠주세요. 각각의 문단은 한 장면(슬라이드)에 해당하며, 각 문단은 3~4문장으로 구성해주세요.
각 문단은 삽화를 생성할 수 있도록 구체적인 장면 묘사를 포함해주세요.

JSON 배열 형식으로 다음과 같이 출력해 주세요:

[
  "첫 번째 문단 텍스트",
  "두 번째 문단 텍스트",
  ...
  "여섯 번째 문단 텍스트"
]
"""

    try:
        # ✅ 1. 동화 텍스트 생성 (GPT-4)
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "너는 유아 맞춤 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        text_list = json.loads(response.choices[0].message.content.strip())

        # ✅ 2. 삽화 이미지 생성 (DALL·E)
        image_urls = []
        for text in text_list:
            image_response = openai.Image.create(
                model="dall-e-3",
                prompt=text,
                size="1024x1024",
                response_format="url"
            )
            image_urls.append(image_response["data"][0]["url"])

        return jsonify({
            "texts": text_list,
            "images": image_urls
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ✅ [2] 심리검사 분석용 API
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
        structured = json.loads(result_text)
        return jsonify({"result": structured})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ✅ [3] 이미지 단독 생성 API
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return jsonify({"error": "이미지 생성에 필요한 프롬프트가 없습니다."}), 400

    try:
        response = openai.Image.create(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            response_format="url"
        )
        image_url = response["data"][0]["url"]
        return jsonify({"image_url": image_url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ✅ 서버 실행
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
