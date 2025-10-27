import sys
import os
import re
import json
import time
import random
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI

# ── 환경 ─────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Check .env or environment variables.")

# 로그 출력 고정(표준출력)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mytales")

# OpenAI 클라이언트
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "120"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
STORY_MODEL_PREVIEW = os.getenv("STORY_MODEL_PREVIEW", "gpt-4o-mini")
STORY_MODEL_FULL = os.getenv("STORY_MODEL_FULL", "gpt-4o")
# dall-e-3 is the only valid DALL-E model name
IMAGE_MODEL = "dall-e-3"
SUPPORTED_IMG_SIZES = {"1024x1024", "1792x1024", "1024x1792"}
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1024x1024")
if IMAGE_SIZE not in SUPPORTED_IMG_SIZES:
    IMAGE_SIZE = "1024x1024"

client = OpenAI(api_key=API_KEY, timeout=OPENAI_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)

# ── 앱 ───────────────────────────────────────────────────────────
app = Flask(__name__)
# CORS 설정 - 모든 도메인에서 접근 허용
CORS(app, origins="*", supports_credentials=True)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route("/", methods=["GET", "OPTIONS"])
def root():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return jsonify({"ok": True, "ts": time.time()})

# ── 유틸 ─────────────────────────────────────────────────────────
def clean_text(s: str) -> str:
    return re.sub(r'[\"<>]', '', (s or "")).strip()

def count_self_choice_indicators(text: str) -> int:
    indicators = [
        "한 번","한입","한 입","냄새","손끝","손가락","스스로",
        "직접","시도","골라","골라보다","조심스레","조심히","다시 한 번","다시 한입"
    ]
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

# ── 캐릭터 프로필 ────────────────────────────────────────────────
def generate_character_profile(name: str, age: str, gender: str) -> dict:
    hair = random.choice(["짧은 갈색 곱슬머리", "긴 검은 생머리", "웨이브 밤색 머리"])
    outfit = random.choice(["노란 셔츠와 파란 멜빵", "빨간 물방울무늬 원피스", "초록 후드와 베이지 팬츠"])
    canonical = (
        f"Canonical Visual Descriptor: {hair}; {outfit}; "
        f"round face with soft cheeks; warm brown almond eyes; childlike proportions."
    )
    profile = {
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
    logger.info(f"캐릭터: {profile}")
    return profile

# ── 스토리 생성 ─────────────────────────────────────────────────
def generate_story_text(name: str, age: str, gender: str, topic: str, cost_mode: str = "preview", max_attempts: int = 2):
    model = STORY_MODEL_PREVIEW if cost_mode != "full" else STORY_MODEL_FULL
    temperature = 0.2 if cost_mode == "preview" else 0.35
    max_tokens = 900 if cost_mode == "preview" else 1200

    prompt = f"""
너는 5~9세 어린이를 위한 따뜻하고 리듬감 있는 한국어 동화 작가다.
JSON만 반환:
{{"title":"", "character":"", "chapters":[{{"title":"", "paragraph":"", "illustration":""}}], "ending":""}}

요구:
- 입력: 이름={name}, 나이={age}, 성별={gender}, 훈육주제={topic}
- 구조: 발단→전개→절정→결말 흐름의 5챕터
- 각 챕터 2~4문장, 대사/행동/감각으로 보여주기, 설교 금지
- 의인화된 '훈육 화신'과 조력자 등장
- 각 챕터 1문장 삽화 설명(텍스트/말풍선 금지)
- 정확한 스키마로만 반환
""".strip()

    for attempt in range(max_attempts):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a Korean children's story writer. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            raw = res.choices[0].message.content.strip()
            cleaned = re.sub(r'```(?:json)?', '', raw).strip()
            data = None
            try:
                data = json.loads(cleaned)
            except Exception:
                m = re.search(r'(\{[\s\S]*\})\s*$', cleaned)
                data = json.loads(m.group(1)) if m else None

            if isinstance(data, dict) and isinstance(data.get("chapters"), list) and len(data["chapters"]) >= 5:
                full_text = " ".join([c.get("paragraph", "") for c in data["chapters"]])
                if count_self_choice_indicators(full_text) >= 1:
                    return data
        except Exception as e:
            logger.warning(f"스토리 시도 실패: {e}")
            time.sleep(0.3)

    # fallback
    title = f"{name}의 작은 모험"
    chapters = [
        {"title": "1. 시작", "paragraph": f"{name}은(는) 새로운 접시에 낯설어했어요.", "illustration": "밝은 부엌에서 접시를 바라보는 아이"},
        {"title": "2. 친구 등장", "paragraph": "말하는 당근이 수줍게 인사했어요.", "illustration": "웃는 당근 친구와 아이"},
        {"title": "3. 첫 시도", "paragraph": "아이는 손끝으로 살짝 만져보았어요.", "illustration": "포크를 조심스레 드는 손"},
        {"title": "4. 제안", "paragraph": "호박 요정이 작은 게임을 제안했어요.", "illustration": "호박 요정이 손짓하는 모습"},
        {"title": "5. 선택", "paragraph": "아이의 접시에서 다시 한입의 용기가 났어요.", "illustration": "창가에서 포크를 든 아이"}
    ]
    return {"title": title, "character": f"{name} ({age} {gender})", "chapters": chapters, "ending": "입가에 작은 미소가 번졌어요."}

# ── 장면 묘사 + 이미지 프롬프트 ────────────────────────────────
def describe_scene_kor(scene_text: str, character_profile: dict, scene_index: int, previous_summary: str) -> str:
    try:
        prompt = f"""
이전 내용: {previous_summary}
현재 장면: {scene_text}
캐릭터 외형: {character_profile.get('visual', {}).get('canonical')}

한 문장으로 감정, 행동, 배경, 조명을 포함한 시각 묘사만 작성.
텍스트/말풍선 금지.
""".strip()
        res = client.chat.completions.create(
            model=STORY_MODEL_PREVIEW,
            messages=[
                {"role": "system", "content": "Write concise visual descriptions for Korean children's picture books."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=160,
        )
        return clean_text(res.choices[0].message.content)
    except Exception as e:
        logger.warning(f"묘사 실패: {e}")
        return f"{scene_text[:100]} ... 따뜻한 조명, 수채화 느낌."

def build_image_prompt_kor(scene_sentence: str, character_profile: dict, scene_index: int, previous_meta=None) -> str:
    canonical = character_profile.get('visual', {}).get('canonical') or ""
    style = "부드러운 수채화 스타일; 따뜻한 조명; 아동 친화적 톤; 밝고 순한 색감"
    return (
        f"{canonical} 장면 {scene_index}: {scene_sentence}. "
        f"{style}. 캐릭터 외형(머리/눈/옷/비율) 절대 변경 금지. 텍스트/말풍선 없음."
    )

# ── API: /generate-story ─────────────────────────────────────────
@app.route("/generate-story", methods=["POST", "OPTIONS"])
def api_generate_story():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        data = request.get_json(force=True) or {}
        name = (data.get("name") or "").strip()
        age = (data.get("age") or "").strip()
        gender = (data.get("gender") or "").strip()
        topic = (data.get("topic") or data.get("education_goal") or "").strip()
        cost_mode = (data.get("cost_mode") or "preview").lower()

        if not all([name, age, gender, topic]):
            return jsonify({"error": "name, age, gender, topic 모두 필요"}), 400

        character_profile = generate_character_profile(name, age, gender)
        story_data = generate_story_text(name, age, gender, topic, cost_mode=cost_mode)

        chapters = story_data.get("chapters", [])
        image_descriptions, image_prompts = [], []
        accumulated = ""

        for idx, ch in enumerate(chapters, start=1):
            para = ch.get("paragraph", "")
            prev = accumulated or "이야기 시작"
            desc = describe_scene_kor(para, character_profile, idx, prev)
            prompt = build_image_prompt_kor(desc, character_profile, idx)
            image_descriptions.append(desc)
            image_prompts.append(prompt)
            accumulated += (" " + para) if para else accumulated

        return jsonify({
            "title": story_data.get("title"),
            "character_profile": character_profile,
            "story_paragraphs": [c.get("paragraph", "") for c in chapters],
            "image_descriptions": image_descriptions,
            "image_prompts": image_prompts,
            "ending": story_data.get("ending", ""),
            "cost_mode": cost_mode
        })
    except Exception as e:
        logger.exception("스토리 생성 중 오류")
        return jsonify({"error": "서버 오류 발생", "detail": str(e)}), 500

@app.route("/generate-full", methods=["POST", "OPTIONS"])
def api_generate_full():
    """이미지 포함 전체 스토리 생성 엔드포인트"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        data = request.get_json(force=True) or {}
        name = (data.get("name") or "").strip()
        age = (data.get("age") or "").strip()
        gender = (data.get("gender") or "").strip()
        topic = (data.get("topic") or data.get("education_goal") or "").strip()
        cost_mode = (data.get("cost_mode") or "preview").lower()

        if not all([name, age, gender, topic]):
            return jsonify({"error": "name, age, gender, topic 모두 필요"}), 400

        character_profile = generate_character_profile(name, age, gender)
        story_data = generate_story_text(name, age, gender, topic, cost_mode=cost_mode)

        chapters = story_data.get("chapters", [])
        image_descriptions, image_prompts, image_urls = [], [], []
        accumulated = ""

        for idx, ch in enumerate(chapters, start=1):
            para = ch.get("paragraph", "")
            prev = accumulated or "이야기 시작"
            desc = describe_scene_kor(para, character_profile, idx, prev)
            prompt = build_image_prompt_kor(desc, character_profile, idx)
            image_descriptions.append(desc)
            image_prompts.append(prompt)
            accumulated += (" " + para) if para else accumulated
            
            # 실제 이미지 생성
            try:
                res = client.images.generate(
                    model=IMAGE_MODEL,
                    prompt=prompt,
                    size=IMAGE_SIZE,
                    n=1
                )
                url = res.data[0].url if res and res.data else None
                image_urls.append(url)
                logger.info(f"이미지 {idx} 생성 완료")
            except Exception as e:
                logger.warning(f"이미지 {idx} 생성 실패: {e}")
                image_urls.append(None)

        # Wix가 기대하는 형식으로 변환
        story_chapters = []
        for idx, ch in enumerate(chapters):
            story_chapters.append({
                "title": ch.get("title", f"장면 {idx + 1}"),
                "paragraphs": [ch.get("paragraph", "")],
                "image_url": image_urls[idx] if idx < len(image_urls) else None
            })

        return jsonify({
            "title": story_data.get("title"),
            "character_profile": character_profile,
            "chapters": story_chapters,
            "story_paragraphs": [c.get("paragraph", "") for c in chapters],
            "image_descriptions": image_descriptions,
            "image_prompts": image_prompts,
            "image_urls": image_urls,
            "ending": story_data.get("ending", ""),
            "cost_mode": cost_mode
        })
    except Exception as e:
        logger.exception("스토리 생성 중 오류")
        return jsonify({"error": "서버 오류 발생", "detail": str(e)}), 500

# ── API: /generate-image ─────────────────────────────────────────
@app.route("/generate-image", methods=["POST", "OPTIONS"])
def api_generate_image():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        data = request.get_json(force=True) or {}
        character_profile = ensure_character_profile(data.get("character_profile"))
        scene_description = data.get("image_description") or ""
        scene_index = int(data.get("scene_index") or 1)

        if not character_profile or not scene_description:
            return jsonify({"error": "character_profile 및 image_description 필요"}), 400

        prompt = build_image_prompt_kor(scene_description, character_profile, scene_index)
        logger.info(f"이미지 생성 {scene_index}: {prompt[:140]}...")

        res = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size=IMAGE_SIZE,
            n=1
        )
        url = res.data[0].url if res and res.data else None
        if not url:
            raise ValueError("이미지 응답에 URL 없음")
        return jsonify({"image_url": url, "prompt_used": prompt})
    except Exception as e:
        logger.exception("이미지 생성 실패")
        return jsonify({"error": "이미지 생성 실패", "detail": str(e)}), 500

# ── 헬스/진단 ───────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "story_model_preview": STORY_MODEL_PREVIEW,
        "story_model_full": STORY_MODEL_FULL,
        "image_model": IMAGE_MODEL,
        "image_size": IMAGE_SIZE,
        "timeout": OPENAI_TIMEOUT,
        "retries": OPENAI_MAX_RETRIES
    })

# ── 실행 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
