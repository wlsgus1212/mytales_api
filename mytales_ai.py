from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, random, logging, time, base64, requests
from io import BytesIO
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

# ─────────────────────────────
# 유틸
# ─────────────────────────────
def clean_text(s):
    return re.sub(r"[\"<>]", "", (s or "")).strip()

def safe_json_loads(s):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"(\{[\s\S]*\})", s)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
    return None

def ensure_character_profile(obj):
    """
    Accept dict or JSON string or canonical string.
    Return dict with visual.canonical, gender, age present where possible.
    """
    if not obj:
        return None
    if isinstance(obj, dict):
        visual = obj.get("visual") or {}
        canonical = visual.get("canonical") or obj.get("style") or ""
        if not visual.get("canonical"):
            visual["canonical"] = canonical
            obj["visual"] = visual
        # normalize gender/age keys
        if "gender" not in obj and visual.get("gender"):
            obj["gender"] = visual.get("gender")
        if "age" not in obj and visual.get("age"):
            obj["age"] = visual.get("age")
        return obj
    if isinstance(obj, str):
        parsed = safe_json_loads(obj)
        if isinstance(parsed, dict):
            return ensure_character_profile(parsed)
        m = re.search(r'Canonical\s*Visual\s*Descriptor\s*[:\-]?\s*(.+)', obj)
        canonical = m.group(1).strip() if m else obj.strip()
        return {
            "name": None,
            "age": None,
            "gender": None,
            "style": canonical,
            "visual": {
                "canonical": canonical,
                "hair": "",
                "outfit": "",
                "face": "",
                "eyes": "",
                "proportions": ""
            }
        }
    return None

# ─────────────────────────────
# 캐릭터 프로필 생성
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face; warm brown eyes; childlike proportions; gender: {gender}; age: {age}."
    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit,
            "eyes": "따뜻한 갈색 눈",
            "proportions": "아이 같은 비율"
        }
    }

# ─────────────────────────────
# 동화 생성 (훈육 규칙 강제 포함)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    logging.info("🧠 동화 생성 시작 (훈육 규칙 포함 프롬프트)")
    prompt = f"""
당신은 5~9세 아동을 위한 따뜻한 훈육 동화 작가입니다. 문장은 짧고 리드미컬합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

출력은 오직 JSON만 반환:
{{"title":"", "table_of_contents":["","",...], "character":"이름 (나이 성별)",
 "chapters":[{{"title":"", "paragraphs":["문장1","문장2"], "illustration":"(원문 문장 그대로)", "artist_description":"(일러스트레이터용 풍부한 장면 묘사)"}}, ... 5개], "ending":""}}

요구사항(엄격):
1) 총 5장(각 챕터 paragraphs 배열 2~3문장).
2) 스토리 아크: 발단→전개(최소 두 번의 시도 포함, 실패/학습 묘사)→절정(챕터4)→결말.
3) 등장: 주인공 + 의인화된 조력자(조력자는 반드시 '작은 규칙'을 하나 제시).
4) 훈육주제가 '편식'인 경우: 반드시 '작은 규칙'을 제시하라(예: '한 입만 천천히'). 주인공은 이 규칙을 최소 두 번 시도하고, 첫 시도에서 실패하거나 불편함을 겪고, 이후 점진적 개선을 통해 챕터4에서 스스로 규칙을 선택해 행동으로 옮겨야 한다.
5) 교훈은 직접적으로 "해야 한다" 식으로 말하지 말고 행동과 결과로 암시하라(칭찬, 자랑스러움, 부모의 포옹 등).
6) 각 챕터의 illustration 필드는 동화의 원문 문장 그대로 포함해야 한다.
7) 각 챕터의 artist_description은 일러스트레이터가 즉시 그릴 수 있도록 캐릭터 외형, 행동, 배경, 조명, 구도, 스타일 힌트를 포함해야 한다.
8) 출력 외 텍스트, 코드블록, 주석을 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a warm Korean children's story writer. Output only JSON."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.6,
            max_tokens=1400,
            timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            # normalize
            for ch in data["chapters"]:
                if "paragraphs" not in ch:
                    para = ch.get("paragraph") or ""
                    ch["paragraphs"] = [para] if para else []
                if "illustration" not in ch:
                    ch["illustration"] = ""
                if "artist_description" not in ch or not ch.get("artist_description"):
                    joined = " ".join(ch["paragraphs"])
                    ch["artist_description"] = make_artist_description_from_paragraph(joined, {"visual": {"canonical": f"Canonical Visual Descriptor: gender: {gender}; age: {age}."}})
            return data
    except Exception:
        logging.exception("동화 생성 실패")
    # fallback
    return {
        "title": f"{name}의 작은 모험",
        "table_of_contents": ["시작","발견","시도","절정","결말"],
        "character": f"{name} ({age} {gender})",
        "chapters": [
            {"title":"1. 시작","paragraphs":[f"{name}은 새로운 꿈을 꾸었어요.","문이 살짝 열렸어요."],"illustration":"", "artist_description":""},
            {"title":"2. 발견","paragraphs":["신비한 마을이 나타났어요.","소리들이 리듬을 만들었어요."],"illustration":"", "artist_description":""},
            {"title":"3. 시도","paragraphs":[f"{name}은(는) 조심스레 시도해봤어요.","처음엔 어색했어요."],"illustration":"", "artist_description":""},
            {"title":"4. 절정","paragraphs":["큰 결심의 순간이 왔어요.","작은 약속을 했어요."],"illustration":"", "artist_description":""},
            {"title":"5. 결말","paragraphs":["다음 날, 작은 약속을 지켰어요.","마음에 따뜻한 빛이 남았어요."],"illustration":"", "artist_description":""}
        ],
        "ending":"작은 약속이 큰 변화를 만들었어요."
    }

# ─────────────────────────────
# artist_description 자동 보강
# ─────────────────────────────
def make_artist_description_from_paragraph(paragraph, character_profile, default_place=None):
    canonical = ""
    if isinstance(character_profile, dict):
        canonical = character_profile.get("visual", {}).get("canonical", "").strip() or ""
    s = (paragraph or "").strip()
    if not s:
        s = "따뜻한 풍경"
    parts = re.split(r'[。\.!?!]|[,，;；]\s*', s)
    main = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if any(k in p for k in ["속삭", "다가", "도착", "만나", "춤", "노래", "도전", "시도", "결심", "제안", "만들"]):
            main = p
            break
    if not main:
        main = parts[0] if parts else s
    quote_m = re.search(r'["“”\']([^"\']{1,200})["“”\']', s)
    quote_summary = ""
    if quote_m:
        q = quote_m.group(1)
        if any(w in q for w in ["한 입","천천히","재미있는 모양","시도"]):
            quote_summary = "따뜻하게 권하는 말투"
        else:
            quote_summary = "부드럽게 속삭이는 분위기"
    place = default_place or ""
    for kw in ["채소 마을","채소마을","마을","정원","주방","숲","바다","교실","초원","집"]:
        if kw in s:
            place = kw
            break
    lighting = "부드러운 황금빛"
    composition = "mid-shot" if "속삭" in main or "다가" in main else "mid-shot"
    place_part = f"{place}에서 " if place else ""
    quote_part = f", 분위기: {quote_summary}" if quote_summary else ""
    illustration = f"{place_part}{main} 장면{quote_part}, {lighting}; 구도: {composition}."
    full = f"{canonical}. {illustration}" if canonical else illustration
    style_hints = "밝고 부드러운 색감; 따뜻한 수채화 스타일; 귀엽고 친근한 캐릭터; 텍스트 없음; 현실적 과장 없음"
    return f"{full} 스타일: {style_hints}"

# ─────────────────────────────
# 이미지 프롬프트 생성 (orientation 및 no-sketch 강제)
# ─────────────────────────────
def build_image_prompt(character_profile, artist_description, scene_index, previous_background=None, orientation="portrait"):
    cp = ensure_character_profile(character_profile)
    canonical = cp.get("visual", {}).get("canonical", "") if cp else ""
    gender = cp.get("gender") if cp and cp.get("gender") else ""
    age = cp.get("age") if cp and cp.get("age") else ""
    bg_hint = f"Maintain same background: {previous_background}." if previous_background else ""
    orientation_hint = "orientation: portrait; vertical composition; height > width; output upright orientation"
    avoid = "No pencil/sketch lines; no photorealism; no text or speech bubbles; no rough sketch artifacts."
    prompt = (
        f"{canonical} gender: {gender}; age: {age}. {artist_description} {bg_hint} {orientation_hint} "
        f"Constraints: {avoid} Render as: soft watercolor children's book illustration; warm soft lighting; pastel palette; mid-shot or close-up as suggested."
    )
    return prompt

# ─────────────────────────────
# 이미지 생성 및 후처리: orientation 검사와 회전(필요시)
# ─────────────────────────────
def image_url_to_upright_dataurl(url, target_orientation="portrait", timeout=15):
    """
    Fetch image from url, check orientation, rotate if needed, return data URL PNG.
    If fetching/parsing fails, return None.
    """
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
        w, h = img.size
        # if we expect portrait but got landscape -> rotate 90 deg
        if target_orientation == "portrait" and w > h:
            img = img.rotate(90, expand=True)
        elif target_orientation == "landscape" and h > w:
            img = img.rotate(90, expand=True)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        logging.exception("이미지 후처리(회전/데이터URL 생성) 실패")
        return None

def generate_image_from_prompt(character_profile, artist_description, scene_index, previous_background=None):
    prompt = build_image_prompt(character_profile, artist_description, scene_index, previous_background, orientation="portrait")
    logging.info("이미지 프롬프트(요약): %s", (prompt[:400] + "...") if len(prompt) > 400 else prompt)
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",  # portrait tall
            quality="standard",
            n=1,
            timeout=60
        )
        if res and getattr(res, "data", None):
            # get URL or b64 content depending on response shape
            candidate = res.data[0]
            # prefer url if present
            url = getattr(candidate, "url", None) or candidate.get("url") if isinstance(candidate, dict) else None
            if url:
                # ensure upright and return data URL for reliable orientation across clients
                dataurl = image_url_to_upright_dataurl(url, target_orientation="portrait")
                if dataurl:
                    return dataurl
                # fallback to original url if dataurl failed
                return url
            # sometimes API returns b64 directly
            b64 = getattr(candidate, "b64_json", None) or candidate.get("b64_json") if isinstance(candidate, dict) else None
            if b64:
                try:
                    img_bytes = base64.b64decode(b64)
                    img = Image.open(BytesIO(img_bytes))
                    w, h = img.size
                    if w > h:
                        img = img.rotate(90, expand=True)
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")
                except Exception:
                    logging.exception("b64 이미지 처리 실패")
            return None
        return None
    except Exception:
        logging.exception("이미지 생성 API 호출 실패")
        return None

# ─────────────────────────────
# 엔드포인트: /generate-story
# ─────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    age = (data.get("age") or "").strip()
    gender = (data.get("gender") or "").strip()
    topic = (data.get("topic") or data.get("education_goal") or "").strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic required"}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)

    # 보강: illustration/artist_description이 비어있으면 paragraph 기반으로 생성
    chapters = story.get("chapters", []) or []
    image_descriptions = []
    previous_bg = None
    for ch in chapters:
        paras = ch.get("paragraphs") or []
        paragraph_text = " ".join(paras) if isinstance(paras, list) else (ch.get("paragraph") or "")
        ill = (ch.get("illustration") or "").strip()
        artist_desc = (ch.get("artist_description") or "").strip()
        if not ill:
            ill = paragraph_text
            ch["illustration"] = ill
        if not artist_desc:
            artist_desc = make_artist_description_from_paragraph(paragraph_text, character, previous_bg)
            ch["artist_description"] = artist_desc
        for kw in ["채소 마을","채소마을","마을","정원","주방","숲","바다","교실","초원","집"]:
            if kw in paragraph_text:
                previous_bg = kw
                break
        image_descriptions.append(artist_desc)

    response = {
        "title": story.get("title"),
        "table_of_contents": story.get("table_of_contents") or [c.get("title","") for c in chapters],
        "character_profile": character,
        "chapters": chapters,
        "story_paragraphs": [(" ".join(c.get("paragraphs")) if isinstance(c.get("paragraphs"), list) else c.get("paragraph","")) for c in chapters],
        "image_descriptions": image_descriptions,
        "ending": story.get("ending", ""),
        "artist_question": "스토리의 흐름에 맞게 차례대로 그림을 그려줄까요?"
    }
    logging.info("Generated story with artist descriptions")
    return jsonify(response)

# ─────────────────────────────
# 엔드포인트: /generate-image
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    raw_cp = data.get("character_profile") or data.get("character") or data.get("characterProfile")
    scenes = data.get("image_descriptions") or data.get("scenes") or []

    character = ensure_character_profile(raw_cp)
    if not character:
        return jsonify({"error": "character_profile must be dict or valid JSON string or canonical string", "received": raw_cp}), 400

    if not scenes or not isinstance(scenes, list):
        return jsonify({"error": "image_descriptions (array) required"}), 400

    # simple background continuity detection
    def extract_bg(s):
        for kw in ["채소 마을","채소마을","마을","정원","주방","숲","바다","교실","초원","집"]:
            if kw in (s or ""):
                return kw
        return None

    first_bg = extract_bg(scenes[0]) or None
    results = [None] * len(scenes)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for i, artist_desc in enumerate(scenes):
            prev_bg = first_bg if i > 0 else None
            futures[executor.submit(generate_image_from_prompt, character, artist_desc, i+1, prev_bg)] = i
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception:
                logging.exception("이미지 생성 작업 실패 for index %s", idx)
                results[idx] = None

    # results contain either data URLs (preferred) or image URLs or None
    return jsonify({"image_urls": results})

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))