# mytales_full.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, random, logging, time, base64, requests
from io import BytesIO
from PIL import Image, ExifTags
from concurrent.futures import ThreadPoolExecutor, as_completed, wait

# ─────────────────────────────
# 환경 및 클라이언트
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found")
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")

# ─────────────────────────────
# 설정값
# ─────────────────────────────
GLOBAL_TOTAL_TIMEOUT = int(os.getenv("GLOBAL_TOTAL_TIMEOUT", "120"))  # 전체 요청 제한 (초)
PER_IMAGE_TIMEOUT = int(os.getenv("PER_IMAGE_TIMEOUT", "45"))         # 이미지 API 타임아웃 (초)
MAX_IMAGE_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "2"))          # 장면당 재시도 수
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "3"))                      # 병렬 작업 수
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1024x1792")                     # portrait 크기

# ─────────────────────────────
# 유틸
# ─────────────────────────────
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
        return {"name": None, "age": None, "gender": None, "style": canonical,
                "visual": {"canonical": canonical, "hair": "", "outfit": "", "face": "", "eyes": "", "proportions": ""}}
    return None

def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face; warm brown eyes; childlike proportions; gender: {gender}; age: {age}."
    return {"name": name, "age": age, "gender": gender, "style": f"{hair}, 착용: {outfit}",
            "visual": {"canonical": canonical, "hair": hair, "outfit": outfit, "eyes": "따뜻한 갈색 눈", "proportions": "아이 같은 비율"}}

# ─────────────────────────────
# 스토리 생성 (기승전결 + 판타지 보상 규칙)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    prompt = f"""
당신은 5~9세 아동을 위한 따뜻한 훈육 동화 작가이며 일러스트레이터 관점에서 artist_description도 생성합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

출력(엄격, JSON만):
{{"title":"", "table_of_contents":["","",...], "character":"이름 (나이 성별)",
 "chapters":[{{"title":"", "paragraphs":["문장1","문장2"], "illustration":"(원문 문장 그대로)", "artist_description":"(일러스트용 묘사)"}} ... 5개], "ending":""}}

요구사항:
1) 5장(발단→전개(최소 2회 시도 포함)→절정(챕터4)→결말).
2) 조력자는 '작은 규칙' 또는 '마법적 보상' 하나를 제시.
3) '편식' 주제일 경우: 규칙 제시 + 최소 두 번 시도(첫 시도 실패 포함) + 챕터4에서 스스로 규칙 선택.
4) 결말은 행동의 결과로 교훈을 암시(직접 지시 금지).
5) 각 챕터에 illustration(원문 문장) 포함 및 artist_description(캐릭터 외형, 필수 시각요소 Include clause, 배경, 조명, 구도, 스타일).
6) 출력 외 텍스트 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":"Write warm Korean children's stories for ages 5-9 and output only JSON."},
                      {"role":"user","content":prompt}],
            temperature=0.6, max_tokens=1400, timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            for ch in data["chapters"]:
                if "paragraphs" not in ch:
                    ch["paragraphs"] = [ch.get("paragraph") or ""]
                if "illustration" not in ch:
                    ch["illustration"] = " ".join(ch.get("paragraphs") or [])
                if "artist_description" not in ch:
                    ch["artist_description"] = make_artist_description_from_paragraph(" ".join(ch.get("paragraphs") or []), {"visual": {"canonical": f"Canonical Visual Descriptor: gender: {gender}; age: {age}."}})
            if validate_story_structure(data):
                return data
    except Exception:
        logging.exception("generate_story_text failed")
    return regenerate_story_with_strict_arc(name, age, gender, topic)

def regenerate_story_with_strict_arc(name, age, gender, topic, fallback=False):
    prompt_extra = "Regenerate with a strict 5-chapter arc and include clear magical reward or small rule; ensure chapter4 is climax containing the character's conscious choice."
    prompt = f"{prompt_extra}\nInput: name={name}, age={age}, gender={gender}, topic={topic}"
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":"Write warm Korean children's stories for ages 5-9. Output only JSON."},
                      {"role":"user","content":prompt}],
            temperature=0.6, max_tokens=1400, timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            for ch in data["chapters"]:
                if "paragraphs" not in ch:
                    ch["paragraphs"] = [ch.get("paragraph") or ""]
                if "illustration" not in ch:
                    ch["illustration"] = " ".join(ch.get("paragraphs") or [])
                if "artist_description" not in ch:
                    ch["artist_description"] = make_artist_description_from_paragraph(" ".join(ch.get("paragraphs") or []), {"visual": {"canonical": f"Canonical Visual Descriptor: gender: {gender}; age: {age}."}})
            if validate_story_structure(data) or fallback:
                return data
    except Exception:
        logging.exception("regenerate_story_with_strict_arc failed")
    # final minimal fallback
    return {
        "title": f"{name}의 작은 모험",
        "table_of_contents": ["시작","만남","시도","절정","결말"],
        "character": f"{name} ({age} {gender})",
        "chapters": [
            {"title":"1. 시작", "paragraphs":[f"{name}은 채소를 싫어했어요.","오늘도 접시에 채소가 남았어요."], "illustration":"", "artist_description":""},
            {"title":"2. 만남", "paragraphs":["작은 요정이 나타났어요.","요정이 작은 규칙을 알려주었어요."], "illustration":"", "artist_description":""},
            {"title":"3. 시도", "paragraphs":["한 번 시도했지만 어려웠어요.","그래도 포기하지 않았어요."], "illustration":"", "artist_description":""},
            {"title":"4. 절정", "paragraphs":["결심의 순간, 스스로 선택했어요.","작은 보상이 마음에 불을 지폈어요."], "illustration":"", "artist_description":""},
            {"title":"5. 결말", "paragraphs":["습관이 조금 생겼어요.","마음이 뿌듯했어요."], "illustration":"", "artist_description":""}
        ],
        "ending":"작은 결심이 큰 변화를 만들었어요."
    }

def validate_story_structure(data):
    try:
        chapters = data.get("chapters", [])
        if not isinstance(chapters, list) or len(chapters) != 5:
            return False
        for ch in chapters:
            paras = ch.get("paragraphs") or []
            if not isinstance(paras, list) or not (1 < len(paras) <= 3):
                return False
        ch4_text = " ".join(chapters[3].get("paragraphs") or [])
        if not any(k in ch4_text for k in ["결심", "선택", "결정", "마지막 용기", "용기"]):
            return False
        whole = " ".join([" ".join(c.get("paragraphs") or []) for c in chapters])
        if not any(k in whole for k in ["요정", "규칙", "작은 규칙", "약속", "보상", "마법"]):
            return False
        return True
    except Exception:
        return False

# ─────────────────────────────
# artist_description 생성
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
# 이미지 프롬프트 빌드
# ─────────────────────────────
def build_image_prompt(character_profile, artist_description, previous_background=None, orientation="portrait"):
    cp = ensure_character_profile(character_profile)
    canonical = cp.get("visual", {}).get("canonical", "") if cp else ""
    gender = cp.get("gender") if cp else ""
    age = cp.get("age") if cp else ""
    bg_hint = f"Maintain same background: {previous_background}." if previous_background else ""
    orientation_hint = "orientation: portrait; vertical composition; height > width; output upright orientation"
    avoid = "No pencil/sketch lines; no photorealism; no text or speech bubbles; no rough sketch artifacts."
    prompt = (f"{canonical} gender: {gender}; age: {age}. {artist_description} {bg_hint} {orientation_hint} "
              f"Constraints: {avoid} Render as: soft watercolor children's book illustration; warm soft lighting; pastel palette; mid-shot or close-up as suggested.")
    return prompt

# ─────────────────────────────
# EXIF-aware fetch + upright conversion -> data URL
# ─────────────────────────────
def image_url_to_upright_dataurl(url, target_orientation="portrait", timeout=15):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
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
        logging.exception("image_url_to_upright_dataurl failed")
        return None

# ─────────────────────────────
# 단순 검증: 색/채도/초록 비율 및 스케치 여부
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
        if avg_sat < 0.12:
            return False
        missing = extract_missing_elements(artist_description)
        if any(m in ["브로콜리","당근","토마토"] for m in missing):
            return green_ratio > 0.02
        return True
    except Exception:
        logging.exception("verify_image_contains_elements failed")
        return False

# ─────────────────────────────
# 이미지 생성 with retries + verification
# ─────────────────────────────
def generate_single_image(character_profile, artist_description, previous_background=None, max_retries=MAX_IMAGE_RETRIES):
    prompt_base = build_image_prompt(character_profile, artist_description, previous_background, orientation="portrait")
    attempt = 0
    last_dataurl = None
    while attempt <= max_retries:
        attempt += 1
        logging.info("Image attempt %s (max %s)", attempt, max_retries)
        try:
            res = client.images.generate(model="dall-e-3", prompt=prompt_base, size=IMAGE_SIZE, quality="standard", n=1, timeout=PER_IMAGE_TIMEOUT)
        except Exception:
            logging.exception("Image API call failed on attempt %s", attempt)
            res = None
        url = None
        b64 = None
        if res and getattr(res, "data", None):
            candidate = res.data[0]
            url = getattr(candidate, "url", None) or (candidate.get("url") if isinstance(candidate, dict) else None)
            b64 = getattr(candidate, "b64_json", None) or (candidate.get("b64_json") if isinstance(candidate, dict) else None)
        dataurl = None
        if url:
            dataurl = image_url_to_upright_dataurl(url, target_orientation="portrait", timeout=15)
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
                logging.exception("b64 processing failed")
        if not dataurl:
            prompt_base += " Emphasize inclusion of listed elements; Avoid sketch; Output upright portrait."
            continue
        last_dataurl = dataurl
        if verify_image_contains_elements(dataurl, artist_description):
            return {"dataurl": dataurl, "attempts": attempt, "ok": True}
        else:
            logging.warning("Verification failed on attempt %s", attempt)
            missing = extract_missing_elements(artist_description)
            if missing:
                prompt_base += " MUST include: " + ", ".join(missing) + "."
            else:
                prompt_base += " Emphasize scene elements and character features."
    return {"dataurl": last_dataurl, "attempts": attempt, "ok": False}

# ─────────────────────────────
# /generate-full 엔드포인트
# ─────────────────────────────
@app.post("/generate-full")
def generate_full():
    start_time = time.time()
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    age = (payload.get("age") or "").strip()
    gender = (payload.get("gender") or "").strip()
    topic = (payload.get("topic") or "").strip()
    generate_images = payload.get("generate_images", True)
    max_image_retries = int(payload.get("max_image_retries", MAX_IMAGE_RETRIES))

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic required"}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)

    chapters = story.get("chapters", []) or []
    previous_bg = None
    scenes = []
    for ch in chapters:
        paras = ch.get("paragraphs") or []
        para_text = " ".join(paras) if isinstance(paras, list) else (ch.get("paragraph") or "")
        if not ch.get("illustration"):
            ch["illustration"] = para_text
        if not ch.get("artist_description"):
            ch["artist_description"] = make_artist_description_from_paragraph(para_text, character, previous_bg)
        for kw in ["채소 마을","마을","정원","주방","식당","숲","교실","집","초원"]:
            if kw in para_text:
                previous_bg = kw
                break
        scenes.append({"artist_description": ch["artist_description"], "prev_bg": previous_bg})

    response_chapters = []
    image_results = [None] * len(scenes)
    warnings = []
    metrics = {"image_attempts": [], "total_images": 0, "successful_images": 0, "generation_time": 0.0}

    if generate_images:
        total_timeout = GLOBAL_TOTAL_TIMEOUT
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(generate_single_image, character, sc["artist_description"], sc["prev_bg"], max_image_retries): idx for idx, sc in enumerate(scenes)}
            try:
                done, not_done = wait(futures.keys(), timeout=total_timeout)
            except Exception:
                done = set()
                not_done = set(futures.keys())
            for fut in done:
                idx = futures[fut]
                try:
                    res = fut.result(timeout=1)
                    image_results[idx] = res
                    metrics["image_attempts"].append(res.get("attempts", 0))
                except Exception:
                    logging.exception("Future result error for index %s", idx)
                    image_results[idx] = None
                    metrics["image_attempts"].append(0)
            for fut in not_done:
                idx = futures[fut]
                fut.cancel()
                image_results[idx] = None
                metrics["image_attempts"].append(0)
                warnings.append(f"Image generation timed out for scene {idx+1}")

    for i, ch in enumerate(chapters):
        img_info = image_results[i] if i < len(image_results) else None
        img_dataurl = img_info["dataurl"] if img_info and isinstance(img_info, dict) else None
        ok = img_info.get("ok") if img_info and isinstance(img_info, dict) else False
        attempts = img_info.get("attempts") if img_info and isinstance(img_info, dict) else 0
        if img_dataurl:
            metrics["total_images"] += 1
            if ok:
                metrics["successful_images"] += 1
        response_chapters.append({
            "title": ch.get("title"),
            "paragraphs": ch.get("paragraphs"),
            "illustration": ch.get("illustration"),
            "artist_description": ch.get("artist_description"),
            "image": img_dataurl,
            "image_ok": ok,
            "image_attempts": attempts
        })
    metrics["generation_time"] = time.time() - start_time

    final = {
        "title": story.get("title"),
        "table_of_contents": story.get("table_of_contents"),
        "character_profile": character,
        "chapters": response_chapters,
        "ending": story.get("ending"),
        "warnings": warnings,
        "metrics": metrics,
        "artist_question": "스토리의 흐름에 맞게 추가 수정할까요?"
    }
    return jsonify(final)

# ─────────────────────────────
# 헬스체크
# ─────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status":"ok", "time": time.time()})

# ─────────────────────────────
# 실행용
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))