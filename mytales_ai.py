from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, json, re, random, logging, time
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
            "visual": {"canonical": canonical, "hair": "", "outfit": "", "face": "", "eyes": "", "proportions": ""}
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
        "visual": {"canonical": canonical, "hair": hair, "outfit": outfit, "eyes": "따뜻한 갈색 눈", "proportions": "아이 같은 비율"}
    }

# ─────────────────────────────
# 동화 생성 (훈육 동화봇 + 일러스트레이터 규칙 통합)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    logging.info("🧠 동화 생성 시작 (훈육 동화봇 + 일러스트 일관성 포함)")
    # 강화된 프롬프트: 이야기와 동시에 아티스트용 설명(artist_description) 생성 요구
    prompt = f"""
당신은 '훈육 동화봇'이며 동시에 '부름쌤의 동화 일러스트레이터'입니다.
대상: 5~9세. 말투: 친근하고 따뜻함. 문장은 짧고 리드미컬함.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

출력 형식(엄격, JSON만 반환):
{{"title":"", "table_of_contents":["","",...], "character":"이름 (나이 성별)",
 "chapters":[{{"title":"", "paragraphs":["문장1","문장2"], "illustration":"(story sentence as-is)", "artist_description":"(그림가가 바로 그릴 수 있는 풍부한 시각화 문장)"}}, ... 5개], "ending":""}}

요구사항:
1) 총 5장. 각 챕터의 paragraphs는 2~3문장 배열.
2) 스토리 아크: 발단→시도(2회 이상)→절정(챕터4)→결말.
3) 등장: 주인공 + 의인화된 조력자(조력자는 '작은 규칙' 제시).
4) 교훈을 직접 말하지 말고 행동으로 암시.
5) 각 챕터의 'illustration'은 동화의 원문 문장 그대로 포함.
6) 각 챕터의 'artist_description'은 그림가(부름쌤) 관점에서 즉시 그림으로 옮길 수 있게 다음을 명확히 포함:
   - 캐릭터 외형(머리, 옷, 나이와 성별 힌트)
   - 장면에 꼭 보여야 할 요소(사물·생명체·행동)
   - 배경(장소, 시간대)과 조명
   - 구도 제안(원근, mid-shot/close-up 등) 및 스타일(밝고 따뜻한 수채화 느낌)
   - 연속성 힌트(이번 장면이 이전 장면과 같은 배경이면 "same background" 표기)
   예: "Canonical...; Scene: 신비한 채소 마을 광장에서 수정이(6살 여자, 노란 셔츠, 파란 멜빵)가 서 있고, 초록 브로콜리가 다가와 살며시 속삭이는 모습; mid-shot; warm pastel watercolor; soft golden light; maintain same village background."
7) 만약 사용자의 설명이 모호하면 artist_description을 자동으로 보강하여 시각적 요소를 채워라.
8) 출력은 오직 JSON만. 부가 텍스트 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":"You are a story author and illustrator for children. Output only JSON."},
                      {"role":"user","content":prompt.strip()}],
            temperature=0.6,
            max_tokens=1400,
            timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            # normalize fields
            for ch in data["chapters"]:
                if "paragraphs" not in ch:
                    para = ch.get("paragraph") or ""
                    ch["paragraphs"] = [para] if para else []
                if "illustration" not in ch:
                    ch["illustration"] = " "
                if "artist_description" not in ch or not ch.get("artist_description"):
                    # 보강: paragraph 기반 artist_description 생성
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
# artist_description 자동 보강 (부름쌤 규칙)
# ─────────────────────────────
def make_artist_description_from_paragraph(paragraph, character_profile, default_place=None):
    canonical = ""
    if isinstance(character_profile, dict):
        canonical = character_profile.get("visual", {}).get("canonical", "").strip() or ""
    s = (paragraph or "").strip()
    if not s:
        s = "따뜻한 풍경"
    # 핵심문장 선택
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
    # 대사 요약
    quote_m = re.search(r'["“”\']([^"\']{1,200})["“”\']', s)
    quote_summary = ""
    if quote_m:
        q = quote_m.group(1)
        if any(w in q for w in ["한 입","천천히","재미있는 모양","시도"]):
            quote_summary = "encouraging whispered suggestion"
        else:
            quote_summary = "gentle spoken suggestion"
    # 배경 추출
    place = default_place or ""
    for kw in ["채소 마을","채소마을","마을","정원","주방","숲","바다","교실","초원","집"]:
        if kw in s:
            place = kw
            break
    lighting = "warm pastel golden light"
    # 구도 제안
    composition = "mid-shot" if "속삭" in main or "다가" in main else "mid-shot"
    # assemble in Korean and English-friendly phrasing to help DALL·E
    place_part = f"{place}에서 " if place else ""
    quote_part = f", 분위기: {quote_summary}" if quote_summary else ""
    illustration = f"{place_part}{main} 장면{quote_part}, {lighting}; 구도: {composition}."
    full = f"{canonical}. {illustration}" if canonical else illustration
    # ensure child-friendly style hints
    style_hints = "bright gentle colors; soft watercolor children's book illustration; cute friendly characters; no text; no realistic gore"
    return f"{full} Style: {style_hints}"

# ─────────────────────────────
# 이미지 프롬프트 생성 (artist_description 우선, orientation/no-sketch 강제)
# ─────────────────────────────
def build_image_prompt(character_profile, artist_description, scene_index, previous_background=None, orientation="portrait"):
    cp = ensure_character_profile(character_profile)
    canonical = cp.get("visual", {}).get("canonical", "") if cp else ""
    gender = cp.get("gender") if cp and cp.get("gender") else ""
    age = cp.get("age") if cp and cp.get("age") else ""
    bg_hint = f"Maintain same background: {previous_background}." if previous_background else ""
    orientation_hint = "orientation: portrait" if orientation == "portrait" else "orientation: landscape"
    # forbid sketch/pencil
    avoid = "No pencil/sketch lines; no photorealism; no text or speech bubbles."
    prompt = (
        f"{canonical} gender: {gender}; age: {age}. {artist_description} {bg_hint} {orientation_hint} "
        f"Constraints: {avoid} Render as: soft watercolor children's book illustration; warm soft lighting; pastel palette; mid-shot or close-up as suggested."
    )
    return prompt

# ─────────────────────────────
# 이미지 생성 (병렬)
# ─────────────────────────────
def generate_image_from_prompt(character_profile, artist_description, scene_index, previous_background=None):
    prompt = build_image_prompt(character_profile, artist_description, scene_index, previous_background, orientation="portrait")
    logging.info("이미지 프롬프트: %s", prompt[:400])
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="standard",
            n=1,
            timeout=60
        )
        if res and getattr(res, "data", None):
            return res.data[0].url
        return None
    except Exception:
        logging.exception("이미지 생성 실패")
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
        # try to update previous_bg for continuity
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

    # background continuity from first scene
    def extract_bg(s):
        for kw in ["채소 마을","채소마을","마을","정원","주방","숲","바다","교실","초원","집"]:
            if kw in (s or ""):
                return kw
        return None

    first_bg = extract_bg(scenes[0]) or None
    urls = [None] * len(scenes)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for i, artist_desc in enumerate(scenes):
            prev_bg = first_bg if i > 0 else None
            futures[executor.submit(generate_image_from_prompt, character, artist_desc, i+1, prev_bg)] = i
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                urls[idx] = fut.result()
            except Exception:
                logging.exception("이미지 생성 작업 실패 for index %s", idx)
                urls[idx] = None

    return jsonify({"image_urls": urls})

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))