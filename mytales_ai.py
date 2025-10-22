from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, random, logging, time, base64, requests
from io import BytesIO
from PIL import Image, ExifTags
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
    if not obj:
        return None
    if isinstance(obj, dict):
        visual = obj.get("visual") or {}
        canonical = visual.get("canonical") or obj.get("style") or ""
        if not visual.get("canonical"):
            visual["canonical"] = canonical
            obj["visual"] = visual
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
# 동화 생성 (기승전결 + 판타지적 보상 규칙 강화)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    logging.info("동화 생성 시작 (강화 프롬프트)")
    prompt = f"""
당신은 5~9세 아동을 위한 따뜻한 훈육 동화 작가이며 일러스트레이터 관점에서 artist_description도 생성합니다.
문체: 친근, 짧고 리드미컬. 무섭지 않음.

입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

출력(엄격, JSON만):
{{"title":"", "table_of_contents":["","",...], "character":"이름 (나이 성별)",
 "chapters":[{{"title":"", "paragraphs":["문장1","문장2"], "illustration":"(원문 문장 그대로)", "artist_description":"(일러스트용 풍부한 묘사)"}} ... 5개], "ending":""}}

요구사항:
1) 기승전결(발단→전개(최소 2회 시도 포함)→절정(챕터4)→결말)을 반드시 지켜라.
2) 조력자(요정/장난감/동물 등)를 등장시켜 '작은 규칙' 또는 '재미있는 이유/마법적 보상'을 하나 제시하라.
3) 훈육 주제가 '편식'일 경우: 반드시 '작은 규칙' 제시(예: '한 입만 천천히') 및 주인공이 최소 두 번 시도(첫 시도 실패 포함), 챕터4에서 스스로 규칙을 선택해 행동으로 옮겨야 한다.
4) 결말은 직접적 지시 없이 행동과 결과(칭찬, 자신감, 마법적 암시 등)로 교훈을 암시하라.
5) 각 챕터의 illustration 필드에는 동화 원문 문장 그대로 포함.
6) 각 챕터의 artist_description은 캐릭터 외형, 필수 시각요소(Include clause), 배경, 조명, 구도, 스타일 힌트 포함.
7) 사용자의 입력이 불충분하면 자동으로 안전하고 창의적인 마법적 보상을 제시하라.
8) 출력 외 추가 텍스트 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write warm Korean children's stories for ages 5-9 and produce illustrator-friendly descriptions. Output only JSON."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.6,
            max_tokens=1400,
            timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            for ch in data["chapters"]:
                if "paragraphs" not in ch:
                    para = ch.get("paragraph") or ""
                    ch["paragraphs"] = [para] if para else []
                if "illustration" not in ch:
                    ch["illustration"] = ""
                if "artist_description" not in ch or not ch.get("artist_description"):
                    joined = " ".join(ch["paragraphs"])
                    ch["artist_description"] = make_artist_description_from_paragraph(joined, {"visual": {"canonical": f"Canonical Visual Descriptor: gender: {gender}; age: {age}."}})
            # validation: ensure arc and magical hint
            if not validate_story_structure(data):
                logging.info("생성된 이야기 구조 검증 실패, 재생성 시도")
                # one retry with stricter instruction
                return regenerate_story_with_strict_arc(name, age, gender, topic)
            return data
    except Exception:
        logging.exception("동화 생성 실패")
    return regenerate_story_with_strict_arc(name, age, gender, topic, fallback=True)

def regenerate_story_with_strict_arc(name, age, gender, topic, fallback=False):
    prompt_extra = "Regenerate with a strict 5-chapter arc and include clear magical reward or small rule; ensure chapter4 is climax containing the character's conscious choice."
    prompt = f"{prompt_extra}\nInput: name={name}, age={age}, gender={gender}, topic={topic}"
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":"Write warm Korean children's stories for ages 5-9. Output only JSON."},
                      {"role":"user","content":prompt}],
            temperature=0.6,
            max_tokens=1400,
            timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            for ch in data["chapters"]:
                if "paragraphs" not in ch:
                    para = ch.get("paragraph") or ""
                    ch["paragraphs"] = [para] if para else []
                if "illustration" not in ch:
                    ch["illustration"] = ""
                if "artist_description" not in ch or not ch.get("artist_description"):
                    joined = " ".join(ch["paragraphs"])
                    ch["artist_description"] = make_artist_description_from_paragraph(joined, {"visual": {"canonical": f"Canonical Visual Descriptor: gender: {gender}; age: {age}."}})
            if not validate_story_structure(data) and not fallback:
                return regenerate_story_with_strict_arc(name, age, gender, topic, fallback=True)
            return data
    except Exception:
        logging.exception("재생성 실패")
    # final fallback minimal story
    return {
        "title": f"{name}의 작은 모험",
        "table_of_contents": ["시작","만남","시도","결심","결말"],
        "character": f"{name} ({age} {gender})",
        "chapters": [
            {"title":"1. 시작","paragraphs":[f"{name}은 채소를 싫어했어요.","오늘도 접시에 채소가 남았어요."],"illustration":"","artist_description":""},
            {"title":"2. 만남","paragraphs":["작은 요정이 나타났어요.","요정이 작은 규칙을 알려주었어요."],"illustration":"","artist_description":""},
            {"title":"3. 시도","paragraphs":["한 번 시도해봤지만 어려웠어요.","그래도 포기하지 않았어요."],"illustration":"","artist_description":""},
            {"title":"4. 절정","paragraphs":["결심의 순간, 스스로 선택했어요.","작은 보상이 마음에 불을 지폈어요."],"illustration":"","artist_description":""},
            {"title":"5. 결말","paragraphs":["습관이 조금 생겼어요.","마음이 뿌듯했어요."],"illustration":"","artist_description":""}
        ],
        "ending":"작은 결심이 큰 변화를 만들었어요."
    }

def validate_story_structure(data):
    try:
        chapters = data.get("chapters", [])
        if not isinstance(chapters, list) or len(chapters) != 5:
            return False
        # each chapter paragraphs 2~3
        for ch in chapters:
            paras = ch.get("paragraphs") or []
            if not isinstance(paras, list) or not (1 < len(paras) <= 3):
                return False
        # chapter4 should contain climax keywords
        ch4_text = " ".join(chapters[3].get("paragraphs") or [])
        if not any(k in ch4_text for k in ["결심", "선택", "결정", "마지막 용기", "용기"]):
            return False
        # presence of helper or rule in story
        whole = " ".join([" ".join(c.get("paragraphs") or []) for c in chapters])
        if not any(k in whole for k in ["요정", "규칙", "작은 규칙", "약속", "보상", "마법"]):
            return False
        return True
    except Exception:
        return False

# ─────────────────────────────
# artist_description 생성 및 강화 (Include clause)
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
        if any(k in p for k in ["속삭", "다가", "도착", "만나", "춤", "노래", "도전", "시도", "결심", "제안", "만들", "먹"]):
            main = p
            break
    if not main:
        main = parts[0] if parts else s
    keywords = ["브로콜리","당근","요정","수정","아이","식탁","접시","한 입","속삭"]
    include = [kw for kw in keywords if kw in s]
    if not include:
        include = ["child", "helper", "food"]
    quote_m = re.search(r'["“”\']([^"\']{1,200})["“”\']', s)
    quote_summary = ""
    if quote_m:
        q = quote_m.group(1)
        if any(w in q for w in ["한 입","천천히","재미있는 모양","시도","먹으면"]):
            quote_summary = "따뜻하게 권하는 말투"
        else:
            quote_summary = "부드럽게 권하는 분위기"
    place = default_place or ""
    for kw in ["채소 마을","채소마을","마을","정원","주방","식당","숲","집","교실"]:
        if kw in s:
            place = kw
            break
    lighting = "부드러운 황금빛"
    composition = "mid-shot"
    include_list = ", ".join(include)
    include_clause = f"Include visible elements exactly: {include_list}."
    place_part = f"{place}에서 " if place else ""
    quote_part = f", 분위기: {quote_summary}" if quote_summary else ""
    illustration = f"{place_part}{main} 장면{quote_part}, {lighting}; 구도: {composition}."
    full = f"{canonical}. {illustration}" if canonical else illustration
    style_hints = "밝고 부드러운 색감; 따뜻한 수채화 스타일; 귀엽고 친근한 캐릭터; no text; no pencil/sketch; avoid photorealism"
    return f"{full} {include_clause} Style: {style_hints}"

# ─────────────────────────────
# 이미지 프롬프트 빌드 (orientation, no-sketch 등 강제)
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
# EXIF-aware fetch + upright conversion -> data URL
# ─────────────────────────────
def image_url_to_upright_dataurl(url, target_orientation="portrait", timeout=15):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
        # EXIF orientation handling
        try:
            exif = img._getexif()
            if exif:
                orientation_key = None
                for tag, value in ExifTags.TAGS.items():
                    if value == 'Orientation':
                        orientation_key = tag
                        break
                if orientation_key and orientation_key in exif:
                    orient = exif.get(orientation_key)
                    if orient == 3:
                        img = img.rotate(180, expand=True)
                    elif orient == 6:
                        img = img.rotate(270, expand=True)
                    elif orient == 8:
                        img = img.rotate(90, expand=True)
        except Exception:
            pass
        w, h = img.size
        # enforce portrait orientation
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
        logging.exception("이미지 후처리 실패")
        return None

# ─────────────────────────────
# 이미지 검증 도우미
# ─────────────────────────────
def extract_missing_elements(artist_description):
    m = re.search(r'Include visible elements exactly:\s*([^\.]+)\.', artist_description)
    if not m:
        return []
    items = [it.strip() for it in m.group(1).split(",")]
    return items

def verify_image_contains_elements(dataurl, artist_description):
    try:
        header, b64 = dataurl.split(",", 1)
        img = Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
        img_small = img.resize((100, 100))
        pixels = list(img_small.getdata())
        total = len(pixels)
        greens = 0
        sats = []
        import colorsys
        for r, g, b in pixels:
            h_, s_, v_ = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
            sats.append(s_)
            if g > r and g > b and g > 80:
                greens += 1
        avg_sat = sum(sats)/len(sats) if sats else 0
        green_ratio = greens / total if total else 0
        # sketch detection
        if avg_sat < 0.12:
            return False
        missing = extract_missing_elements(artist_description)
        if any(m in ["브로콜리","당근","토마토"] for m in missing):
            return green_ratio > 0.02
        return True
    except Exception:
        logging.exception("이미지 검증 실패")
        return False

# ─────────────────────────────
# 이미지 생성 with retries + verification
# ─────────────────────────────
def generate_image_from_prompt(character_profile, artist_description, scene_index, previous_background=None, max_retries=2):
    cp = ensure_character_profile(character_profile)
    target_orientation = "portrait"
    prompt_base = build_image_prompt(cp, artist_description, scene_index, previous_background, orientation=target_orientation)
    attempt = 0
    last_dataurl = None

    while attempt <= max_retries:
        attempt += 1
        logging.info("이미지 생성 시도 %s for scene %s", attempt, scene_index)
        try:
            res = client.images.generate(
                model="dall-e-3",
                prompt=prompt_base,
                size="1024x1792",
                quality="standard",
                n=1,
                timeout=60
            )
        except Exception:
            logging.exception("이미지 생성 API 호출 실패")
            res = None

        url = None
        b64 = None
        if res and getattr(res, "data", None):
            candidate = res.data[0]
            url = getattr(candidate, "url", None) or (candidate.get("url") if isinstance(candidate, dict) else None)
            b64 = getattr(candidate, "b64_json", None) or (candidate.get("b64_json") if isinstance(candidate, dict) else None)

        dataurl = None
        if url:
            dataurl = image_url_to_upright_dataurl(url, target_orientation)
        elif b64:
            try:
                img_bytes = base64.b64decode(b64)
                img = Image.open(BytesIO(img_bytes))
                w, h = img.size
                if w > h:
                    img = img.rotate(90, expand=True)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                dataurl = "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")
            except Exception:
                logging.exception("b64 처리 실패")

        if not dataurl:
            prompt_base += " Emphasize inclusion of listed elements; Avoid sketch; Output upright portrait."
            continue

        last_dataurl = dataurl
        if verify_image_contains_elements(dataurl, artist_description):
            return dataurl
        else:
            logging.warning("검증 실패: 핵심 요소 누락 가능, 재시도")
            missing = extract_missing_elements(artist_description)
            if missing:
                prompt_base += " MUST include: " + ", ".join(missing) + "."
            else:
                prompt_base += " Emphasize scene elements and character features."
            # loop retry

    return last_dataurl

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
        for kw in ["채소 마을","채소마을","마을","정원","주방","식당","숲","교실","초원","집"]:
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
    logging.info("생성 완료: story + artist descriptions")
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

    def extract_bg(s):
        for kw in ["채소 마을","채소마을","마을","정원","주방","식당","숲","교실","초원","집"]:
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
                logging.exception("이미지 생성 실패 for index %s", idx)
                results[idx] = None

    return jsonify({"image_urls": results})

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))