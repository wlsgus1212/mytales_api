from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

OPENAI_API_KEY = "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"

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

STORY_SAVE_PATH = "generated_stories.json"

@app.route("/generate_story", methods=["POST"])
def generate_story():
    data = request.json
    user_input = data.get("user_input", "")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": user_input}],
        "max_tokens": 500
    }

    response = requests.post(OPENAI_URL, headers=headers, json=payload)

    if response.status_code == 200:
        story = response.json()["choices"][0]["message"]["content"]

        # AI 응답을 JSON 파일로 저장
        story_data = {"user_input": user_input, "story": story}
        
        # 기존 파일이 있으면 불러와서 추가 저장
        if os.path.exists(STORY_SAVE_PATH):
            with open(STORY_SAVE_PATH, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        else:
            existing_data = []

        existing_data.append(story_data)

        with open(STORY_SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

        return jsonify({"story": story})

    else:
        return jsonify({"error": "API 요청 실패"}), response.status_code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
