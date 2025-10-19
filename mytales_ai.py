from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os, random, re, logging, json, time

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Please check your .env or environment variables.")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────
# 유틸 함수
# ─────────────────────────────
def clean_text(s):
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def count_self_choice_indicators(text):
    indicators = ["한 번", "한입", "한 입", "냄새", "손끝", "손가락", "스스로", "직접", "시도", "골라", "골라보다", "조심스레", "조심히", "다시 한 번", "다시 한입"]
    if not text:
        return 0
    return sum(text.count(ind) for ind in indicators)

def ensure_character_profile(obj):
    if not obj:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        m = re.search(r'Canonical\s*Visual\s*Descriptor\s*[:\-]?\s*(.+)', s, re.IGNORECASE)
        canonical = m.group(1).strip() if m else s
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

# ─────────────────────────────
# 동화 텍스트 생성 (프롬프트만 교체)
# ─────────────────────────────
def generate_story_text(name, age, gender, topic, max_attempts=2):
    prompt = """
당신은 5~9세 어린이를 위한 따뜻하고 리드미컬한 동화 작가입니다. 출력은 엄격한 JSON만 허용합니다:
{"title":"", "character":"", "chapters":[{"title":"", "paragraph":"", "illustration":""}, ...], "ending":""}

요구사항:
1. 입력값을 반영: 이름, 나이, 성별, 훈육주제(예: 편식).
2. 스토리 아크 필수: 발단(문제 인식) → 전개(시도와 실패) → 절정(중대한 선택/위기) → 결말(행동 변화와 결과).
3. 챕터 구성: 총 5장(각 2~4문장). 각 챕터 끝에 삽화 설명 1문장(시각 정보만, 말풍선·텍스트 금지).
4. 등장인물: 의인화된 훈육 화신(예: 당근 요정) + 조력자 필수.
5. 동기 부여: 행동의 '이유'를 명확히 제공(외적 동기와 간단한 원리 또는 상징적 근거).
6. 시도와 학습: 주인공이 스스로 시도하는 장면을 최소 2회 포함; 각 시도는 실패 또는 학습을 포함.
7. 작은 규칙: 각 챕터에 작은 실행 규칙 1개 포함(예: "한 모금만 천천히").
8. 교훈은 직접 서술 금지; 행동과 결과, 감정 변화로 암시.
9. 감각 묘사(시각·후각·촉각) 포함.
10. 언어: 한국어. 스타일: 따뜻하고 간결.
11. 출력 예시 형식에 정확히 맞춰 JSON만 반환.

추가: 챕터4는 절정(중대한 선택)으로 배치하고, 챕터 내 문장 말미에 캐릭터 외형을 한 번 "캐릭터: Canonical Visual Descriptor: ..." 형태로 포함해 이미지 연속성에 도움을 주세요.
""".strip()

    for _ in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are '훈육 동화봇' writing warm Korean discipline stories in JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=1200,
            )
            raw = res.choices[0].message.content.strip() if getattr(res.choices[0].message, 'content', None) else str(res)
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            try:
                data = json.loads(cleaned)
            except Exception:
                # 시도적으로 본문 끝의 JSON 객체 추출
                m = re.search(r'(\{[\s\S]*\})\s*$', cleaned)
                if m:
                    try:
                        data = json.loads(m.group(1))
                    except Exception:
                        data = None
                else:
                    data = None

            if isinstance(data, dict) and isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
                full_text = " ".join([c.get("paragraph","") for c in data["chapters"]])
                if count_self_choice_indicators(full_text) >= 2:
                    return data
        except Exception as e:
            logging.exception("generate_story_text 실패")
            time.sleep(0.5)

    # Fallback (기본 구조)
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": "따뜻한 부엌 창가 장면"},
        {"title": "2. 소리", "paragraph": "딸깍 소리와 함께 음식 친구들이 말을 걸었어요.", "illustration": "말하는 당근과 작은 조명"},
        {"title": "3. 조심스러운 접근", "paragraph": f"{name}은(는) 손끝으로 살짝 만져보았어요.", "illustration": "호기심 어린 손끝 클로즈업"},
        {"title": "4. 조력자의 등장", "paragraph": "호박 요정이 게임을 제안했어요.", "illustration": "작은 호박 요정이 반짝이는 장면"},
        {"title": "5. 귀환", "paragraph": "집으로 돌아와 다시 한입 시도했어요.", "illustration": "창가에서 미소짓는 장면"}
    ]
    return {
        "title": title,
        "character": f"{name} ({age} {gender})",
        "chapters": chapters,
        "ending": "아이의 입가에 작은 미소가 피어났어요."
    }

# ─────────────────────────────
# 장면 묘사 + 이미지 프롬프트 생성 (프롬프트 템플릿 교체)
# ─────────────────────────────
def describe_scene_kor(scene_text, character_profile, scene_index, previous_summary):
    try:
        prompt = f"""
이전 내용: {previous_summary}
현재 장면: {scene_text}
캐릭터 외형: {character_profile.get('visual', {}).get('canonical')}
→ 감정/배경/조명/행동을 포함한 묘사, 한 문장으로. 텍스트/말풍선 없이.
""".strip()
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Write Korean visual descriptions for children's picture books."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.25,
            max_tokens=180,
        )
        return clean_text(res.choices[0].message.content)
    except Exception:
        logging.exception("묘사 실패")
        return clean_text(((scene_text or "")[:120]) + " ... 따뜻한 조명, 수채화 느낌.")

def build_image_prompt_kor(scene_sentence, character_profile, scene_index, previous_meta=None):
    # 교체된 이미지 프롬프트 템플릿 적용
    canonical = character_profile.get('visual', {}).get('canonical') or character_profile.get('style') or ""
    age = character_profile.get("age") or ""
    gender = character_profile.get("gender") or ""
    variant = character_profile.get("variant", {})
    variant_id = variant.get("variant_id") if isinstance(variant, dict) else ""
    seed = variant.get("seed") if isinstance(variant, dict) else ""
    appearance_overrides = variant.get("appearance_overrides") if isinstance(variant, dict) else ""

    overrides_str = ""
    if isinstance(appearance_overrides, dict) and appearance_overrides:
        pairs = []
        for k, v in appearance_overrides.items():
            pairs.append(f"{k}:{v}")
        overrides_str = "; " + ", ".join(pairs)

    meta_prev = f"이전 이미지 메타: {previous_meta}." if previous_meta else ""
    prompt = (
        f"{canonical} {age}세, {gender}. variant_id:{variant_id} seed:{seed}{overrides_str}\n"
        f"장면 인덱스: {scene_index}. 장면 설명: {scene_sentence}.\n"
        f"Constraints:\n"
        f"- 캐릭터 외형(머리/눈/옷/비율)은 절대 변경 금지.\n"
        f"- 일관성 유지: 모든 프롬프트에 동일한 Canonical Visual Descriptor 포함.\n"
        f"- 스타일: 부드러운 수채화; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감.\n"
        f"- 구도: mid-shot 권장; 표정과 포즈는 scene_sentence에서 구체화.\n"
        f"- 금지: 텍스트/말풍선, 과도한 리얼리즘, 과장된 성별 표현.\n"
        f"Render hints: color_palette: pastel greens & warm yellows; camera: mid-shot, eye-level.\n"
        f"{meta_prev}"
    )
    return prompt.strip()

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
        return jsonify({"error": "name, age, gender, topic 모두 필요"}), 400

    character_profile = generate_character_profile(name, age, gender)
    story_data = generate_story_text(name, age, gender, topic)

    chapters = story_data.get("chapters", [])
    if len(chapters) < 5:
        chapters = [
            {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": ""},
            {"title": "2. 소리", "paragraph": "딸깍 소리와 함께 음식 친구들이 말을 걸었어요.", "illustration": ""},
            {"title": "3. 조심스러운 접근", "paragraph": f"{name}은(는) 손끝으로 살짝 만져보았어요.", "illustration": ""},
            {"title": "4. 조력자의 등장", "paragraph": "호박 요정이 게임을 제안했어요.", "illustration": ""},
            {"title": "5. 귀환", "paragraph": "집으로 돌아와 다시 한입 시도했어요.", "illustration": ""}
        ]

    image_descriptions = []
    image_prompts = []
    accumulated = ""
    previous_meta = None

    for idx, ch in enumerate(chapters, start=1):
        para = ch.get("paragraph", "")
        prev = accumulated or "이야기 시작"
        desc = describe_scene_kor(para, character_profile, idx, prev)
        prompt = build_image_prompt_kor(desc, character_profile, idx, previous_meta)
        image_descriptions.append(desc)
        image_prompts.append(prompt)
        accumulated += " " + para
        previous_meta = {"style_tags": "부드러운 수채화; 따뜻한 조명"}

    response = {
        "title": story_data.get("title") or f"{name}의 이야기",
        "character_profile": character_profile,
        "story_paragraphs": [c.get("paragraph", "") for c in chapters],
        "image_descriptions": image_descriptions,
        "image_prompts": image_prompts,
        "ending": story_data.get("ending") or ""
    }
    logging.info("DEBUG /generate-story response summary: %s", json.dumps(response, ensure_ascii=False)[:2000])
    return jsonify(response)

# ─────────────────────────────
# 엔드포인트: /generate-image
# ─────────────────────────────
@app.post("/generate-image")
def generate_image():
    data = request.get_json(force=True)
    raw_cp = data.get("character_profile") or data.get("character") or data.get("characterProfile")
    scene_description = (data.get("image_description") or data.get("scene") or data.get("scene_description") or data.get("scene_sentence") or "")
    scene_index = data.get("scene_index") or data.get("index") or 1
    requested_size = data.get("size")

    character_profile = ensure_character_profile(raw_cp)
    if not character_profile:
        return jsonify({"error":"character_profile은 dict 또는 canonical 문자열이어야 합니다.","received": raw_cp}), 400
    if not scene_description:
        return jsonify({"error":"scene_description(또는 image_description/scene 등) 필수"}), 400

    prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)
    logging.info("DEBUG /generate-image prompt len=%d", len(prompt))

    try:
        res = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="standard",
            n=1
        )
    except Exception as e:
        logging.exception("이미지 생성 API 호출 실패")
        return jsonify({"error":"이미지 생성 API 호출 실패","detail": str(e), "prompt_used": prompt}), 500

    image_url = None
    try:
        if res and getattr(res,"data",None):
            image_url = res.data[0].url
    except Exception:
        logging.exception("이미지 응답 파싱 실패")
        image_url = None

    if not image_url:
        logging.error("이미지 생성 응답에 URL 없음. full response: %s", str(res)[:2000])
        return jsonify({"error":"이미지 생성 실패(응답에 URL 없음)","prompt_used":prompt,"raw_response": str(res)[:2000]}), 500

    return jsonify({"image_url": image_url, "prompt_used": prompt})

# ─────────────────────────────
# 로컬 실행
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)