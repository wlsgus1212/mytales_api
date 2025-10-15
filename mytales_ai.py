from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

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
logging.basicConfig(level=logging.INFO)

# ───────────────────────────────
# 유틸
# ───────────────────────────────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def split_sentences_kor(text, expected=5):
    parts = [p.strip() for p in re.split(r'\n+|(?<=\.)\s+|(?<=\?|!)\s+', text) if p.strip()]
    if len(parts) < expected:
        joined = " ".join(parts)
        parts = [joined] if joined else []
    return parts

def count_self_choice_indicators(text):
    if not text:
        return 0
    indicators = ["한 번", "한입", "한 입", "냄새", "손끝", "손가락", "스스로", "직접", "시도", "골라", "골라보다", "조심스레", "조심히", "다시 한 번", "다시 한입"]
    lower = text
    cnt = sum(lower.count(ind) for ind in indicators)
    return cnt

# ───────────────────────────────
# 캐릭터 프로필 생성 (canonical 고정자 포함)
# ───────────────────────────────
def generate_character_profile(name, age, gender):
    hair_options = ["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"]
    outfit_options = ["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"]
    hair = random.choice(hair_options)
    outfit = random.choice(outfit_options)
    canonical = f"Canonical Visual Descriptor: {hair}; {outfit}; round face with soft cheeks; warm brown almond eyes; childlike proportions."

    return {
        "name": name,
        "age": age,
        "gender": gender,
        "style": f"{hair}, 착용: {outfit}",
        "visual": {
            "canonical": canonical,
            "hair": hair,
            "outfit": outfit,
            "face": "부드러운 볼의 둥근 얼굴",
            "eyes": "따뜻한 갈색 아몬드형 눈",
            "proportions": "아이 같은 비율"
        }
    }

# ───────────────────────────────
# 스토리 생성 (훈육: 의인화 + 조력자 + 단계적 시도 + 암시적 결말)
# ───────────────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    base_prompt = f"""
당신은 '훈육 동화봇'입니다. 대상은 5~9세 아동이며, 말투는 따뜻하고 리드미컬합니다.
이야기는 의인화된 존재(훈육 주제의 화신)와 조력자가 등장하는 모험 서사로, 주인공이 스스로 여러 번 작은 시도를 통해 변화에 다가가는 형식이어야 합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 훈육 주제={topic}.

반드시 지킬 사항:
1) 구조: 제목, 목차(5개), 주인공 소개, 챕터1~5(도입, 모험 출발, 갈등/시험(의인화 존재 등장), 조력자 등장/실험 제안, 여러 번의 작은 시도와 부분적 성공·실수, 귀환/암시적 결말), 마무리(행동으로 암시).
2) 각 챕터은 1~3문장. 감정 변화와 감각적 디테일(맛·냄새·소리·질감 등)을 포함.
3) 의인화된 존재(문제의 화신)와 조력자(놀이·실험 제안)를 반드시 등장시킬 것.
4) 주인공의 '스스로 선택하고 시도하는 장면'을 최소 2회 이상 넣을 것(예: 냄새 맡기, 한 조각만 시도하기, 손끝으로 만져보기, 다시 시도하기 등).
5) 교훈은 직접적으로 쓰지 말고 행동 변화로 암시(예: 다음 날 주인공이 스스로 작은 조각을 집는다).
6) 각 챕터 끝에 삽화 설명(한 문장)을 포함. 삽화 설명에는 캐릭터 canonical descriptor나 시각적 단서 포함.
7) 출력은 엄격한 JSON으로만 반환: 
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}},...], "ending":""}}

예시 톤: 부드럽고 모험적, 은유와 놀이를 사용.
"""
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are '훈육 동화봇', write warm Korean discipline stories for children aged 5-9 following strict JSON output rules."},
                {"role": "user", "content": base_prompt.strip()}
            ],
            temperature=0.6,
            max_tokens=1200,
        )
        raw = res.choices[0].message.content.strip()
        logging.info("DEBUG generate_story raw (trunc): %s", raw[:800])

        # 안전 파싱 시도
        try:
            cleaned = re.sub(r"```(?:json)?", "", raw).strip()
            data = json.loads(cleaned)
        except Exception:
            match = re.search(r'\{[\s\S]*\}\s*$', raw)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = None
            else:
                data = None

        # fallback construction if parsing failed: try to extract paragraphs and enforce structure
        if not data:
            title_match = re.search(r'제목[:\s]*([^\n]+)', raw)
            title = title_match.group(1).strip() if title_match else f"{name}의 이야기"
            paras = split_sentences_kor(raw, expected=5)
            chapters = []
            for i, p in enumerate(paras[:5], start=1):
                chapters.append({"title": f"장면 {i}", "paragraph": clean_text(p), "illustration": ""})
            data = {"title": title, "character": f"{name} ({age} {gender})", "chapters": chapters, "ending": ""}

        # Validate: chapters length and self-choice indicator count
        chapters = data.get("chapters", [])
        joined_paragraphs = " ".join(ch.get("paragraph", "") for ch in chapters)
        choice_count = count_self_choice_indicators(joined_paragraphs)
        if len(chapters) >= 5 and choice_count >= 2:
            return data
        # if not valid, retry once more (loop)
        logging.info("Story validation failed (chapters=%d, choice_count=%d). Retrying...", len(chapters), choice_count)
        time.sleep(0.5)

    # final fallback: construct a compliant story programmatically ensuring 2 self-choice events
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작의 밤", "paragraph": f"{name}은(는) 식탁 앞에서 접시를 바라보며 머뭇거렸어요; 색들이 낯설었거든요.", "illustration": f"램프빛 아래 접시를 바라보는 {name}, canonical: short curly brown hair; yellow shirt and blue overalls."},
        {"title": "2. 등불과 초대", "paragraph": f"창밖에서 반짝이던 등불이 길을 만들자 {name}은(는) 배낭을 메고 따라갔어요.", "illustration": f"{name}이 작은 배낭을 메고 반짝이는 오솔길을 걷는 모습."},
        {"title": "3. 의인화된 만남", "paragraph": f"당근 마을의 작은 당근들이 '냄새를 맡아봐'라며 장난을 쳤고, {name}은(는) 손끝으로 냄새를 맡아보았어요.", "illustration": f"웃는 당근들과 {name}이 손끝으로 냄새를 맡는 장면; canonical 포함."},
        {"title": "4. 조력자의 놀이 제안", "paragraph": f"지혜로운 호박 조력자가 '한 조각만 맛보기 게임'을 제안했고, {name}은(는) 조심스레 한 입을 댔다가 다시 시도해보았어요.", "illustration": f"호박 모자가 달린 조력자가 게임을 제안하는 장면; 따뜻한 조명."},
        {"title": "5. 귀환과 암시", "paragraph": f"집으로 돌아온 {name}은(는) 부엌에서 포크에 작은 조각을 꽂아 창밖을 보았어요; 손끝엔 작은 호기심이 남았어요.", "illustration": f"부엌 창가에서 포크에 작은 조각을 꽂은 {name}의 옆모습; canonial 포함."}
    ]
    return {"title": title, "character": f"{name} ({age} {gender})", "chapters": chapters, "ending": "손끝엔 작은 호기심이 남아 있었어요."}

# ───────────────────────────────
# 장면 묘사 생성 (서버가 항상 생성)
# ───────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    prompt = f"""
당신은 어린이 그림책 일러스트 전문가입니다.
- 이전 요약: {previous_summary}
- 현재 장면(원문): {scene_text}
- 캐릭터 고정 외형: {character_profile['visual']['canonical']}
이 장면을 1개의 한국어 문장으로 시각적으로 구체하게 묘사하세요.
한 문장에 감정, 행동, 배경, 조명 또는 카메라 구도 중 최소 두 가지를 포함하세요. 말풍선/텍스트 금지.
"""
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You write concise Korean visual descriptions for children's picture book illustrations."},
            {"role": "user", "content": prompt.strip()}
        ],
        temperature=0.25,
        max_tokens=200,
    )
    return clean_text(res.choices[0].message.content)

# ───────────────────────────────
# 이미지 프롬프트 구성 (canonical 고정, 이전 메타 포함)
# ───────────────────────────────
def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    canonical = character_profile['visual']['canonical']
    style_tags = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    meta_prev = f"이전 이미지 메타: {previous_meta}." if previous_meta else ""
    prompt = (
        f"{canonical} {meta_prev} 장면 인덱스: {scene_index}. 장면 설명: {scene_sentence}. "
        f"스타일: {style_tags}. 카메라: 중간 샷 권장. 캐릭터의 머리, 옷, 눈 색상과 비율은 절대 변경하지 마세요. 텍스트/말풍선 금지."
    )
    return prompt

# ───────────────────────────────
# 이미지 생성 및 검증(간단 텍스트 체크 기반 재시도)
# ───────────────────────────────
def generate_image_with_retry(prompt, max_retries=2, retry_delay=1.0):
    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        logging.info("이미지 생성 시도 %d", attempt)
        try:
            res = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            image_url = res.data[0].url if res and getattr(res, "data", None) else None
        except Exception as e:
            logging.exception("이미지 생성 API 호출 실패")
            image_url = None

        # 간단 검증: canonical의 핵심 단어 포함 여부 확인
        prompt_lower = (prompt or "").lower()
        ok_checks = ("short curly brown hair".lower() in prompt_lower) or ("짧은 갈색 곱슬머리".lower() in prompt_lower)
        if image_url and ok_checks:
            return image_url, attempt
        if attempt <= max_retries:
            time.sleep(retry_delay)
            continue
        return image_url, attempt

# ───────────────────────────────
# 엔드포인트: /generate-story (서버가 이미지까지 생성)
# ───────────────────────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    age = (data.get("age") or "").strip()
    gender = (data.get("gender") or "").strip()
    topic = (data.get("topic") or data.get("education_goal") or "").strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic(또는 education_goal)을 모두 입력하세요."}), 400

    character_profile = generate_character_profile(name, age, gender)
    story_data = generate_story_text(name, age, gender, topic)

    chapters = story_data.get("chapters") or []
    if not chapters:
        paras = story_data.get("story_paragraphs") or split_sentences_kor(story_data.get("raw_story_text", "") or "", expected=5)
        chapters = []
        for i, p in enumerate(paras[:5], start=1):
            chapters.append({"title": f"장면 {i}", "paragraph": clean_text(p), "illustration": ""})

    image_descriptions = []
    image_prompts = []
    image_urls = []
    prompt_used = []
    accumulated = ""
    previous_meta = None

    for idx, chapter in enumerate(chapters, start=1):
        para = chapter.get("paragraph", "")
        prev = accumulated if accumulated else "이야기 시작"
        desc = describe_scene_kor(para, character_profile, idx, prev)
        image_descriptions.append(desc)
        prompt = build_image_prompt_kor(desc, character_profile, idx, previous_meta=previous_meta)
        image_prompts.append(prompt)

        image_url, attempts = generate_image_with_retry(prompt, max_retries=2, retry_delay=1.0)
        prompt_used.append({"prompt": prompt, "attempts": attempts})
        image_urls.append(image_url)

        previous_meta = {"style_tags": "부드러운 수채화; 따뜻한 조명", "palette": "따뜻한 노랑-차분한 파랑"}
        accumulated = (accumulated + " " + para).strip()

    response = {
        "title": story_data.get("title") or f"{name}의 이야기",
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in chapters],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts,
        "image_urls": image_urls,
        "prompt_used": prompt_used,
        "ending": story_data.get("ending") or ""
    }
    logging.info("DEBUG /generate-story final response summary: %s", json.dumps(response, ensure_ascii=False)[:2000])
    return jsonify(response)

# ───────────────────────────────
# 엔드포인트: /generate-image (개별 이미지 생성 허용)
# ───────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    logging.info("DEBUG /generate-image payload: %s", data)

    character_profile = data.get("character_profile") or data.get("characterProfile") or data.get("character")
    scene_description = (data.get("image_description") or data.get("imageDescription") or
                         data.get("scene_sentence") or data.get("sceneSentence") or data.get("scene") or
                         data.get("paragraph") or "")
    scene_index = data.get("scene_index") or data.get("index") or 1

    if not character_profile or not scene_description:
        return jsonify({
            "error": "character_profile과 scene_description 필드는 필수입니다.",
            "received": {
                "character_profile": bool(character_profile),
                "scene_description": bool(scene_description),
                "raw_payload": data
            }
        }), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)
    logging.info("DEBUG single image prompt len=%d", len(prompt))

    image_url, attempts = generate_image_with_retry(prompt, max_retries=2, retry_delay=1.0)
    if not image_url:
        return jsonify({"error": "이미지 생성 실패", "prompt_used": prompt, "attempts": attempts}), 500

    return jsonify({"image_url": image_url, "prompt_used": prompt, "attempts": attempts})

# ───────────────────────────────
# 앱 실행
# ───────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)