import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, MyTales API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render의 환경 변수를 사용
    app.run(host="0.0.0.0", port=port)
