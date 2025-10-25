# 🔐 GitHub Secrets 설정 가이드

## 📋 현재 환경 변수 상태

`.env` 파일에서 확인된 값:

| 변수명                  | 상태                          | 비고                          |
|-------------------------|-------------------------------|-------------------------------|
| `OPENAI_API_KEY`        | ✅ **설정됨**                 | sk-proj-ajkrw...              |
| `OPENAI_MODEL_NAME`     | ✅ **설정됨**                 | gpt-5-mini                    |
| `NOTION_API_KEY`        | ⚠️ **예시 값 (설정 필요)**    | secret_xxxx... (실제 키 필요) |
| `NOTION_DATABASE_ID`    | ⚠️ **예시 값 (설정 필요)**    | xxxx... (실제 ID 필요)        |

---

## 🚀 방법 1: 자동 설정 (GitHub CLI 사용)

### 1단계: GitHub CLI 설치

```powershell
# Windows (winget)
winget install --id GitHub.cli

# 또는 직접 다운로드
# https://cli.github.com/
```

### 2단계: GitHub 인증

```powershell
gh auth login
```

화면 안내를 따라 GitHub 계정으로 로그인

### 3단계: Notion 값 업데이트 (필수!)

`.env` 파일을 열고 실제 Notion 값으로 수정:

```env
# .env 파일 수정
NOTION_API_KEY=secret_실제키입력
NOTION_DATABASE_ID=실제데이터베이스ID입력
```

**Notion 값 얻는 방법:**
- **NOTION_API_KEY**: [Notion Integrations](https://www.notion.so/my-integrations) → Integration 생성 → Token 복사
- **NOTION_DATABASE_ID**: Notion Database URL에서 추출 (32자리)
  ```
  https://www.notion.so/workspace/1234567890abcdef1234567890abcdef?v=...
                                   ↑ 이 부분
  ```

### 4단계: 자동 설정 스크립트 실행

```powershell
cd C:\Users\Admin\WORKSPACE\Cursor\economic_study\economic_report_ai_v2
.\setup_github_secrets.ps1
```

✅ 완료! Secrets가 자동으로 등록됩니다.

---

## 📝 방법 2: 수동 설정 (웹 브라우저 사용)

### 1단계: GitHub Secrets 페이지 이동

**직접 링크:**
👉 https://github.com/byu0224-0001/report_daily_briefing/settings/secrets/actions

또는 수동으로:
1. https://github.com/byu0224-0001/report_daily_briefing
2. **Settings** 클릭
3. 좌측 메뉴: **Secrets and variables** → **Actions**
4. **New repository secret** 클릭

### 2단계: Secrets 하나씩 등록

#### Secret 1: OPENAI_API_KEY

- **Name**: `OPENAI_API_KEY`
- **Value**: `.env` 파일의 `OPENAI_API_KEY` 값을 복사하여 붙여넣기
  ```
  sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  ```
- **Add secret** 클릭

> 💡 **실제 값은 `.env` 파일에서 복사하세요**: `sk-proj-ajkrw...`로 시작하는 전체 키

#### Secret 2: OPENAI_MODEL_NAME

- **Name**: `OPENAI_MODEL_NAME`
- **Value**: 
  ```
  gpt-5-mini
  ```
- **Add secret** 클릭

#### Secret 3: NOTION_API_KEY ⚠️ (실제 값 필요)

- **Name**: `NOTION_API_KEY`
- **Value**: `secret_실제_Notion_Integration_Token`
- **Add secret** 클릭

**실제 값 얻는 방법:**
1. [Notion Integrations](https://www.notion.so/my-integrations) 접속
2. **+ New integration** 클릭
3. 이름 입력 (예: `Daily Briefing Bot`)
4. Workspace 선택
5. **Capabilities** 체크:
   - ✅ Read content
   - ✅ Update content
   - ✅ Insert content
6. **Submit** 클릭
7. **Internal Integration Token** 복사 → Secret으로 등록

#### Secret 4: NOTION_DATABASE_ID ⚠️ (실제 값 필요)

- **Name**: `NOTION_DATABASE_ID`
- **Value**: `32자리_Database_ID`
- **Add secret** 클릭

**실제 값 얻는 방법:**
1. Notion에서 Database 페이지 열기
2. 브라우저 주소창 URL 확인:
   ```
   https://www.notion.so/myworkspace/1234567890abcdef1234567890abcdef?v=yyy
                                     ↑ 이 32자리가 DATABASE_ID
   ```
3. 복사 → Secret으로 등록

### 3단계: 등록 확인

모든 Secret 등록 후, 다음과 같이 4개가 보여야 합니다:

```
✅ OPENAI_API_KEY          Updated XX seconds ago
✅ OPENAI_MODEL_NAME       Updated XX seconds ago  
✅ NOTION_API_KEY          Updated XX seconds ago
✅ NOTION_DATABASE_ID      Updated XX seconds ago
```

---

## 🧪 테스트: GitHub Actions 수동 실행

### 1. Actions 탭 이동

👉 https://github.com/byu0224-0001/report_daily_briefing/actions

### 2. 워크플로우 선택

**Daily AI Briefing** 클릭

### 3. 수동 실행

- 우측 **"Run workflow"** 버튼 클릭
- Branch: `main` 선택
- **"Run workflow"** 클릭

### 4. 실행 로그 확인

- 노란색 점: 실행 중
- 녹색 체크: 성공 ✅
- 빨간 X: 실패 ❌ (로그 클릭하여 원인 확인)

### 5. Notion에서 확인

성공 시 Notion Database에 새로운 브리핑 페이지가 생성됩니다!

---

## ⚠️ 중요: Notion 설정이 아직 안 된 경우

현재 `.env` 파일의 Notion 값들이 예시 값입니다:

```env
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**반드시 실제 값으로 변경해야 합니다!**

### Notion 설정 전체 프로세스

#### 1️⃣ Integration 생성
1. https://www.notion.so/my-integrations
2. **+ New integration**
3. 이름: `Daily Briefing Bot`
4. Submit → **Token 복사**

#### 2️⃣ Database 생성
1. Notion 앱에서 새 페이지 생성
2. `/database` → **Table - Full page**
3. 페이지 이름: `📊 Daily Briefing Database`
4. 속성 추가:
   - `Name` (Title) - 기본 제공
   - `Date` (Date) - 추가 필요
   - `Top Keywords` (Text) - 추가 필요
   - `Category Summary` (Text) - 추가 필요

#### 3️⃣ Integration 연결
1. Database 페이지 우측 상단 **⋯** 클릭
2. **Add connections**
3. `Daily Briefing Bot` 선택
4. **Confirm**

#### 4️⃣ Database ID 복사
1. 브라우저 URL에서 32자리 ID 복사
2. `.env` 파일에 입력

#### 5️⃣ 다시 Secrets 등록
위의 "방법 1" 또는 "방법 2"로 진행

---

## 🎯 빠른 체크리스트

### GitHub Secrets 등록 전:
- [ ] GitHub CLI 설치됨 (방법 1 사용 시)
- [ ] `.env` 파일에 실제 Notion 값 입력됨
- [ ] Notion Integration 생성됨
- [ ] Notion Database 생성 및 연결됨

### GitHub Secrets 등록:
- [ ] `OPENAI_API_KEY` 등록
- [ ] `OPENAI_MODEL_NAME` 등록  
- [ ] `NOTION_API_KEY` 등록
- [ ] `NOTION_DATABASE_ID` 등록

### 테스트:
- [ ] Actions 탭에서 수동 실행
- [ ] 실행 로그 확인 (5-10분 소요)
- [ ] Notion Database에 브리핑 생성 확인

---

## 🆘 문제 해결

### Q1: "Secrets not found" 에러
**A**: Secret 이름이 정확한지 확인하세요. 대소문자를 구분합니다.

### Q2: "Notion API 401 Unauthorized"
**A**: `NOTION_API_KEY`가 올바른지 확인하세요.

### Q3: "Notion API 404 Not Found"
**A**: 
1. `NOTION_DATABASE_ID`가 올바른지 확인
2. Integration이 Database에 연결되어 있는지 확인

### Q4: PowerShell 스크립트 실행 불가
**A**: 실행 정책 변경이 필요할 수 있습니다:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 📚 참고 링크

- **Secrets 설정**: https://github.com/byu0224-0001/report_daily_briefing/settings/secrets/actions
- **Actions 확인**: https://github.com/byu0224-0001/report_daily_briefing/actions
- **Notion Integrations**: https://www.notion.so/my-integrations
- **GitHub CLI**: https://cli.github.com/

---

**🎉 Secrets 설정이 완료되면 완전 자동화가 시작됩니다!**

