from flask import Flask, request, jsonify
from flask_cors import CORS  # CORS 라이브러리 추가

app = Flask(__name__)
CORS(app)  # 모든 도메인에서 API 호출 가능하도록 설정

@app.route("/generate_story", methods=["POST"])
def generate_story():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    name = data.get("name", "아이")
    age = data.get("age", "0")
    gender = data.get("gender", "미정")
    interest = data.get("interest", "모험")
    diary_entry = data.get("diary_entry", "오늘 하루는 어땠나요?")

    story = f"{name}({age}세, {gender})는 {interest} 속에서 신비로운 
여행을 떠납니다. \n오늘의 일기: {diary_entry}"

    return jsonify({"story": story})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)

