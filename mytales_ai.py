from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, MyTales API is running!"

@app.route("/generate_story", methods=["POST"])
def generate_story():
    data = request.get_json()
    
    if not data or "name" not in data or "interest" not in data:
        return jsonify({"error": "Missing 'name' or 'interest' in request"}), 400
    
    # 사용자 입력 받기
    child_name = data.get("name", "아이")
    age = data.get("age", "7")
    gender = data.get("gender", "남")
    interest = data.get("interest", "모험")
    diary_entry = data.get("diary_entry", "")

    # 동화 생성
    story = f"""{child_name}는 {age}살 {gender}이며, {interest} 속에서 
신비로운 여행을 떠납니다.
그러던 중, 예상치 못한 만남을 하게 되고, 흥미진진한 모험이 시작됩니다.
"{diary_entry}"라는 경험을 바탕으로, {child_name}는 이 여행에서 중요한 
교훈을 얻고 집으로 돌아옵니다."""

    return jsonify({"story": story})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
