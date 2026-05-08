# 스테이블코인 데일리 뉴스레터

매일 아침 07:00 KST에 한국 스테이블코인 관련 뉴스를 모아 이메일로 발송하는 자동화 파이프라인.

## 구조

```
stablecoin_news/
├── main.py                     # 메인 파이프라인
├── verify_sources.py           # RSS URL 검증 스크립트
├── sources.yaml                # 뉴스 소스 카탈로그
├── subscribers.yaml            # 구독자 명단
├── models.py                   # Article 데이터 클래스
├── collectors/                 # 수집기
│   ├── rss.py                  # 일반 RSS
│   ├── google_news.py          # 구글 뉴스 검색 RSS
│   └── naver.py                # 네이버 뉴스 검색 API
├── processors/                 # 처리기
│   ├── relevance.py            # 키워드 관련성 필터
│   ├── dedupe.py               # URL 정규화 + 중복 제거
│   └── llm.py                  # Claude 분류·요약
├── senders/
│   └── email.py                # Resend API 발송
├── templates/
│   └── daily.html              # 이메일 HTML 템플릿
├── data/
│   └── sent_urls.json          # 발송 이력 (자동 갱신·커밋)
└── .github/workflows/
    ├── daily.yml               # 매일 07:00 KST 발송
    └── verify.yml              # 매주 일 03:00 KST RSS 재검증
```

## 초기 설정

### 1. 로컬에서 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. RSS 소스 검증

`sources.yaml`의 `direct_rss`와 `regulators` URL이 실제 살아있는지 확인:

```bash
python verify_sources.py
```

각 소스에 `verified: true/false`가 자동 기록됨. 실패한 URL은 수동으로 올바른 RSS 주소 찾아 수정 후 재실행.

### 3. API 키 발급

| 서비스 | 용도 | 발급처 |
|---|---|---|
| Anthropic | Claude Haiku (분류·요약) | console.anthropic.com |
| Naver Developers | 뉴스 검색 API (선택) | developers.naver.com |
| Resend | 이메일 발송 | resend.com |

Resend는 도메인 인증이 필요. 개인 도메인이 없으면 `resend.dev` 같은 테스트 도메인으로 본인 발송만 가능 (가족·지인까지 보내려면 도메인 필요).

### 4. 구독자·발신자 설정

`subscribers.yaml` 편집:

```yaml
subscribers:
  - name: "본인"
    email: "you@example.com"
    active: true
  - name: "아내"
    email: "spouse@example.com"
    active: true

sender:
  from_name: "스테이블코인 데일리"
  from_email: "noreply@your-domain.com"   # Resend 인증한 도메인
  reply_to: "you@example.com"
```

### 5. GitHub 시크릿 등록

레포 Settings → Secrets and variables → Actions → New repository secret:

- `ANTHROPIC_API_KEY`
- `NAVER_CLIENT_ID` (선택)
- `NAVER_CLIENT_SECRET` (선택)
- `RESEND_API_KEY`

### 6. 로컬 테스트

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export RESEND_API_KEY=re_...
export NAVER_CLIENT_ID=...
export NAVER_CLIENT_SECRET=...
python main.py
```

본인 메일로 테스트 발송이 오면 성공.

### 7. GitHub Actions 활성화

`.github/workflows/daily.yml`이 레포에 들어있으면 자동으로 활성화.
첫 실행은 Actions 탭에서 "Run workflow" 버튼으로 수동 실행해 동작 확인.

## 동작 흐름

1. **수집** — 구글 뉴스 RSS + 네이버 뉴스 API + 직접 RSS + 정부기관 RSS
2. **시간 필터** — 최근 24시간 이내 기사
3. **관련성 필터** — 키워드 기반 1차 거름
4. **중복 제거** — URL 정규화 + 제목 해시
5. **이력 제외** — 어제 보낸 URL은 제외 (`data/sent_urls.json`)
6. **LLM 처리** — Claude Haiku로 분류·요약·중요도 점수 (배치 15건)
7. **컷오프** — 중요도 1짜리 제외, 상위 30건만 채택
8. **렌더링** — 카테고리별(규제/발행사/시장동향/기술/기타) 그룹핑
9. **발송** — Resend로 구독자별 개별 발송
10. **이력 저장** — 발송 URL을 레포에 커밋

## 비용

| 항목 | 비용 |
|---|---|
| GitHub Actions (퍼블릭 레포) | 무료 |
| Anthropic Claude Haiku | 일 30~50건 처리 → 월 500~1,500원 |
| Naver 검색 API | 무료 (일 25,000회 한도) |
| Resend | 무료 (일 100통 / 월 3,000통) |
| **합계** | **월 1~2천원** |

## 운영 팁

- **수집량이 적은 날**: `relevance_keywords.primary`에 키워드 추가, 또는 `naver_news.queries` 확장
- **노이즈 많은 날**: LLM 프롬프트에 제외 카테고리 명시, 또는 `exclude_keywords` 추가
- **카테고리 분류 오류**: `processors/llm.py`의 `SYSTEM_PROMPT` 수정
- **이메일 디자인 변경**: `templates/daily.html` 편집
- **실패 알림**: 별도 텔레그램 봇 워크플로 추가 (작성 예정)
