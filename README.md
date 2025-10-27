# 🤖 AI Daily Briefing System (v11.1)

**CrewAI 기반 일일 증권사 리포트 자동 수집·분석·브리핑 시스템**

---

## 📋 프로젝트 개요

이 시스템은 매일 아침 **국내 주요 증권사 리포트를 자동으로 수집·분석·요약**하여,  
**Notion Database에 일일 브리핑 페이지를 자동 생성**하는 완전 자동화 파이프라인입니다.

### 🎯 주요 기능

1. **자동 리포트 수집** (네이버 금융 + 한경컨센서스)
2. **키워드 자동 추출** (빈도 분석 기반)
3. **PDF 본문 요약** (GPT-5-mini 기반 2-3줄 요약)
4. **일일 브리핑 생성** (애널리스트 스타일 종합 리포트)
5. **Notion 자동 업로드** (페이지 + 본문 블록 생성)
6. **GitHub Actions 자동 실행** (매일 오전 9시 KST, 평일만)

---

## 🏗️ 아키텍처

```
📦 economic_report_ai_v2/
├── run_daily_briefing.py          # 핵심 파이프라인 (CrewAI 5-Agent)
├── requirements.txt               # Python 의존성
├── .env.example                   # 환경 변수 템플릿
├── .github/
│   └── workflows/
│       └── daily.yml              # GitHub Actions 스케줄러
└── README.md                      # 프로젝트 문서 (현재 파일)
```

### 🔄 파이프라인 흐름

```
1️⃣ Researcher Agent
   ↓ (네이버/한경 리포트 수집)
   
2️⃣ Analyzer Agent              3️⃣ Summarizer Agent
   ↓ (키워드 분석)               ↓ (PDF 요약)
   
4️⃣ Briefing Agent
   ↓ (일일 브리핑 생성)
   
5️⃣ Notion Uploader Agent
   ↓ (Notion DB 업로드)
   
✅ 완료
```

---

## 🚀 빠른 시작 가이드

### 1. 로컬 환경 설정

#### 1-1. 레포지토리 클론
```bash
git clone <your-repo-url>
cd economic_study/economic_report_ai_v2
```

#### 1-2. Python 가상환경 생성 (권장)
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

#### 1-3. 의존성 설치
```bash
pip install -r requirements.txt
```

#### 1-4. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일을 열어 실제 API 키 입력
```

`.env` 파일 예시:
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxx
OPENAI_MODEL_NAME=gpt-5-mini
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxx
```

#### 1-5. 로컬 실행 테스트
```bash
python run_daily_briefing.py
```

---

### 2. Notion 설정

#### 2-1. Notion Integration 생성
1. [Notion Integrations](https://www.notion.so/my-integrations) 접속
2. **New Integration** 클릭
3. 이름 설정 (예: `Daily Briefing Bot`)
4. **Capabilities** → "Read content", "Update content", "Insert content" 체크
5. **Submit** → **Internal Integration Token** 복사 → `.env`의 `NOTION_API_KEY`에 입력

#### 2-2. Notion Database 생성
1. Notion에서 새 페이지 생성 → `/database` → **Table - Full page** 선택
2. 필수 속성 추가:
   - `Name` (Title) - 기본 제공
   - `Date` (Date)
   - `Top Keywords` (Text)
   - `Category Summary` (Text)

3. 우측 상단 **...** → **Add connections** → 위에서 만든 Integration 연결
4. 브라우저 URL에서 Database ID 복사:
   ```
   https://www.notion.so/myworkspace/xxxxxxxxxxxxxxxxxxxxx?v=yyy
                                     ↑ 이 부분이 DATABASE_ID
   ```
5. `.env`의 `NOTION_DATABASE_ID`에 입력

---

### 3. GitHub Actions 자동 실행 설정

#### 3-1. Repository Secrets 등록
1. GitHub Repository → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭 후 다음 4개 추가:

| Secret Name          | Value 예시                          |
|----------------------|-------------------------------------|
| `OPENAI_API_KEY`     | `sk-proj-xxxxxxxxxxxxxxxx`          |
| `OPENAI_MODEL_NAME`  | `gpt-5-mini`                        |
| `NOTION_API_KEY`     | `secret_xxxxxxxxxxxxxxxx`           |
| `NOTION_DATABASE_ID` | `xxxxxxxxxxxxxxxx`                  |

#### 3-2. 자동 실행 확인
- **평일 오전 9시 (KST)** 자동 실행 (월~금)
- 주말은 자동 스킵
- **Actions** 탭에서 실행 로그 확인 가능
- 수동 실행: **Actions** → **Daily AI Briefing** → **Run workflow**

---

## 🛠️ 상세 기능 설명

### Agent 구성

| Agent              | 역할                           | 사용 Tool                     |
|--------------------|--------------------------------|-------------------------------|
| **Researcher**     | 리포트 수집                    | Naver/Hankyung Scraper        |
| **Analyzer**       | 키워드/카테고리 분석           | Python Analyzer Tool          |
| **Summarizer**     | PDF 본문 요약                  | Report Summarizer Tool        |
| **Analyst**        | 일일 브리핑 생성               | Final Briefing Tool           |
| **Notion Uploader**| Notion DB 업로드               | Notion Upload Tool            |

### 수집 출처

- **네이버 금융 리서치**: 4개 카테고리
  - 투자정보 / 종목분석 / 산업분석 / 경제분석
- **한경컨센서스**: 종목 애널리스트 리포트

### 브리핑 구성

1. **핵심 테마 TOP 3-5** (키워드 기반)
2. **거시경제 요약**
3. **주요 종목 및 산업별 요약**

---

## 📊 출력 예시

### Notion 페이지 구조
```
📄 2025-10-25 일일 브리핑
   ├── Date: 2025-10-25
   ├── Top Keywords: 삼성전자(12회), 2차전지(8회), 반도체(7회)...
   └── Category Summary: {'종목분석': 45, '투자정보': 23, ...}

   📝 본문:
   # 2025-10-25 일일 증권사 리포트 브리핑
   *총 68건 기반 / 2025.10.25 발행*
   
   ## 핵심 테마 TOP 5
   1. 반도체 업황 회복 기대
   2. 2차전지 밸류체인 재평가
   ...
```

---

## 🔧 트러블슈팅

### 1. `ModuleNotFoundError: No module named 'crewai'`
```bash
pip install --upgrade crewai crewai-tools
```

### 2. `PDF 추출 실패` 에러
- PyMuPDF 재설치: `pip install --upgrade PyMuPDF`
- 네트워크 타임아웃 가능성 → `timeout=15` 조정

### 3. `Notion API 403 Forbidden`
- Integration이 Database에 연결되어 있는지 확인
- Database ID가 정확한지 재확인

### 4. GitHub Actions 실행 실패
- Repository Secrets 4개 모두 등록했는지 확인
- Actions 탭 → 실패한 Job → 로그 확인

---

## 🚀 확장 기능 (선택 사항)

### 1. Slack 알림 추가
```python
def send_slack_notification(webhook_url: str, page_url: str):
    payload = {"text": f"✅ 일일 브리핑 생성 완료: {page_url}"}
    requests.post(webhook_url, json=payload)
```

### 2. 디버그 모드 추가
```bash
python run_daily_briefing.py --test  # 3개 리포트만 수집
```

### 3. 멀티 에이전트 확장
- 종목 분석 전담 Agent
- 거시경제 전담 Agent
- 병렬 처리로 속도 개선

---

## 📝 라이선스 & 면책조항

- 이 시스템은 **개인 학습·투자 참고용**으로 개발되었습니다.
- 수집된 리포트의 저작권은 원본 증권사에 있습니다.
- 투자 손실에 대한 책임은 사용자 본인에게 있습니다.

---

## 👨‍💻 개발자

**병욱** | AI/MLOps 자동화 아키텍처

---

## 📚 참고 문서

- [CrewAI Documentation](https://docs.crewai.com/)
- [Notion API Reference](https://developers.notion.com/)
- [OpenAI API Documentation](https://platform.openai.com/docs/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

---

**🎉 이제 매일 평일 오전 9시, 자동으로 생성되는 브리핑을 Notion에서 확인하세요!**

---

## 📌 v11.1 주요 변경사항

### ✅ 프로덕션 모드 활성화
- 테스트 모드 해제, 평일만 실행
- PDF whitelist 검증 강화 (stock.pstatic.net만 허용)
- HTML fallback 로직 개선 (신한투자 리포트 대응)
- 인코딩 안정화 (PYTHONUTF8=1 추가)

### 🛠️ 기술 개선
- PDF URL 필터링 강화 (종목 페이지 차단)
- meta refresh 리다이렉트 추적 (무한 루프 방지)
- Mobile UA 조건부 적용
- PDF 캐싱 구조 추가

