from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/generate_story", methods=["POST"])
def generate_story():
    print("Received data:", request.data)  # 요청 데이터 출력
    data = request.get_json()

    if not data:
        return jsonify({"error": "Invalid JSON format"}), 400

    name = data.get("name", "아이")
    age = data.get("age", "7")
    gender = data.get("gender", "남")
    interest = data.get("interest", "모험")
    diary_entry = data.get("diary_entry", "")

    story = f"{name}({age}세, {gender})는 {interest} 속에서 신비로운 여행을 떠납니다. \n"
    story += f"오늘의 일기: {diary_entry}"

    return jsonify({"story": story})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
