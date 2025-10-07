@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        text_prompt = data.get("prompt", "").strip()
        if not text_prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 🎨 1️⃣ GPT로 ‘삽화용 묘사 프롬프트’ 생성
        scene_prompt_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 유아용 그림책 삽화 디자이너야. "
                        "아래 문단 내용을 읽고, 장면을 구체적으로 묘사하는 한 줄 프롬프트를 작성해. "
                        "아이, 표정, 배경, 색감, 분위기를 포함하고, 실사나 금속, 패턴, 조형물 묘사는 절대 하지 마."
                    ),
                },
                {"role": "user", "content": text_prompt},
            ],
            temperature=0.7,
            max_tokens=150,
        )

        refined_prompt = (
            scene_prompt_res.choices[0].message.content.strip()
            if scene_prompt_res.choices
            else text_prompt
        )

        # 🎨 2️⃣ DALL·E로 실제 이미지 생성
        full_prompt = (
            f"유아용 동화책 삽화 스타일로 그려줘. {refined_prompt}. "
            "밝고 따뜻한 파스텔톤, 부드러운 선, 귀여운 인물, 자연 배경."
        )

        result = client.images.generate(
            model="dall-e-2",
            prompt=full_prompt,
            size="512x512"
        )

        image_url = result.data[0].url if result.data else None
        if not image_url:
            return jsonify({"error": "No image returned"}), 500

        log.info("🖼️ Generated image prompt: %s", refined_prompt)
        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        log.error("❌ Error generating image: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500
