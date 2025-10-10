from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, traceback, logging, random

# ───────────────────────────────
# 1️⃣ 환경설정
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
# 보호 단어 및 필터 설정
# ───────────────────────────────
PROTECTED_KEYS = {"holding", "sitting", "kitchen", "carrot", "smiling", "window",
                  "garden", "tree", "friend", "toy", "animal", "leaf"}
BANNED = [
    "blood","kill","dead","violence","weapon","fight","ghost","drug","alcohol",
    "beer","wine","sex","realistic","photoreal","gore","scary","logo","text","brand","war"
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

# ───────────────────────────────
# 이름 조사 처리
# ───────────────────────────────
def format_child_name(name: str) -> str:
    if not name:
        return name
    last_char = name[-1]
    last_code = ord(last_char) - 0xAC00
    has_final = (last_code % 28) != 0
    return f"{name}이는" if has_final else f"{name}는"

# ───────────────────────────────
# 안전하게 정화 (핵심 단어 보호)
# ───────────────────────────────
def sanitize_caption(caption: str, name="child", age="8", gender="child"):
    if not caption:
        caption = ""
    # 보호 처리: 잠깐 마스킹
    for word in PROTECTED_KEYS:
        caption = re.sub(rf"\b{re.escape(word)}\b", f"__KEEP__{word}", caption, flags=re.I)

    # 대체 단어 적용
    for k, v in REPLACE.items():
        caption = re.sub(rf"\b{k}\b", v, caption, flags=re.I)

    # 금지어 제거
    for k in BANNED:
        caption = re.sub(rf"\b{k}\b", "", caption, flags=re.I)

    # 기본적으로 허용하지 않을 문자 제거
    caption = re.sub(r'["\'`<>]', " ", caption).strip()

    # 단어 수 제한
    words = caption.split()
    if len(words) > 45:
        caption = " ".join(words[:45])

    # tail 보강 (중복 추가 방지)
    tail = ", same character and same world, consistent outfit and hairstyle, pastel tone, soft watercolor storybook style, child-friendly, no text, no logos"
    if "storybook" not in caption.lower():
        caption = caption.rstrip(", ") + tail

    # 나이/성별 정보가 없으면 추가
    if not re.search(r"\b\d+[- ]?year[- ]?old\b|\b세\b", caption):
        caption = f"{age}-year-old {gender} named {name}, " + caption

    # 보호 단어 복원
    for word in PROTECTED_KEYS:
        caption = caption.replace(f"__KEEP__{word}", word)

    # 최종 공백 정리
    caption = re.sub(r"\s{2,}", " ", caption).strip()
    return caption

# ───────────────────────────────
# 이미지 프롬프트 생성 보조 함수
# ───────────────────────────────
def build_image_prompt(scene_caption: str, name: str, age: str, gender: str, style_desc: str):
    character_block = f"{age}-year-old {gender} named {name}, {style_desc}, same outfit across scenes"
    constraints = "no text, no logos, child-safe, pastel watercolor storybook"
    # 명확한 순서로 결합 (캐릭터 블록 -> 장면 캡션 -> 제한)
    prompt = f"{character_block}, {scene_caption}, {constraints}"
    # 불필요한 쉼표 중복 제거
    prompt = re.sub(r",\s*,+", ",", prompt).strip(", ").strip()
    return prompt

# ───────────────────────────────
# GPT 이미지 묘사 생성 함수 (구조화된 출력 요청)
# ───────────────────────────────
def describe_scene(paragraph, name, age, gender, style_desc="", scene_index=0):
    try:
        # GPT에게 구조화된 JSON 출력을 요청해서 핵심 요소를 추출
        prompt = f"""
You are an expert illustrator for children's storybooks.
Break the following scene into structured fields to create a single concise descriptive sentence for image generation.
Return JSON only with keys: action, facial_expression, background, props, mood, one_sentence.

Scene {scene_index + 1} text:
\"\"\"{paragraph}\"\"\"

Character info: {age}-year-old {gender} named {name}; style: {style_desc}

Guidelines:
- Make 'one_sentence' a vivid single English sentence suitable for image generation.
- Keep the sentence child-friendly and include the important prop or imaginary friend if present.
- Keep output short but specific.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert children's illustrator."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.7,
            max_tokens=400,
        )

        raw = res.choices[0].message.content.strip()
        # 로그로 GPT 원본 저장 (디버그용)
        log.info("describe_scene raw output: %s", raw.replace("\n", " "))

        # GPT가 JSON을 그대로 내보내지 않을 경우를 대비한 회복 시도
        try:
            # 빠르게 JSON 추출: 가장 바깥의 JSON 객체를 찾음
            json_text = re.search(r"\{.*\}", raw, flags=re.S).group(0)
            parsed = json.loads(json_text)
        except Exception:
            # fallback: GPT가 단순 문장을 반환하면 구조화된 dict로 변환
            sentence = raw.splitlines()[0].strip()
            parsed = {"one_sentence": sentence,
                      "action": "", "facial_expression": "", "background": "", "props": "", "mood": ""}

        sentence = parsed.get("one_sentence", "").strip()
        if not sentence:
            sentence = parsed.get("action", "") + " " + parsed.get("background", "")
            sentence = sentence.strip()

        caption = sentence or f"{age}-year-old {gender} named {name}, smiling in a storybook watercolor scene."
        # sanitize 하되 보호 단어는 유지
        caption = sanitize_caption(caption, name, age, gender)
        # 최종 프롬프트 빌드
        final_prompt = build_image_prompt(caption, name, age, gender, style_desc)
        # 로그에 최종 프롬프트 남기기
        log.info("describe_scene final image prompt: %s", final_prompt)
        return final_prompt

    except Exception:
        log.error("❌ describe_scene GPT 오류: %s", traceback.format_exc())
        fallback = f"{age}-year-old {gender} named {name}, smiling in a storybook watercolor scene."
        return build_image_prompt(sanitize_caption(fallback, name, age, gender), name, age, gender, style_desc)

# ───────────────────────────────
# 동화 생성 엔드포인트
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

        name_particle = format_child_name(name)

        # 옷 & 머리 랜덤 스타일 고정 (서버에서 일관되게 관리)
        hair_options = ["short curly brown hair", "long straight black hair", "wavy chestnut hair"]
        outfit_options = ["yellow shirt and blue overalls", "red polka-dot dress", "green hoodie and beige pants"]
        hair = random.choice(hair_options)
        outfit = random.choice(outfit_options)
        style_desc = f"{hair}, wearing {outfit}"

        # GPT에게 구조화된 JSON 형식으로 동화 생성 요청
        prompt = f"""
너는 ‘훈육 동화봇’이라는 이름의 이야기 마법사야.
5~9세 어린이를 위한 공감 가득한 동화를 만들고, 아이가 스스로 느끼며 배울 수 있게 도와줘.

정보:
- 이름: {name}
- 나이: {age}
- 성별: {gender}
- 훈육 주제: {goal}

목표:
- 감정 표현 중심, 반복 구조, 따뜻한 표현
- 아이가 스스로 깨달을 수 있는 이야기
- 각 장면에 말하는 동물, 장난감, 채소 친구, 자연 요소 등 상상력 자극 요소 포함

출력 형식:
JSON 하나의 객체로 반환. keys: title, chapters(5 items 배열, each: title, paragraph, illustration), character (name, age, gender, style).
각 chapter.paragraph는 2-4 문장 내외, child-friendly.

반드시 JSON만 출력.
"""
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "너는 어린이를 위한 상상력 풍부한 동화를 만드는 이야기 마법사야."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.95,
            max_tokens=1800,
        )

        content = res.choices[0].message.content.strip()
        log.info("generate_story raw output: %s", content.replace("\n", " "))

        # 코드 블럭 제거 후 JSON 파싱
        content = re.sub(r"```json|```", "", content).strip()
        story_data = json.loads(content)

        # 스타일은 생성된 캐릭터에서 우선 취함
        style_desc = story_data.get("character", {}).get("style", style_desc)

        story = []
        for i, item in enumerate(story_data.get("chapters", [])):
            paragraph = item.get("paragraph", "").strip()
            # 장면별로 이미지 프롬프트 생성
            caption_prompt = describe_scene(paragraph, name, age, gender, style_desc=style_desc, scene_index=i)
            story.append({
                "title": item.get("title", ""),
                "paragraph": paragraph,
                "illustration": item.get("illustration", ""),
                "illustration_prompt": caption_prompt
            })

        response_payload = {
            "title": story_data.get("title"),
            "character": story_data.get("character"),
            "story": story
        }

        return Response(json.dumps(response_payload, ensure_ascii=False), content_type="application/json; charset=utf-8")

    except Exception as e:
        log.error("❌ generate-story error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 이미지 생성 엔드포인트 (프롬프트 후보 제공 + 선택 생성)
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    try:
        data = request.get_json(force=True)
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        # 다수 후보 생성: 원문, 정제본, 그리고 안전한 축약본
        candidates = []
        candidates.append(prompt)
        candidates.append(sanitize_caption(prompt))
        candidates.append(sanitize_caption(prompt.split(",")[0] if "," in prompt else prompt))

        # 유니크화
        candidates = list(dict.fromkeys(candidates))

        last_exception = None
        for idx, p in enumerate(candidates):
            try:
                log.info("Trying image generation candidate %d: %s", idx + 1, p[:200])
                r = client.images.generate(model="dall-e-3", prompt=p, size="1024x1024", quality="standard")
                url = r.data[0].url
                return jsonify({"image_url": url, "used_prompt": p}), 200
            except Exception as ex:
                log.warning("Image attempt %d failed: %s", idx + 1, str(ex))
                last_exception = ex
                continue

        # 모든 시도 실패 시 안전한 페일백
        fallback = sanitize_caption("child smiling warmly in a safe bright place, watercolor style")
        try:
            r3 = client.images.generate(model="dall-e-3", prompt=fallback, size="1024x1024", quality="standard")
            url = r3.data[0].url
            return jsonify({"image_url": url, "used_prompt": fallback, "note": "fallback"}), 200
        except Exception as ex:
            log.error("❌ generate-image fallback failed: %s", traceback.format_exc())
            return jsonify({"error": str(last_exception or ex)}), 500

    except Exception as e:
        log.error("❌ generate-image error: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ───────────────────────────────
# 실행
# ───────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)