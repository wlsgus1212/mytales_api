from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re

# ───────────────────────────────
# 환경 설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)

# ───────────────────────────────
# 캐릭터 설정 생성
# ───────────────────────────────
def generate_character_profile(name, age, gender):
    hair_options = ["short curly brown hair", "long straight black hair", "wavy chestnut hair"]
    outfit_options = ["yellow shirt and blue overalls", "red polka-dot dress", "green hoodie and beige pants"]
    hair = random.choice(hair_options)
    outfit = random.choice(outfit_options)
    style = f"{hair}, wearing {outfit}"

    return {
        "name_en": name,
        "age": age,
        "gender": gender,
        "style": style,
        "visual": {
            "face": "round face with soft cheeks",
            "eyes": "warm brown almond eyes",
            "hair": hair,
            "outfit": outfit,
            "proportions": "childlike proportions"
        }
    }

# ───────────────────────────────
# 장면 설명 문장 생성
# ───────────────────────────────
def describe_scene(paragraph, character_profile):
    name = character_profile.get("name_en", "Child")
    age = character_profile.get("age", "8")
    gender = character_profile.get("gender", "child")
    style = character_profile.get("style", "")

    prompt = f"""
You are an expert children's illustrator. Given the following story scene, write one vivid and detailed English sentence that describes the exact moment to illustrate. 
Include the character's emotion, action, and background. Avoid generic phrases. Do not include any written text or speech bubbles.
Character: {age}-year-old {gender} named {name}, outfit and hairstyle: {style}.
Scene: "{paragraph}"
"""

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert children's illustrator."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.2,
        max_tokens=120,
    )

    sentence = res.choices[0].message.content.strip()
    sentence = re.sub(r"[\"<>]", "", sentence)
    return sentence

# ───────────────────────────────
# 이미지 프롬프트 생성
# ───────────────────────────────
def build_image_prompt(scene_sentence, character_profile):
    visual = character_profile.get("visual", {})
    name = character_profile.get("name_en", "Child")
    age = character_profile.get("age", "8")
    gender = character_profile.get("gender", "child")

    face = visual.get("face", "")
    eyes = visual.get("eyes", "")
    hair = visual.get("hair", "")
    outfit = visual.get("outfit", "")
    proportions = visual.get("proportions", "")

    prompt = (
        f"Scene: {scene_sentence}. "
        f"The character is a {age}-year-old {gender} named {name}, with {face}, {hair}, {eyes}, wearing {outfit}. "
        f"Use soft watercolor style, warm lighting, and child-friendly tone. No text or speech bubbles."
    )
    return prompt.strip()

# ───────────────────────────────
# 동화 생성 엔드포인트
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    goal = data.get("education_goal", "").strip()

    if not all([name, age, gender, goal]):
        return jsonify({"error": "모든 항목을 입력해주세요."}), 400

    character_profile = generate_character_profile(name, age, gender)

    # 예시 동화 본문 (실제 GPT 호출로 대체 가능)
    story_paragraphs = [
        f"{name} sits quietly under a yellow lamp on a rainy evening, holding a small book.",
        f"Outside the window, raindrops fall gently as {name} looks out with a thoughtful expression.",
        f"{name} smiles softly as a warm breeze enters the room, brushing her hair."
    ]

    image_descriptions = [describe_scene(p, character_profile) for p in story_paragraphs]

    return jsonify({
        "story": story_paragraphs,
        "character_profile": character_profile,
        "image_descriptions": image_descriptions
    })

# ───────────────────────────────
# 이미지 생성 엔드포인트
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    character_profile = data.get("character_profile", {})
    scene_description = data.get("image_description", "")

    if not character_profile or not scene_description:
        return jsonify({"error": "캐릭터 정보와 장면 설명이 필요합니다."}), 400

    prompt = build_image_prompt(scene_description, character_profile)

    # OpenAI 이미지 생성 호출
    res = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1
    )

    image_url = res.data[0].url
    return jsonify({"image_url": image_url})