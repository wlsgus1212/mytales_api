from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging, random

# ───────────────────────────────
# 환경설정
# ───────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mytales")

# ───────────────────────────────
# 상수 및 필터
# ───────────────────────────────
PROTECTED_KEYS = {"holding", "sitting", "kitchen", "carrot", "smiling", "window",
                  "garden", "tree", "friend", "toy", "animal", "leaf"}
BANNED = [
    "blood","kill","dead","violence","weapon","fight","ghost","drug","alcohol",
    "beer","wine","sex","photoreal","gore","scary","logo","brand","war"
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
    "hand-drawn 2D storybook illustration, soft pastel palette, consistent linework, "
    "gentle watercolor texture, flat clean shading, same artist style across all images, "
    "no photorealism, no text, no speech bubbles, no captions, no logos, child-safe"
)

# ───────────────────────────────
# 유틸: 이름 조사
# ───────────────────────────────
def format_child_name(name: str) -> str:
    if not name:
        return name
    last_char = name[-1]
    last_code = ord(last_char) - 0xAC00
    has_final = (last_code % 28) != 0
    return f"{name}이는" if has_final else f"{name}는"

# ───────────────────────────────
# sanitize: 텍스트/말풍선 제거, 핵심 단어 보호
# ───────────────────────────────
def sanitize_caption(caption: str, name="child", age="8", gender="child"):
    if not caption:
        caption = ""

    # 보호 단어 마스킹
    for word in PROTECTED_KEYS:
        caption = re.sub(rf"\b{re.escape(word)}\b", f"__KEEP__{word}", caption, flags=re.I)

    # 치환 및 금지어 처리
    for k, v in REPLACE.items():
        caption = re.sub(rf"\b{re.escape(k)}\b", v, caption, flags=re.I)
    for k in BANNED:
        caption = re.sub(rf"\b{re.escape(k)}\b", "", caption, flags=re.I)

    # 텍스트·말풍선 유발 단어 제거
    text_terms = ["speech", "speech bubble", "speech-bubble", "speechbubble",
                  "speechballoon", "bubble", "talking caption", "caption", "text", "words", "lettering",
                  "speechbubble", "speechbubble"]
    for t in text_terms:
        caption = re.sub(rf"\b{re.escape(t)}\b", "", caption, flags=re.I)

    caption = re.sub(r'["\'`<>]', " ", caption).strip()
    words = caption.split()
    if len(words) > 45:
        caption = " ".join(words[:45])

    # tail 추가(중복 방지)
    tail = "same character and same world, consistent outfit and hairstyle, pastel tone, soft watercolor storybook style, child-friendly, no text, no speech bubbles, no captions"
    if tail.lower() not in caption.lower():
        caption = caption.rstrip(", ") + ", " + tail

    # 나이/성별 추가
    if not re.search(r"\b\d+[- ]?year[- ]?old\b|\b세\b", caption):
        caption = f"{age}-year-old {gender} named {name}, " + caption

    # 보호 단어 복원
    for word in PROTECTED_KEYS:
        caption = caption.replace(f"__KEEP__{word}", word)

    caption = re.sub(r"\s{2,}", " ", caption).strip()
    return caption

# ───────────────────────────────
# 빌드: 최종 이미지 프롬프트 (캐릭터 프로필 고정)
# ───────────────────────────────
def build_image_prompt(scene_sentence: str, character_profile: dict):
    # character_profile expects keys: name_en, name_ko (optional), age, gender, style
    name_en = character_profile.get("name_en", character_profile.get("name", "Child"))
    age = character_profile.get("age", "8")
    style_desc = character_profile.get("style", "").strip()

    character_block = f"{age}-year-old child named {name_en}, {style_desc}, same outfit and hairstyle across scenes"
    # 한 문장으로 제한: scene_sentence 최초 문장 및 25단어 이하
    scene_sentence = scene_sentence.split(".")[0].strip()
    words = scene_sentence.split()
    if len(words) > 25:
        scene_sentence = " ".join(words[:25])

    prompt = f"{character_block}. {scene_sentence}. {STYLE_CONSTRAINTS}"
    prompt = re.sub(r"\s{2,}", " ", prompt).strip()
    # 중복 문구 제거 간단 처리
    prompt = re.sub(r"(no text(?:, )?){2,}", "no text, ", prompt)
    prompt = re.sub(r"(no speech bubbles(?:, )?){2,}", "no speech bubbles, ", prompt)
    return prompt

# ───────────────────────────────
# 장면 묘사: GPT로부터 영어 한 문장 얻기 (낮은 temperature)
# ───────────────────────────────
def describe_scene(paragraph: str, character_profile: dict, scene_index=0):
    try:
        name_en = character_profile.get("name_en", character_profile.get("name", "Child"))
        age = character_profile.get("age", "8")
        gender = character_profile.get("gender", "child")
        style_desc = character_profile.get("style", "")

        prompt = f"""
You are an expert children's illustrator. For the following short scene, return a single concise English sentence suitable for image generation. Return only one sentence, no JSON, no lists, no code blocks.
Character: {age}-year-old {gender} named {name_en}, outfit and hairstyle: {style_desc}.
Scene text: "{paragraph}"
Constraints: keep it child-friendly and focused on a single moment; do not include any written text, speech bubbles, captions, or lettering.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert children's illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.25,
            max_tokens=120,
        )
        raw = res.choices[0].message.content.strip()
        log.info("describe_scene raw output: %s", raw.replace("\n", " "))

        # 코드블럭/불필요 텍스트 제거
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            # JSON이 아닌 경우에도 전체 텍스트에서 첫 문장 추출
            try:
                # 시도: JSON이 아닌 단순 텍스트인 경우 fallback
                raw = re.sub(r"```.*?```", "", raw, flags=re.S).strip()
            except Exception:
                raw = raw
        # 한 문장만 취함
        sentence = raw.splitlines()[0].split(".")[0].strip()
        if not sentence:
            sentence = f"{age}-year-old child named {name_en} in a gentle watercolor scene"
        # 텍스트 관련 어휘 제거 재확인
        sentence = re.sub(r"\b(speech|bubble|caption|text|lettering)\b", "", sentence, flags=re.I).strip()
        # sanitize 및 프롬프트 조합
        sanitized = sanitize_caption(sentence, name=name_en, age=age, gender=gender)
        final_prompt = build_image_prompt(sanitized, character_profile)
        log.info("describe_scene final image prompt: %s", final_prompt)
        return final_prompt

    except Exception:
        log.error("❌ describe_scene GPT 오류: %s", traceback.format_exc())
        fallback = f"{character_profile.get('age','8')}-year-old child named {character_profile.get('name_en','Child')} in a gentle watercolor storybook."
        return build_image_prompt(sanitize_caption(fallback, name=character_profile.get('name_en','Child')), character_profile)

# ───────────────────────────────
# 동화 생성 엔드포인트 (character profile 포함 반환)
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

        # 서버에서 고정 스타일 선택
        hair_options = ["short curly brown hair", "long straight black hair", "wavy chestnut hair"]
        outfit_options = ["yellow shirt and blue overalls", "red polka-dot dress", "green hoodie and beige pants"]
        hair = random.choice(hair_options)
        outfit = random.choice(outfit_options)
        style_desc = f"{hair}, wearing {outfit}"

        # 영어 이름 생성(간단 규칙: 사용자가 입력한 이름 romanization을 기대할 수 없으므로 영어 표기 제공)
        # 여기서는 name 자체를 영어로 쓰게 하거나 간단 변환; 필요시 별도 매핑 적용
        name_en = re.sub(r"[^A-Za-z0-9 ]", "", name) or "Child"

        prompt = f"""
너는 어린이를 위한 이야기 마법사야. 아래 정보를 바탕으로 5개 장면의 따뜻한 동화를 JSON으로 반환해줘.
정보: 이름:{name}, 나이:{age}, 성별:{gender}, 주제:{goal}.
출력형식: JSON object with keys: title, chapters (array of 5 items: title, paragraph, illustration(optional)), character (name_ko, name_en, age, gender, style).
각 chapter.paragraph는 2-4문장, child-friendly. 반드시 JSON만 출력.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "너는 어린이를 위한 상상력 풍부한 동화를 만드는 이야기 마법사야."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.9,
            max_tokens=1800,
        )

        content = res.choices[0].message.content.strip()
        log.info("generate_story raw output: %s", content.replace("\n", " "))

        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        # character profile 보강: 서버에서 확실히 갖고있도록 함
        character = story_data.get("character", {})
        character.setdefault("name_ko", name)
        character.setdefault("name_en", name_en)
        character.setdefault("age", age)
        character.setdefault("gender", gender)
        character.setdefault("style", style_desc)

        # 장면별로 illustration_prompt 생성 (일관된 character profile 사용)
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
        log.error("❌ generate-story error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 이미지 생성 엔드포인트 (final prompt 사용, used_prompt 포함 응답)
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = (data.get("prompt") or "").strip()
        character = data.get("character")  # optional character profile dict

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 클라이언트가 장면 문장만 보냈다면 character가 필요함
        if character and isinstance(character, dict):
            final_prompt = build_image_prompt(prompt, character)
        else:
            # 이미 완성된 프롬프트가 전달된 경우라도 sanitize 적용
            final_prompt = sanitize_caption(prompt, name="child", age="8", gender="child")

        log.info("generate-image final prompt: %s", final_prompt)

        def attempt(p):
            return client.images.generate(model="dall-e-3", prompt=p, size="1024x1024", quality="standard")

        # 시도 1: final_prompt
        try:
            r = attempt(final_prompt)
            url = r.data[0].url
            return jsonify({"image_url": url, "used_prompt": final_prompt}), 200
        except Exception:
            log.warning("generate-image attempt 1 failed, retrying with stronger text-ban")
            simplified = final_prompt + ", no text, no speech bubbles, no captions"
            try:
                r2 = attempt(simplified)
                url = r2.data[0].url
                return jsonify({"image_url": url, "used_prompt": simplified}), 200
            except Exception:
                log.error("generate-image all attempts failed: %s", traceback.format_exc())
                return jsonify({"error": "image generation failed"}), 500

    except Exception as e:
        log.error("❌ generate-image error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)