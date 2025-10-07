@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    name = data.get("name", "").strip()
    age = data.get("age", "")
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    # 🧠 통합 프롬프트
    prompt = (
        f"너는 5~8세 아이를 위한 전문 동화 작가이자 삽화 연출가야.\n"
        f"아이 이름은 '{name}', 나이는 {age}세, 성별은 {gender}야.\n"
        f"훈육 주제는 '{goal}'이야.\n\n"
        "아이에게 교훈이 자연스럽게 전달되는 6문단짜리 유아용 동화를 써줘.\n"
        "각 문단은 3~4문장으로 구성하고, 내용이 자연스럽게 이어지도록 해.\n"
        "각 문단에는 따뜻하고 구체적인 장면 묘사를 포함시켜.\n"
        "또한 각 문단 옆에 그 문단을 그림으로 표현하기 좋은 삽화 설명도 함께 만들어줘.\n\n"
        "출력은 JSON 형식으로 아래 예시처럼 만들어:\n"
        "[\n"
        " {\"paragraph\": \"첫 번째 문단 내용\", \"image_prompt\": \"첫 번째 문단에 어울리는 그림 설명\"},\n"
        " {\"paragraph\": \"두 번째 문단 내용\", \"image_prompt\": \"두 번째 문단에 어울리는 그림 설명\"},\n"
        " ...\n"
        "]"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 감성적이고 상상력 풍부한 유아동화 작가이자 삽화 연출가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.75,
            max_tokens=1500
        )

        content = res.choices[0].message.content.strip()
        log.info("✅ GPT Response (preview): %s", content[:250])

        try:
            story = json.loads(content)
        except Exception:
            story = []

        if not isinstance(story, list) or not story:
            return jsonify({"error": "Invalid story format"}), 500

        # 이름 대입, 공백 제거
        for s in story:
            s["paragraph"] = s.get("paragraph", "").replace("??", name).strip()
            s["image_prompt"] = s.get("image_prompt", "").strip()

        return Response(
            json.dumps({"story": story}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error("❌ Error generating story: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500
