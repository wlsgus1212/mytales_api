from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

# 환경 변수 로드
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

@app.route("/", methods=["GET"])
def root():
    return "MyTales Flask API is running."

# 무료 동화 생성 API
@app.route("/generate-story", methods=["POST"])
def generate_story():
    data = request.get_json()
    name = data.get("name", "")
    age = data.get("age", "")
    gender = data.get("gender", "")
    education_goal = data.get("education_goal", "")

    if not all([name, age, gender, education_goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    prompt = f"""
    아이의 이름은 {name}, 나이는 {age}세, 성별은 {gender}입니다.
    부모가 훈육하고 싶은 주제는 "{education_goal}"입니다.

    이 아이에게 적합한 맞춤형 동화를 만들어 주세요.
    총 6개의 문단으로 나눠주세요. 각각의 문단은 한 장면(슬라이드)에 해당하며, 각 문단은 3~4문장으로 구성해주세요.
    각 문단은 삽화를 생성할 수 있도록 구체적인 장면 묘사를 포함해주세요.

    JSON 배열 형식으로 출력:
    [
      "첫 번째 문단",
      "두 번째 문단",
      "세 번째 문단",
      "네 번째 문단",
      "다섯 번째 문단",
      "여섯 번째 문단"
    ]
    """

    try:
        # GPT 호출 (최신 SDK)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 유아 맞춤 동화 작가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        text_list = json.loads(response.choices[0].message.content.strip())

        # DALL·E 이미지 생성
        image_urls = []
        for text in text_list:
            image_response = client.images.generate(
                model="gpt-image-1",
                prompt=text,
                size="1024x1024"
            )
            image_urls.append(image_response.data[0].url)

        return jsonify({"texts": text_list, "images": image_urls})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
