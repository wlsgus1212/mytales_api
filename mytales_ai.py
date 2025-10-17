from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

# ──────────────
# 환경 설정
# ──────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ──────────────
# 유틸 함수
# ──────────────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def count_self_choice_indicators(text):
    indicators = ["한 번", "한입", "한 입", "냄새", "손끝", "손가락", "스스로", "직접", "시도", "골라", "골라보다", "조심스레", "조심히", "다시 한 번", "다시 한입"]
    if not text:
        return 0
    lower = text
    return sum(lower.count(ind) for ind in indicators)

def ensure_character_profile(obj):
    """
    입력이 dict이면 그대로 반환.
    문자열이면 JSON 파싱 시도, 실패하면 canonical descriptor로 변환한 dict 반환.
    """
    if not obj:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        # 문자열이 JSON이면 파싱 시도
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # "Canonical Visual Descriptor: ..." 같은 형식에서 값만 추출 시도
        m = re.search(r'Canonical\s*Visual\s*Descriptor\s*[:\-]?\s*(.+)', s, re.IGNORECASE)
        if m:
            canonical = m.group(1).strip()
        else:
            # 전체 문자열을 canonical로 사용
            canonical = s
        # 최소한의 구조로 반환
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
    # 그 외 타입이면 None 반환
    return None

# ──────────────
# 캐릭터 프로필 생성
# ──────────────
def generate_character_profile(name, age, gender):
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
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

# ──────────────
# 동화 텍스트 생성 (간단 예시, 기존 로직 유지)
# ──────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    base_prompt = f"""
당신은 '훈육 동화봇'입니다. 대상은 5~9세 아동이며, 말투는 따뜻하고 리드미컬합니다.
이야기는 의인화된 존재(훈육 주제의 화신)와 조력자가 등장하는 모험 서사로, 주인공이 스스로 여러 번 작은 시도를 통해 변화에 다가가는 형식이어야 합니다.
입력: 이름={name}, 나이={age}, 성별={gender}, 훈육 주제={topic}.

반드시 지킬 사항:
1) 구조: 제목, 목차(5개), 주인공 소개, 챕터1~5, 마무리(행동으로 암시).
2) 각 챕터는 1~3문장. 감정 변화, 감각 묘사 포함.
3) 의인화된 존재 + 조력자 필수.
4) '스스로 시도' 장면 2회 이상 필수.
5) 교훈은 직접 언급 금지 (행동으로 암시).
6) 각 챕터 끝에 삽화 설명 1문장.
7) JSON 형식:
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}},...], "ending":""}}
"""
    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are '훈육 동화봇' writing Korean discipline stories in JSON."},
                    {"role": "user", "content": base_prompt.strip()}
                ],
                temperature=0.6,
                max_tokens=1200,
            )
        except Exception as e:
            logging.exception("LLM 호출 실패")
            time.sleep(0.5)
            continue

        raw = res.choices[0].message.content.strip()
        logging.info("DEBUG generate_story raw: %s", raw[:1000])

        # 안전 파싱 시도
        data = None
        try:
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            data = json.loads(cleaned)
        except Exception:
            match = re.search(r'\{[\s\S]*\}\s*$', raw)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = None

        if data and isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
            paragraph_text = " ".join([c.get("paragraph", "") for c in data["chapters"]])
            if count_self_choice_indicators(paragraph_text) >= 2:
                return data

        logging.info("generate_story validation failed, retrying...")
        time.sleep(0.5)

    # fallback: 간단한 기본 스토리(필요시 더 정교하게 만듬)
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작의 밤", "paragraph": f"{name}은(는) 식탁 앞에서 접시를 바라보며 머뭇거렸어요; 색들이 낯설었거든요.", "illustration": f"램프빛 아래 접시를 바라보는 {name}; canonical 포함."},
        {"title": "2. 오솔길의 초대", "paragraph": f"창밖에서 반짝이던 빛을 따라 {name}은(는) 작은 배낭을 메고 길을 나섰어요.", "illustration": "반짝이는 오솔길과 작은 배낭을 멘 아이."},
        {"title": "3. 의인화된 만남", "paragraph": "말하는 당근들이 냄새를 권유했고, 주인공은 손끝으로 냄새를 맡아보았어요.", "illustration": "웃는 당근들과 손끝으로 냄새를 맡는 장면; canonical 포함."},
        {"title": "4. 조력자의 제안", "paragraph": "지혜로운 호박이 '한 조각만 맛보기' 게임을 권했어요; 주인공은 조심스레 시도하고 다시 한 번 시도했어요.", "illustration": "호박 조력자가 게임을 제안하는 장면; 따뜻한 조명."},
        {"title": "5. 귀환과 암시", "paragraph": "집으로 돌아온 주인공은 부엌에서 포크에 작은 조각을 꽂아 창밖을 바라보았어요; 손끝엔 작은 호기심이 남았어요.", "illustration": "부엌 창가에서 포크에 작은 조각을 꽂은 옆모습; canonical 포함."}
    ]
    return {"title": title, "character": f"{name} ({age} {gender})", "chapters": chapters, "ending": "손끝엔 작은 호기심이 남아 있었어요."}

# ──────────────
# 장면 묘사 및 이미지 프롬프트 생성
# ──────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    prompt = f"""
당신은 어린이 그림책 일러스트 전문가입니다.
- 이전 요약: {previous_summary}
- 현재 장면: {scene_text}
- 캐릭터 외형: {character_profile.get('visual', {}).get('canonical') if isinstance(character_profile, dict) else str(character_profile)}
한 문장으로 감정, 행동, 배경, 조명 또는 카메라 구도 중 최소 2개를 포함하여 시각적으로 묘사하세요. 말풍선/텍스트 금지.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write Korean visual descriptions for children's picture books."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.25,
            max_tokens=180,
        )
        return clean_text(res.choices[0].message.content)
    except Exception:
        logging.exception("describe_scene_kor 호출 실패, fallback 문장 사용")
        # fallback: 간단한 묘사
        return clean_text(f"{scene_text[:120]}... (따뜻한 조명, 부드러운 수채화 느낌)")

def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    canonical = ""
    if isinstance(character_profile, dict):
        canonical = character_profile.get('visual', {}).get('canonical') or character_profile.get('style') or ""
    else:
        canonical = str(character_profile)
    style_tags = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    meta_prev = f"이전 이미지 메타: {previous_meta}." if previous_meta else ""
    prompt = (
        f"{canonical} {meta_prev} 장면 인덱스: {scene_index}. 장면 설명: {scene_sentence}. "
        f"스타일: {style_tags}. 카메라: 중간 샷 권장. 캐릭터의 머리, 옷, 눈 색상과 비율은 절대 변경하지 마세요. 텍스트/말풍선 금지."
    )
    return prompt.strip()

# ──────────────
# 엔드포인트: /generate-story
# ──────────────
@app.post("/generate-story")
def generate_story():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    age = (data.get("age") or "").strip()
    gender = (data.get("gender") or "").strip()
    topic = (data.get("topic") or data.get("education_goal") or "").strip()

    if not all([name, age, gender, topic]):
        return jsonify({"error": "name, age, gender, topic 모두 필요"}), 400

    character_profile = generate_character_profile(name, age, gender)
    story_data = generate_story_text(name, age, gender, topic)

    chapters = story_data.get("chapters", []) or []
    image_descriptions, image_prompts = [], []
    accumulated, previous_meta = "", None

    for idx, chapter in enumerate(chapters, start=1):
        para = chapter.get("paragraph", "")
        prev = accumulated or "이야기 시작"
        desc = describe_scene_kor(para, character_profile, idx, prev)
        prompt = build_image_prompt_kor(desc, character_profile, idx, previous_meta)
        image_descriptions.append(desc)
        image_prompts.append(prompt)
        accumulated += " " + para
        previous_meta = {"style_tags": "부드러운 수채화; 따뜻한 조명"}

    response = {
        "title": story_data.get("title"),
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in chapters],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts,
        "ending": story_data.get("ending") or ""
    }
    logging.info("DEBUG /generate-story response summary: %s", json.dumps(response, ensure_ascii=False)[:2000])
    return jsonify(response)

# ──────────────
# 엔드포인트: /generate-image
# ──────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    raw_cp = data.get("character_profile") or data.get("character") or data.get("characterProfile")
    scene_description = (data.get("image_description") or data.get("scene") or data.get("scene_description") or data.get("scene_sentence") or "")
    scene_index = data.get("scene_index") or data.get("index") or 1

    # 허용: character_profile가 dict이거나 문자열 canonical인 경우 처리
    character_profile = ensure_character_profile(raw_cp)
    if not character_profile:
        return jsonify({"error": "character_profile은 dict 또는 canonical 문자열이어야 합니다.", "received": raw_cp}), 400

    if not scene_description:
        return jsonify({"error": "scene_description (image_description/scene 등) 필수"}), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)
    logging.info("DEBUG /generate-image prompt len=%d", len(prompt))

    # 이미지 해상도를 512로 낮추어 리소스 사용량 완화 (필요시 1024로 변경)
    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="512x512",
            quality="standard",
            n=1
        )
        image_url = None
        if res and getattr(res, "data", None):
            # 안전: 데이터 구조 확인
            try:
                image_url = res.data[0].url
            except Exception:
                logging.exception("이미지 응답 구조 파싱 실패")
                image_url = None
        if not image_url:
            logging.error("이미지 생성 응답에 URL 없음. full response: %s", str(res)[:1000])
            return jsonify({"error": "이미지 생성 실패(응답에 URL 없음)", "prompt_used": prompt}), 500
    except Exception as e:
        logging.exception("이미지 생성 API 호출 실패")
        return jsonify({"error": "이미지 생성 API 호출 실패", "detail": str(e), "prompt_used": prompt}), 500

    return jsonify({"image_url": image_url, "prompt_used": prompt})

# ──────────────
# 앱 실행
# ──────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)