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
    raise RuntimeError("❌ OPENAI_API_KEY not found")

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

# ─────────────────────────────
# 캐릭터 프로필
# ─────────────────────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face, warm brown eyes, childlike proportions."
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
# 동화 생성 (강화 프롬프트)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic):
    logging.info("🧠 동화 생성 시작 (훈육 동화봇 프롬프트)")
    prompt = f"""
당신은 "훈육 동화봇"입니다. 대상은 5~9세 아동이며 말투는 친근하고 따뜻합니다. 문장은 짧고 리드미컬하며 반복과 리듬감을 살려 쓰세요.
입력: 이름={name}, 나이={age}, 성별={gender}, 주제={topic}

출력 형식(엄격, JSON만 반환):
{{"title":"", "table_of_contents":["","",...], "character":"이름 (나이 성별)", "chapters":[{{"title":"", "paragraphs":["문장1","문장2"], "illustration":"장면 묘사(한 문장)"}} ... 5개], "ending":""}}

요구사항(엄격):
1. 전체 구조: 제목 → 목차(챕터 제목 5개) → 주인공 소개 → 챕터1~5(각 2~3문장, 배열형 paragraphs) → 엔딩(행동으로 암시).
2. 스토리 아크: 발단(문제 인식) → 전개(최소 2회의 시도와 실패/학습) → 절정(중대한 선택) → 결말(행동 변화와 감정의 마무리).
3. 등장: 주인공 + 의인화된 조력자(요정/장난감/동물 등). 조력자는 반드시 '작은 규칙' 또는 '이유' 하나를 제시.
4. 문체: 짧고 간결, 쉬운 단어, 무서운 표현 금지.
5. 교훈: 직접적 문장("~해야 한다") 금지. 행동과 결과로 자연스럽게 암시.
6. 각 챕터의 illustration 필드에는 동화 문장 그대로의 사건·행동·대사 분위기·배경·조명(한 문장)을 포함.
   예: "신비로운 채소 마을 광장에서 수정이 도착하자 브로콜리가 수줍게 다가와 속삭이는 장면, 부드러운 황금빛 조명."
7. 챕터4는 절정(중대한 선택 또는 갈등의 해결)으로 구성.
8. 출력은 오직 JSON 문자열만 반환. 추가 설명이나 코드블록 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role":"system","content":"You are '훈육 동화봇'. Write warm, structured Korean children's picture stories. Output only JSON."},
                {"role":"user","content":prompt.strip()}
            ],
            temperature=0.6,
            max_tokens=1200,
            timeout=60
        )
        raw = res.choices[0].message.content.strip()
        data = safe_json_loads(re.sub(r"```(?:json)?", "", raw))
        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) == 5:
            # ensure illustration fields exist
            for ch in data["chapters"]:
                if "illustration" not in ch or not ch.get("illustration"):
                    ch["illustration"] = ""
            return data
    except Exception:
        logging.exception("❌ 동화 생성 실패 (강화)")
    # fallback minimal structure
    return {
        "title": f"{name}의 작은 모험",
        "table_of_contents": ["반짝이는 시작","새로운 만남","첫 시도","결심의 밤","작은 약속"],
        "character": f"{name} ({age} {gender})",
        "chapters": [
            {"title":"1. 시작","paragraphs":[f"{name}은(는) 새로운 꿈을 꾸었어요.","꿈속 길을 따라 걸었더니 문이 살짝 열렸어요."],"illustration":""},
            {"title":"2. 만남","paragraphs":["문을 지나자 신비한 마을이 있었어요.","그곳에서 이상한 소리가 들려왔어요."],"illustration":""},
            {"title":"3. 시도","paragraphs":[f"{name}은(는) 조심스레 다가가 시도해봤어요.","처음에는 어색했지만 한 번씩 해보았어요."],"illustration":""},
            {"title":"4. 절정","paragraphs":["큰 결심의 순간이 왔어요.","마음속으로 작은 약속을 했어요."],"illustration":""},
            {"title":"5. 결말","paragraphs":["다음 날, 작은 약속을 지켰어요.","마음에 따뜻한 빛이 남았어요."],"illustration":""}
        ],
        "ending":"작은 약속이 큰 변화를 만들었어요."
    }

# ─────────────────────────────
# paragraph에서 illustration 자동 보강
# ─────────────────────────────
def make_illustration_from_paragraph(paragraph, character_profile, default_place=None):
    canonical = character_profile.get("visual", {}).get("canonical", "").strip()
    s = (paragraph or "").strip()
    if not s:
        s = "따뜻한 풍경"
    parts = re.split(r'[。\.!?!]|[,，;；]\s*', s)
    main_piece = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if any(k in p for k in ["속삭", "다가", "도착", "만나", "춤", "노래", "도전", "시도", "결심", "속삭였"]):
            main_piece = p
            break
    if not main_piece:
        main_piece = parts[0] if parts else s
    quote_m = re.search(r'["“”\']([^"\']{1,200})["“”\']', s)
    quote_summary = ""
    if quote_m:
        quote_text = quote_m.group(1).strip()
        if any(w in quote_text for w in ["건강", "활기", "강해", "힘"]):
            quote_summary = "친절하게 권하는 분위기"
        elif any(w in quote_text for w in ["약속", "도와", "도움"]):
            quote_summary = "따뜻하게 약속하는 말투"
        else:
            quote_summary = "속삭이는 말투"
    place = default_place or ""
    for kw in ["마을","정원","주방","숲","바다","교실","채소 마을","채소마을"]:
        if kw in s:
            place = kw if not place else place
            break
    lighting = "부드러운 황금빛 조명"
    place_part = f"{place}에서 " if place else ""
    quote_part = f", {quote_summary}" if quote_summary else ""
    illustration = f"{place_part}{main_piece} 장면{quote_part}, {lighting}."
    full_illustration = f"{canonical}. {illustration}" if canonical else illustration
    return full_illustration

# ─────────────────────────────
# 이미지 생성 (illustration 우선, 배경 연속성 유지)
# ─────────────────────────────
def generate_image_from_prompt(character_profile, scene_illustration, scene_index, previous_background=None):
    canonical = character_profile.get("visual", {}).get("canonical", "")
    bg_hint = f"배경 연속성: 이전 장면과 같은 장소({previous_background})." if previous_background else ""
    prompt = (
        f"{canonical}. {scene_illustration} {bg_hint} "
        "Watercolor children's book illustration; warm soft lighting; pastel palette; mid-shot composition; no text or speech bubbles; non-photorealistic."
    )
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="standard",
            n=1,
            timeout=60
        )
        return res.data[0].url
    except Exception:
        logging.exception("이미지 생성 실패")
        return None

# ─────────────────────────────
# 엔드포인트: /generate-story
# ─────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    age = data.get("age", "").strip()
    gender = data.get("gender", "").strip()
    topic = (data.get("education_goal") or data.get("topic") or "").strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "모든 입력값 필요"}), 400

    character = generate_character_profile(name, age, gender)
    story = generate_story_text(name, age, gender, topic)

    # 보강: illustration이 비어있으면 paragraph 기반으로 생성
    image_descriptions = []
    chapters = story.get("chapters", [])
    for ch in chapters:
        # paragraphs 배열에서 가장 설명적인 문장 선택(끝부분 우선)
        paras = ch.get("paragraphs") or []
        paragraph_text = " ".join(paras) if isinstance(paras, list) else ch.get("paragraph", "")
        ill = (ch.get("illustration") or "").strip()
        if not ill:
            ill = make_illustration_from_paragraph(paragraph_text, character)
            ch["illustration"] = ill
        image_descriptions.append(ch.get("illustration"))

    response = {
        "title": story.get("title"),
        "table_of_contents": story.get("table_of_contents") or [c.get("title","") for c in chapters],
        "character": story.get("character") or f"{name} ({age} {gender})",
        "chapters": chapters,
        "story_paragraphs": [(" ".join(c.get("paragraphs")) if isinstance(c.get("paragraphs"), list) else c.get("paragraph","")) for c in chapters],
        "image_descriptions": image_descriptions,
        "ending": story.get("ending", "")
    }
    logging.info("Generated story and image_descriptions")
    return jsonify(response)

# ─────────────────────────────
# 엔드포인트: /generate-image
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    character = data.get("character_profile") or data.get("character")
    scenes = data.get("image_descriptions") or data.get("scenes") or []
    if not character or not scenes:
        return jsonify({"error": "character_profile 및 image_descriptions 필요"}), 400

    # extract simple background keyword from first scene for continuity
    def extract_bg(s):
        for kw in ["채소 마을","채소마을","마을","정원","주방","숲","바다","교실","초원","집"]:
            if kw in s:
                return kw
        return None

    first_bg = extract_bg(scenes[0]) or None
    urls = [None] * len(scenes)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for i, desc in enumerate(scenes):
            prev_bg = first_bg if i > 0 else None
            futures[executor.submit(generate_image_from_prompt, character, desc, i+1, prev_bg)] = i
        for fut in as_completed(futures):
            idx = futures[fut]
            urls[idx] = fut.result()

    return jsonify({"image_urls": urls})

# ─────────────────────────────
# 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)