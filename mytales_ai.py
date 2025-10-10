### 전체 Flask 앱 코드 (visual 필드 안전화 포함)

```python
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging, random

# ───────────────────────────────
# 환경
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ───────────────────────────────
# 상수: 안전·스타일·치환
# ───────────────────────────────
PROTECTED_KEYS = {"holding", "sitting", "garden", "carrot", "broccoli", "pumpkin", "smiling", "window"}
BANNED = [
    "blood","kill","dead","violence","weapon","fight","ghost","drug","alcohol",
    "beer","wine","sex","gore","scary","logo","brand","war"
]
REPLACE = {
    "monster": "friendly imaginary friend",
    "fight": "face the challenge",
    "weapon": "magic wand",
    "blood": "red ribbon",
    "dark": "warm light",
    "fire": "gentle light",
    "realistic": "watercolor",
    "photo": "watercolor"
}

STYLE_CONSTRAINTS = (
    "hand-drawn 2D storybook illustration; soft pastel palette; consistent linework and line thickness across all images; "
    "gentle watercolor texture; flat clean shading; same artist style across all images; identical facial features and proportions across scenes; "
    "identical outfit and hairstyle across scenes; NO photorealism; NO comic panels; NO speech bubbles; NO text; NO logos; child-safe"
)

# ───────────────────────────────
# 유틸: 이름 처리, visual 안전화
# ───────────────────────────────
def format_child_name(name: str) -> str:
    if not name:
        return name
    last_char = name[-1]
    last_code = ord(last_char) - 0xAC00
    has_final = (last_code % 28) != 0
    return f"{name}이는" if has_final else f"{name}는"

def ensure_visual_dict(visual_field):
    if isinstance(visual_field, dict):
        return visual_field
    if isinstance(visual_field, str) and visual_field.strip():
        v = visual_field.strip()
        # 간단 파싱: 문자열을 hair/face로 재활용
        return {
            "face": v if len(v) <= 40 else v[:40],
            "eyes": "warm brown almond eyes",
            "nose": "small button nose",
            "hair": v,
            "hair_accessory": "yellow ribbon",
            "outfit": "yellow shirt and blue overalls with a small heart patch on left pocket",
            "proportions": "childlike proportions, same scale across scenes",
            "mark": ""
        }
    return {
        "face": "round face with soft cheeks and light freckles",
        "eyes": "warm brown almond eyes",
        "nose": "small button nose",
        "hair": "short curly brown hair",
        "hair_accessory": "yellow ribbon",
        "outfit": "yellow shirt and blue overalls with a small heart patch on left pocket",
        "proportions": "childlike proportions, same scale across scenes",
        "mark": ""
    }

# ───────────────────────────────
# sanitize: 텍스트 제거 + 보호 단어 마스킹
# ───────────────────────────────
def sanitize_caption(caption: str, name="child", age="8", gender="child"):
    if not caption:
        caption = ""

    for word in PROTECTED_KEYS:
        caption = re.sub(rf"\b{re.escape(word)}\b", f"__KEEP__{word}", caption, flags=re.I)

    for k, v in REPLACE.items():
        caption = re.sub(rf"\b{re.escape(k)}\b", v, caption, flags=re.I)
    for k in BANNED:
        caption = re.sub(rf"\b{re.escape(k)}\b", "", caption, flags=re.I)

    text_terms = ["speech", "speech bubble", "speech-bubble", "speechbubble",
                  "speechballoon", "bubble", "caption", "text", "words", "lettering"]
    for t in text_terms:
        caption = re.sub(rf"\b{re.escape(t)}\b", "", caption, flags=re.I)

    caption = re.sub(r'["\'`<>]', " ", caption).strip()
    words = caption.split()
    if len(words) > 45:
        caption = " ".join(words[:45])

    tail = "same character and same world, consistent outfit and hairstyle, pastel tone, soft watercolor storybook style, child-friendly, no text, no speech bubbles, no captions"
    if tail.lower() not in caption.lower():
        caption = caption.rstrip(", ") + ", " + tail

    if not re.search(r"\b\d+[- ]?year[- ]?old\b|\b세\b", caption):
        caption = f"{age}-year-old {gender} named {name}, " + caption

    for word in PROTECTED_KEYS:
        caption = caption.replace(f"__KEEP__{word}", word)

    caption = re.sub(r"\s{2,}", " ", caption).strip()
    return caption

# ───────────────────────────────
# build_image_prompt: 시각 세부속성 고정 + 한 문장 프롬프트
# ───────────────────────────────
def build_image_prompt(scene_sentence: str, character_profile: dict):
    visual = character_profile.get("visual")
    if not isinstance(visual, dict):
        visual = ensure_visual_dict(visual)
        character_profile["visual"] = visual

    name_en = character_profile.get("name_en", character_profile.get("name", "Child"))
    age = character_profile.get("age", "8")
    gender = character_profile.get("gender", "child")
    style_desc = character_profile.get("style", "").strip()

    face = visual.get("face", "round face with soft cheeks")
    eyes = visual.get("eyes", "warm brown almond eyes")
    nose = visual.get("nose", "small button nose")
    hair = visual.get("hair", "short curly brown hair")
    hair_acc = visual.get("hair_accessory", "yellow ribbon")
    outfit = visual.get("outfit", "yellow shirt and blue overalls with a small heart patch on left pocket")
    proportions = visual.get("proportions", "childlike proportions, same scale across scenes")
    mark = visual.get("mark", "")

    character_block = (
        f"{age}-year-old {gender} named {name_en}; face: {face}; eyes: {eyes}; nose: {nose}; "
        f"hair: {hair} with {hair_acc}; outfit: {outfit}; proportions: {proportions}"
    )
    if mark:
        character_block += f"; distinctive mark: {mark}"

    scene_sentence = scene_sentence.split(".")[0].strip()
    words = scene_sentence.split()
    if len(words) > 25:
        scene_sentence = " ".join(words[:25])

    prompt = f"{character_block}. {scene_sentence}. {STYLE_CONSTRAINTS}"
    prompt = re.sub(r"\s{2,}", " ", prompt).strip()
    return prompt

# ───────────────────────────────
# describe_scene: scene paragraph -> 영어 한 문장 -> final prompt
# ───────────────────────────────
def describe_scene(paragraph: str, character_profile: dict, scene_index=0):
    try:
        name_en = character_profile.get("name_en", character_profile.get("name", "Child"))
        age = character_profile.get("age", "8")
        gender = character_profile.get("gender", "child")
        style_desc = character_profile.get("style", "")

        prompt = f"""
You are an expert children's illustrator. For the following short scene, return a single concise English sentence suitable for image generation. Return only one sentence, no extra JSON, no lists, no code blocks, and do not include any written text or speech bubbles in the sentence.
Character: {age}-year-old {gender} named {name_en}, outfit and hairstyle: {style_desc}.
Scene text: "{paragraph}"
Constraints: child-friendly; focus on a single clear action or moment; do not include words like 'speech', 'bubble', 'caption', or any written text.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert children's illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.15,
            max_tokens=120,
        )
        raw = res.choices[0].message.content.strip()
        log.info("describe_scene raw output: %s", raw.replace("\n", " "))

        raw = re.sub(r"```.*?```", "", raw, flags=re.S).strip()
        sentence = raw.splitlines()[0].split(".")[0].strip()
        if not sentence:
            sentence = f"{age}-year-old child named {name_en} in a gentle watercolor scene"

        sentence = re.sub(r"\b(speech|bubble|caption|text|lettering)\b", "", sentence, flags=re.I).strip()
        sanitized = sanitize_caption(sentence, name=name_en, age=age, gender=gender)
        final_prompt = build_image_prompt(sanitized, character_profile)
        log.info("describe_scene final image prompt: %s", final_prompt)
        return final_prompt

    except Exception:
        log.error("describe_scene error: %s", traceback.format_exc())
        fallback_sentence = f"{character_profile.get('age','8')}-year-old child named {character_profile.get('name_en','Child')} in a gentle watercolor storybook."
        return build_image_prompt(sanitize_caption(fallback_sentence, name=character_profile.get('name_en','Child')), character_profile)

# ───────────────────────────────
# generate-story: produce story JSON + consistent character_profile
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    try:
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        age = data.get("age", "")
        gender = data.get("gender", "").strip()
        goal = data.get("education_goal", "").strip()

        if not all([name, age, gender, goal]):
            return jsonify({"error": "모든 항목을 입력해주세요."}), 400

        hair_options = ["short curly brown hair", "long straight black hair", "wavy chestnut hair"]
        outfit_options = ["yellow shirt and blue overalls", "red polka-dot dress", "green hoodie and beige pants"]
        hair = random.choice(hair_options)
        outfit = random.choice(outfit_options)
        style_desc = f"{hair}, wearing {outfit}"

        name_en = re.sub(r"[^A-Za-z0-9 ]", "", name) or "Child"

        prompt = f"""
You are a children's story generator. Given the following info, produce a warm, child-friendly short story for ages 5-9 with 5 scenes.
Info: name: {name}, age: {age}, gender: {gender}, theme: {goal}.
Output: JSON object with keys: title, chapters (array of 5 items, each: title, paragraph (2-4 sentences), illustration (optional)), character (object with name_ko, name_en, age, gender, style, visual).
Do not include any extra text outside the JSON.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a warm children's storyteller."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.9,
            max_tokens=1800,
        )

        content = res.choices[0].message.content.strip()
        log.info("generate_story raw output: %s", content.replace("\n", " "))

        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        character = story_data.get("character", {})
        character.setdefault("name_ko", name)
        character.setdefault("name_en", name_en)
        character.setdefault("age", age)
        character.setdefault("gender", gender)
        character.setdefault("style", style_desc)

        visual_field = character.get("visual")
        character["visual"] = ensure_visual_dict(visual_field)

        story = []
        for i, item in enumerate(story_data.get("chapters", [])):
            paragraph = item.get("paragraph", "").strip()
            illustration_prompt = describe_scene(paragraph, character, scene_index=i)
            story.append({
                "title": item.get("title", ""),
                "paragraph": paragraph,
                "illustration": item.get("illustration", ""),
                "illustration_prompt": illustration_prompt
            })

        response_payload = {
            "title": story_data.get("title"),
            "character": character,
            "story": story
        }

        return Response(json.dumps(response_payload, ensure_ascii=False), content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("generate-story error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# generate-image: accepts scene sentence + character_profile OR final prompt
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = (data.get("prompt") or "").strip()
        character = data.get("character")

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        if character and isinstance(character, dict):
            # ensure visual dict
            if not isinstance(character.get("visual"), dict):
                character["visual"] = ensure_visual_dict(character.get("visual"))
            final_prompt = build_image_prompt(prompt, character)
        else:
            final_prompt = sanitize_caption(prompt, name="child", age="8", gender="child")

        if re.search(r"[가-힣]", final_prompt):
            cp = character or {}
            name_en = cp.get("name_en", "Child")
            age = cp.get("age", "8")
            scene_sentence = re.sub(r"[가-힣]", "", prompt)[:120].strip() or "a gentle storybook scene"
            final_prompt = build_image_prompt(scene_sentence, cp if cp else {"name_en": name_en, "age": age, "visual": {}})

        log.info("generate-image final prompt: %s", final_prompt)

        def attempt(p):
            return client.images.generate(model="dall-e-3", prompt=p, size="1024x1024", quality="standard")

        try:
            r = attempt(final_prompt)
            url = r.data[0].url
            return jsonify({"image_url": url, "used_prompt": final_prompt}), 200
        except Exception:
            log.warning("generate-image primary attempt failed, retrying with stronger no-text clause")
            simplified = final_prompt + ", no text, no speech bubbles, no captions"
            try:
                r2 = attempt(simplified)
                url = r2.data[0].url
                return jsonify({"image_url": url, "used_prompt": simplified}), 200
            except Exception:
                log.error("generate-image all attempts failed: %s", traceback.format_exc())
                return jsonify({"error": "image generation failed"}), 500

    except Exception as e:
        log.error("generate-image error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
```
