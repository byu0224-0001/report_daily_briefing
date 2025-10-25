# 🚀 빠른 설정 가이드

## 1️⃣ 환경 변수 파일 생성

프로젝트 루트에 `.env` 파일을 생성하고 아래 내용을 복사하세요:

```env
# OpenAI API Configuration
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL_NAME=gpt-5-mini

# Notion API Configuration
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: Timezone (default: Asia/Seoul)
TZ=Asia/Seoul
```

> 💡 `env.example` 파일을 복사해서 사용할 수 있습니다:
> ```bash
> cp env.example .env
> ```

---

## 2️⃣ API 키 발급 방법

### OpenAI API Key

1. [OpenAI Platform](https://platform.openai.com/) 접속
2. 우측 상단 프로필 → **API Keys** 클릭
3. **Create new secret key** 클릭
4. 생성된 키를 복사하여 `.env` 파일의 `OPENAI_API_KEY`에 입력

### Notion API Key & Database ID

#### Step 1: Integration 생성
1. [Notion Integrations](https://www.notion.so/my-integrations) 접속
2. **+ New Integration** 클릭
3. 정보 입력:
   - **Name**: `Daily Briefing Bot`
   - **Associated workspace**: 본인 워크스페이스 선택
4. **Capabilities** 설정:
   - ✅ Read content
   - ✅ Update content
   - ✅ Insert content
5. **Submit** 클릭
6. **Internal Integration Token** 복사 → `.env`의 `NOTION_API_KEY`에 입력

#### Step 2: Database 생성
1. Notion 앱 열기
2. 새 페이지 생성
3. `/database` 입력 → **Table - Full page** 선택
4. 페이지 이름: `📊 Daily Briefing Database`
5. 필수 속성(Property) 추가:

| Property Name       | Property Type | 설명                    |
|---------------------|---------------|-------------------------|
| `Name`              | Title         | (기본 제공)             |
| `Date`              | Date          | 브리핑 날짜             |
| `Top Keywords`      | Text          | 주요 키워드             |
| `Category Summary`  | Text          | 카테고리별 통계         |

#### Step 3: Integration 연결
1. Database 페이지 우측 상단 **⋯** (더보기) 클릭
2. **Add connections** 클릭
3. 위에서 만든 Integration(`Daily Briefing Bot`) 선택
4. **Confirm** 클릭

#### Step 4: Database ID 복사
1. Database 페이지에서 브라우저 주소창 URL 확인:
   ```
   https://www.notion.so/myworkspace/1234567890abcdef1234567890abcdef?v=...
                                     ↑ 이 32자리가 DATABASE_ID
   ```
2. 해당 ID를 복사하여 `.env`의 `NOTION_DATABASE_ID`에 입력

---

## 3️⃣ GitHub Actions 설정

### Repository Secrets 등록

1. GitHub Repository 페이지 접속
2. **Settings** → **Secrets and variables** → **Actions** 클릭
3. **New repository secret** 버튼 클릭
4. 아래 4개의 Secret을 순서대로 추가:

| Name                  | Value                                |
|-----------------------|--------------------------------------|
| `OPENAI_API_KEY`      | `.env`의 `OPENAI_API_KEY` 값         |
| `OPENAI_MODEL_NAME`   | `gpt-5-mini`                             |
| `NOTION_API_KEY`      | `.env`의 `NOTION_API_KEY` 값         |
| `NOTION_DATABASE_ID`  | `.env`의 `NOTION_DATABASE_ID` 값     |

---

## 4️⃣ 로컬 실행 테스트

```bash
# 의존성 설치
pip install -r requirements.txt

# 실행
python run_daily_briefing.py
```

### 예상 출력:
```
🚀 2025.10.25 CrewAI Daily Briefing 시작 (v7-Final)
⚠️ 네이버 투자정보 수집 중...
⚠️ 네이버 종목분석 수집 중...
...
✅ Notion 업로드 완료 (Page ID: xxx-xxx-xxx)
✅ 완료: ...
```

---

## 5️⃣ 자동 실행 확인

### 스케줄 확인
- **매일 오전 7시 (KST)** 자동 실행
- GitHub Actions 탭에서 실행 로그 확인

### 수동 실행 방법
1. GitHub Repository → **Actions** 탭
2. **Daily AI Briefing** 워크플로 선택
3. **Run workflow** 버튼 클릭
4. **Run workflow** 확인

---

## ✅ 설정 완료 체크리스트

- [ ] `.env` 파일 생성 완료
- [ ] OpenAI API Key 발급 및 입력
- [ ] Notion Integration 생성
- [ ] Notion Database 생성 및 속성 설정
- [ ] Integration을 Database에 연결
- [ ] Database ID 복사 및 입력
- [ ] GitHub Repository Secrets 4개 등록
- [ ] 로컬 실행 테스트 성공
- [ ] GitHub Actions 수동 실행 테스트 성공

---

## 🆘 문제 해결

### Q1. `OPENAI_API_KEY not found` 에러
**A:** `.env` 파일이 프로젝트 루트에 있는지 확인하고, `python-dotenv`가 설치되어 있는지 확인하세요.

### Q2. `Notion API 403 Forbidden`
**A:** Integration이 Database에 연결되어 있는지 다시 확인하세요. (Database 우측 상단 ⋯ → Connections 확인)

### Q3. `GitHub Actions에서 실행되지 않음`
**A:** Repository Secrets가 모두 정확히 입력되었는지 확인하세요. Secret 이름은 대소문자를 구분합니다.

### Q4. `PDF 추출 실패` 에러가 많이 발생
**A:** 정상입니다. 일부 리포트는 PDF 링크가 없거나 접근이 제한될 수 있습니다. 시스템은 이를 자동으로 건너뜁니다.

---

**🎉 설정 완료! 이제 매일 아침 자동으로 브리핑이 생성됩니다.**

