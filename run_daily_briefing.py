# ==========================================================
# CrewAI Daily Briefing v9.0 (전수 리포트 분석 + 하이브리드 모델)
# - 모든 리포트 전수 요약 (PDF + HTML)
# - gpt-4o-mini (압축) + gpt-5-mini (브리핑)
# - 병렬 처리로 속도 최적화
# ==========================================================
import os, re, time, fitz, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openai import OpenAI
from crewai.tools import BaseTool
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ----------------------------------------------------------
# 0️⃣ 환경 설정
# ----------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# 하이브리드 모델: gpt-4o-mini (압축) + gpt-5-mini (브리핑)
LLM_SUMMARY = "gpt-4o-mini"  # 리포트 요약용 (빠르고 저렴)
LLM_BRIEFING = os.getenv("OPENAI_MODEL_NAME", "gpt-5-mini")  # 브리핑 생성용
client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
NOTION_HEADERS = {"Authorization": f"Bearer {NOTION_API_KEY}",
                  "Notion-Version": "2022-06-28",
                  "Content-Type": "application/json"}

today_display = datetime.now().strftime("%Y.%m.%d")
today_file = datetime.now().strftime("%Y-%m-%d")

# 테스트 모드: 최근 3일치 리포트 수집 (주말 대응)
TEST_MODE_RECENT_DAYS = False  # True: 최근 3일, False: 오늘만 (프로덕션 모드)
if TEST_MODE_RECENT_DAYS:
    # 4자리 연도와 2자리 연도 둘 다 생성
    target_dates_full = [(datetime.now() - timedelta(days=i)).strftime("%Y.%m.%d") for i in range(3)]
    target_dates_short = [(datetime.now() - timedelta(days=i)).strftime("%y.%m.%d") for i in range(3)]
    target_dates = target_dates_full + target_dates_short  # 둘 다 허용
    print(f"[TEST] 최근 3일치 리포트 수집 모드: {', '.join(target_dates_full)}")
else:
    target_dates = [today_display, datetime.now().strftime("%y.%m.%d")]
    print(f"[PROD] 오늘 날짜만 수집: {today_display}")

# ----------------------------------------------------------
# 🌐 Selenium 설정
# ----------------------------------------------------------
def create_selenium_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

# ----------------------------------------------------------
# 1️⃣ 리포트 수집
# ----------------------------------------------------------
class NaverResearchScraperTool(BaseTool):
    name: str = "Naver Research Scraper Tool"
    description: str = "네이버 금융 리서치 리포트 수집"
    
    def _run(self) -> str:
        """네이버 리서치 리포트 수집 (Selenium)"""
        base_url = "https://finance.naver.com/research/"
        categories = {
            "투자정보": "invest_list.naver",
            "종목분석": "company_list.naver",
            "산업분석": "industry_list.naver",
            "경제분석": "economy_list.naver"
        }
        reports = []
        driver = create_selenium_driver()
        print(f"\n[DEBUG] 네이버 수집 시작 - 날짜: {target_dates}")
        try:
            for cat, path in categories.items():
                url = base_url + path
                print(f"\n[DEBUG] {cat} 페이지 접속: {url}")
                driver.get(url)
                time.sleep(3)  # 로딩 대기 시간 증가
                
                # 페이지 소스 저장 (디버깅용)
                page_source = driver.page_source
                if "table" not in page_source.lower():
                    print(f"   ⚠️ {cat}: 페이지 소스에 'table' 없음")
                    continue
                
                soup = BeautifulSoup(page_source, "html.parser")
                
                # 다양한 선택자 시도
                rows = soup.select("table.type_1 tbody tr")
                if not rows:
                    rows = soup.select("table tbody tr")
                if not rows:
                    rows = soup.select("tbody tr")
                if not rows:
                    rows = soup.find_all("tr")
                
                print(f"[DEBUG] {cat}: {len(rows)}개 row 발견")
                for i, row in enumerate(rows):
                    cols = row.find_all("td")
                    if len(cols) < 4: 
                        continue
                    
                    # 컬럼 구조 분석 (종목명, 제목, 증권사, 첨부, 작성일, 조회수)
                    # 제목은 보통 cols[0] 또는 cols[1]
                    title_tag = cols[0].find("a")
                    if not title_tag and len(cols) > 1:
                        title_tag = cols[1].find("a")
                    
                    # 증권사는 보통 cols[1] 또는 cols[2]
                    company = cols[2].get_text(strip=True) if len(cols) > 2 else "N/A"
                    if not company or company == "":
                        company = cols[1].get_text(strip=True) if len(cols) > 1 else "N/A"
                    
                    # 날짜 찾기: 뒤에서 두 번째 컬럼 (작성일)
                    date = ""
                    if len(cols) >= 6:  # 6개 컬럼: [종목명, 제목, 증권사, 첨부, 작성일, 조회수]
                        date = cols[4].get_text(strip=True)  # 작성일 (5번째, 0-indexed)
                    elif len(cols) >= 5:  # 5개 컬럼: [제목, 증권사, 첨부, 작성일, 조회수]
                        date = cols[3].get_text(strip=True)  # 작성일
                    else:
                        date = cols[-2].get_text(strip=True)  # 뒤에서 두 번째
                    
                    # 디버그: 처음 5개 row 출력
                    if i < 5:
                        title_text = title_tag.get_text(strip=True)[:30] if title_tag else 'N/A'
                        print(f"   - [{date}] {title_text}... (컬럼수: {len(cols)})")
                    
                    # 날짜 형식 통일 (공백, 특수문자 제거)
                    date_clean = date.replace(" ", "").replace(".", ".").strip()
                    
                    # 날짜 필터
                    if date_clean not in target_dates:
                        continue
                    if not title_tag:
                        continue
                    
                    # href 추출 및 검증
                    href = title_tag.get("href", "")
                    if not href or href == "#":
                        continue
                    
                    # URL 조합: 절대 경로 체크
                    if href.startswith("http"):
                        detail_url = href
                    elif href.startswith("/"):
                        detail_url = "https://finance.naver.com" + href
                    else:
                        detail_url = "https://finance.naver.com/" + href
                    
                    # PDF URL 추출: 첨부 컬럼에서 직접 찾기 (강화)
                    pdf_url = None
                    try:
                        # 첨부 컬럼 (보통 cols[3] 또는 cols[4])
                        attach_col = cols[3] if len(cols) > 3 else cols[2] if len(cols) > 2 else None
                        if attach_col:
                            # 네이버 PDF 다운로드 링크 패턴 강화
                            pdf_link = attach_col.find("a", href=re.compile(r"\.pdf|download|filekey|attach|report|view", re.IGNORECASE))
                            if pdf_link:
                                href = pdf_link.get("href", "")
                                if href.startswith("http"):
                                    pdf_url = href
                                elif href.startswith("/"):
                                    pdf_url = "https://finance.naver.com" + href
                                else:
                                    pdf_url = "https://finance.naver.com/" + href
                        
                        # 상세 페이지에서 PDF 찾기
                        if not pdf_url:
                            d_res = requests.get(detail_url, headers=HEADERS, timeout=5)
                            d_soup = BeautifulSoup(d_res.text, "html.parser")
                            
                            # 다양한 패턴 시도 (강화)
                            pdf_btn = d_soup.find("a", href=re.compile(r"download|view|filekey|attach|\.pdf", re.IGNORECASE))
                            if not pdf_btn:
                                pdf_btn = d_soup.find("a", string=re.compile("리포트보기|PDF|다운로드|보기", re.IGNORECASE))
                            if not pdf_btn:
                                pdf_btn = d_soup.find("a", class_=re.compile("pdf|download|report", re.IGNORECASE))
                            
                            if pdf_btn:
                                pdf_href = pdf_btn.get("href", "")
                                if pdf_href.startswith("http"):
                                    pdf_url = pdf_href
                                elif pdf_href.startswith("/"):
                                    pdf_url = "https://finance.naver.com" + pdf_href
                                else:
                                    pdf_url = "https://finance.naver.com/" + pdf_href
                    except Exception as e:
                        pdf_url = None
                    # URL 유효성 검사 (종목 화면 리다이렉트 제외 - 확장)
                    valid_url = detail_url
                    if not detail_url or not detail_url.startswith("http"):
                        valid_url = None
                    # 모든 /item/ 패턴 제외 (종목 페이지)
                    if valid_url and "/item/" in valid_url:
                        valid_url = None
                    
                    reports.append({
                        "source": "네이버",
                        "category": cat,
                        "title": title_tag.get_text(strip=True),
                        "company": company,
                        "date": date,
                        "url": valid_url,
                        "pdf_url": pdf_url
                    })
                print(f"   [OK] {cat}: {len([r for r in reports if r['category'] == cat])}개 수집 완료")
                time.sleep(1)
        finally:
            driver.quit()
        print(f"[OK] 네이버: {len(reports)}개 수집 완료")
        return str(reports)

class HankyungScraperTool(BaseTool):
    name: str = "Hankyung Scraper Tool"
    description: str = "한경 컨센서스 리포트 수집"
    
    def _run(self) -> str:
        """한경컨센서스 리포트 수집"""
        url = "https://consensus.hankyung.com/analysis/list"
        reports = []
        print(f"[DEBUG] 한경 수집 시작 - 검색 날짜: {target_dates[:3]}")
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            rows = soup.select("table tbody tr")
            print(f"[DEBUG] 한경: {len(rows)}개 row 발견")
            row_count = 0
            collected_count = 0
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 4: 
                    continue
                date_raw = cols[3].get_text(strip=True)
                # 날짜 형식 통일 (YYYY-MM-DD → YYYY.MM.DD, YY-MM-DD → YY.MM.DD)
                date = date_raw.replace("-", ".")
                # 날짜 필터: target_dates 목록에 있는 날짜만 수집
                if date not in target_dates:
                    continue
                title_tag = cols[0].find("a")
                if not title_tag:
                    continue
                pdf_tag = row.find("a", href=re.compile(r"\.pdf$"))
                pdf_url = "https://consensus.hankyung.com" + pdf_tag["href"] if pdf_tag else None
                reports.append({
                    "source": "한경컨센서스",
                    "category": cols[2].get_text(strip=True),
                    "title": title_tag.get_text(strip=True),
                    "company": cols[1].get_text(strip=True),
                    "date": date,
                    "url": "https://consensus.hankyung.com" + title_tag["href"],
                    "pdf_url": pdf_url
                })
                collected_count += 1
                time.sleep(0.5)
            print(f"   [OK] 한경: {collected_count}개 수집 완료")
        except Exception as e:
            print(f"⚠️ 한경 수집 실패: {e}")
        return str(reports)

# ----------------------------------------------------------
# 2️⃣ 키워드 분석 (날짜 제외)
# ----------------------------------------------------------
class PythonAnalyzerTool(BaseTool):
    name: str = "Python Analyzer Tool"
    description: str = "리포트 제목 기반 키워드/카테고리 분석"
    
    def _run(self, reports_str: str) -> str:
        """키워드 및 카테고리 분석"""
        try:
            reports = eval(reports_str)
            df = pd.DataFrame(reports).drop_duplicates(subset=["title", "company"])
            
            # 단어 추출
            words = sum([re.findall(r"[가-힣A-Za-z0-9]{2,12}", t) for t in df["title"]], [])
            
            # 날짜 관련 키워드 제외 (10, 24, 26, 10월, 2025 등)
            today = datetime.now().day
            month = datetime.now().month
            year = datetime.now().year
            date_pattern = re.compile(r"(\d{1,2}월|\d{1,2}일|20\d{2}|\d{2}\.\d{2}|\d{4}\.\d{2}\.\d{2})")
            
            # 숫자 전용 패턴 (모든 숫자 제외)
            number_pattern = re.compile(r'^\d+$')
            
            stop_words = {
                "리포트", "분석", "전망", "투자", "경제", "산업", "이슈",
                str(today), str(month), str(year), f"{month}월", "2025", "25", "24", "10", "26",
                "Weekly", "Preview", "Monitor", "Daily", "주간", "주차", "일보",
                "China", "Weekly", "3Q25", "4주차", "10월", "11월", "12월"
            }
            
            filtered_words = [
                w for w in words
                if w not in stop_words 
                and not date_pattern.search(w) 
                and not number_pattern.match(w)  # 순수 숫자 제외
                and len(w) >= 2
                and w.isalnum()  # 영문자/한글만 허용
            ]
            
            counter = Counter(filtered_words)
            
            result = {
                "total_reports": len(df),
                "top_keywords": ", ".join([f"{k}({v}회)" for k, v in counter.most_common(10)]),
                "category_summary": df["category"].value_counts().to_dict(),
                "reports": df.to_dict("records")  # 리포트 전체 정보 포함
            }
            return str(result)
        except Exception as e:
            return f"분석 실패: {e}"

# ----------------------------------------------------------
# 3️⃣ 각 리포트별 핵심 1줄 요약 (PDF 내용 포함)
# ----------------------------------------------------------
class ReportSummarizerTool(BaseTool):
    name: str = "Report Summarizer Tool"
    description: str = "전체 리포트 전수 요약 (병렬 처리)"
    
    def _extract_pdf_text(self, pdf_url: str) -> str:
        """PDF 본문 추출"""
        try:
            # PDF URL 유효성 검증
            if not pdf_url or not isinstance(pdf_url, str):
                return ""
            
            # URL 파라미터 제거 (query string, fragment 제거)
            original_url = pdf_url
            pdf_url = pdf_url.split("?")[0].split("#")[0]
            
            # 공백 제거 먼저 (중요!)
            pdf_url_stripped = pdf_url.strip()
            
            # PDF URL 보정 (`.p` → `.pdf` 자동 추가) - 개선 버전
            if pdf_url_stripped and not pdf_url_stripped.lower().endswith(".pdf"):
                # URL이 잘린 경우 (.p 또는 .pd로 끝나는 경우)
                if pdf_url_stripped.endswith(".p"):
                    pdf_url = pdf_url_stripped[:-1] + "pdf"  # .p → .pdf (버그 수정)
                elif pdf_url_stripped.endswith(".pd"):
                    pdf_url = pdf_url_stripped[:-2] + "pdf"  # .pd → .pdf
                # pstatic URL 패턴 특별 처리 (점으로 끝나지 않는 경우만)
                elif "pstatic.net" in pdf_url_stripped and not pdf_url_stripped.endswith("."):
                    pdf_url = pdf_url_stripped + ".pdf"
                # 숫자로 끝나는 URL에도 .pdf 자동 추가
                elif re.search(r'/\d+$', pdf_url_stripped):
                    pdf_url = pdf_url_stripped + ".pdf"
                else:
                    pdf_url = pdf_url_stripped
            else:
                pdf_url = pdf_url_stripped
            
            print(f"      [DEBUG PDF] 원본: {original_url[:80]} → 수정: {pdf_url[:80]}")
            
            # HTTP 요청 시도 (다중 fallback)
            res = None
            attempts = []
            
            # 1. 보정된 URL부터 시도
            if pdf_url_stripped != pdf_url:
                attempts.append(pdf_url)
                print(f"      [DEBUG PDF] 보정 URL 추가: {pdf_url[:80]}")
            
            # 2. 원본 URL 시도
            attempts.append(pdf_url_stripped)
            
            # 3. .p/.pd 패턴이면 수정본 추가 시도
            if pdf_url_stripped.endswith(".p") and pdf_url_stripped not in attempts:
                fixed_p = pdf_url_stripped[:-1] + "pdf"  # 버그 수정: df → pdf
                attempts.append(fixed_p)
                print(f"      [DEBUG PDF] .p 수정본 추가: {fixed_p[:80]}")
            elif pdf_url_stripped.endswith(".pd") and pdf_url_stripped not in attempts:
                fixed_pd = pdf_url_stripped[:-2] + "pdf"
                attempts.append(fixed_pd)
                print(f"      [DEBUG PDF] .pd 수정본 추가: {fixed_pd[:80]}")
            
            # 4. 확장자 없는 경우 .pdf 추가 시도
            if not pdf_url_stripped.endswith(".pdf") and not pdf_url_stripped.endswith(".p") and not pdf_url_stripped.endswith(".pd"):
                attempts.append(pdf_url_stripped + ".pdf")
                print(f"      [DEBUG PDF] .pdf 추가 시도: {(pdf_url_stripped + '.pdf')[:80]}")
            
            for i, attempt_url in enumerate(attempts):
                try:
                    print(f"      [DEBUG PDF] 시도 {i+1}/{len(attempts)}: {attempt_url[:80]}")
                    res = requests.get(attempt_url, headers=HEADERS, timeout=15, stream=True)
                    if res.status_code == 200:
                        pdf_url = attempt_url
                        if len(attempts) > 1:
                            print(f"      [DEBUG PDF] ✓ 성공! {attempt_url[:80]}")
                        break
                    else:
                        print(f"      [DEBUG PDF] HTTP {res.status_code}")
                except Exception as e:
                    print(f"      [DEBUG PDF] 예외: {str(e)[:50]}")
                    continue
            
            if not res or res.status_code != 200:
                print(f"      [DEBUG PDF] HTTP {res.status_code if res else 'None'} - 모든 시도 실패")
                return ""
            
            # Content-Type 검증 완화 (PDF가 아니어도 시도)
            content_type = res.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and not pdf_url.endswith('.pdf'):
                print(f"      [DEBUG PDF] Content-Type: {content_type} (PDF 아님)")
                
                # HTML 응답인 경우 재시도
                if content_type.startswith('text/html'):
                    print(f"      [DEBUG PDF] HTML 응답 → URL 재구성 시도")
                    # .pdf 자동 추가 시도
                    alt_pdf = pdf_url.split("?")[0] + ".pdf"
                    try:
                        res_alt = requests.get(alt_pdf, headers=HEADERS, timeout=10)
                        if res_alt.status_code == 200 and 'pdf' in res_alt.headers.get('content-type', '').lower():
                            res = res_alt
                            pdf_url = alt_pdf
                            print(f"      [DEBUG PDF] 재구성 성공: {alt_pdf[:80]}")
                        else:
                            print(f"      [DEBUG PDF] HTML 재시도 실패 → PDF 아님")
                            return ""
                    except Exception as e:
                        print(f"      [DEBUG PDF] HTML 재시도 예외: {str(e)[:50]}")
                        return ""
            
            # 파일명을 고유하게 생성 (동시 접근 방지)
            import uuid
            temp_file = f"temp_{uuid.uuid4().hex[:8]}.pdf"
            
            try:
                with open(temp_file, "wb") as f:
                    f.write(res.content)
                
                with fitz.open(temp_file) as pdf:
                    text = ""
                    total = len(pdf)
                    pages = list(range(min(5, total))) + list(range(max(0, total - 3), total))
                    for p in sorted(set(pages)):
                        text += pdf[p].get_text()
                
                print(f"      [DEBUG PDF] 추출 성공: {len(text)}자")
                
                # 파일 닫힌 후 삭제
                import time
                time.sleep(0.1)  # 파일 핸들 해제 대기
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
                return re.sub(r"\s+", " ", text.strip())[:3500]
            except Exception as pdf_error:
                print(f"      [DEBUG PDF] 파싱 실패: {pdf_error}")
                return ""
        except Exception as e:
            print(f"      [PDF 추출 실패: {e}]")
            return ""
    
    def _extract_html_text(self, url: str) -> str:
        """PDF가 없을 경우 HTML 본문 크롤링 (Selenium으로 JS 렌더링된 페이지)"""
        try:
            print(f"      [DEBUG HTML] URL: {url[:80]}")
            # Selenium으로 JS 렌더링된 본문 가져오기
            driver = create_selenium_driver()
            driver.get(url)
            time.sleep(3)  # JS 로딩 대기
            
            # iframe이 있는 경우 내부 문서 접근 (이중 iframe 탐색)
            try:
                iframes = driver.find_elements("tag name", "iframe")
                if iframes:
                    driver.switch_to.frame(iframes[0])
                    time.sleep(1)
                    # 이중 iframe 확인
                    inner_iframes = driver.find_elements("tag name", "iframe")
                    if inner_iframes:
                        driver.switch_to.frame(inner_iframes[0])
                        time.sleep(1)
                    html = driver.page_source
                    driver.switch_to.default_content()
                else:
                    html = driver.page_source
            except Exception:
                # iframe 전환 실패 시 기본 페이지 사용
                html = driver.page_source
            
            driver.quit()
            
            soup = BeautifulSoup(html, "html.parser")
            
            # 네이버 리포트 페이지 구조에 맞춰 본문 추출
            # 주요 섹션 선택자들 (td 우선순위 상향)
            content_selectors = [
                "td.view_content",     # 테이블 셀 본문 (경제/산업 분석 우선)
                "table.view",          # 테이블 뷰
                "div.view_con",        # 네이버 리포트 본문
                "div.tb_view",         # 테이블 형식 추가
                "div.article_view", 
                "div.article_view_con",
                "div.tb_type1",        # 테이블 형식
                "div.tb_cont",         # 테이블 컨텐츠
                "div.board_view",      # 게시판 형식
                "article",
                "div.content",
                "#content"
            ]
            
            text = ""
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(separator="\n").strip()
                    print(f"      [DEBUG HTML] 선택자 '{selector}'로 {len(text)}자 추출")
                    break
            
            # 위 선택자로 못 찾으면 전체 본문에서 불필요한 부분 제거
            if not text or len(text) < 100:  # 200자 → 100자로 완화
                print(f"      [DEBUG HTML] 선택자로 추출 실패, fallback 시도")
                # 스크립트, 스타일 제거
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n").strip()
                
                # 여전히 짧으면 p, td, div 태그에서 긴 텍스트 찾기
                if not text or len(text) < 100:  # 200자 → 100자로 완화
                    for tag in soup.find_all(["p", "td", "div"]):
                        tag_text = tag.get_text(separator=" ").strip()
                        if len(tag_text) > 100 and not re.search(r"네이버|삭제|오류|주식거래", tag_text, re.IGNORECASE):
                            text = tag_text
                            print(f"      [DEBUG HTML] fallback으로 {len(text)}자 추출")
                            break
            
            # 광고/네비게이션 텍스트 필터링
            text = re.sub(r"\s+", " ", text.strip())
            
            # 404 에러 페이지 체크
            error_patterns = [
                r"방문하시려는 페이지의 주소가 잘못",
                r"페이지의 주소가 변경",
                r"삭제되었거나",
                r"네이버 :: 세상의 모든 지식",
            ]
            
            for pattern in error_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return ""  # 에러 페이지는 빈 텍스트 반환
            
            # 유효한 본문인지 판단 (최소 50자 이상으로 완화)
            if len(text) < 50:
                print(f"      [DEBUG HTML] 본문이 너무 짧음: {len(text)}자")
                return ""
            
            # 광고 패턴 체크 (더 정교하게)
            ad_patterns = [
                r"네이버 주식거래연결.*빠른 주문.*도와드립니다",  # 연결된 광고 텍스트
                r"^.{0,100}주석.*결론.*참고.*$",  # 너무 짧은 반복 패턴
            ]
            
            for pattern in ad_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
                if matches and len(text) < 500:
                    # 광고 텍스트가 주요 내용이고 전체가 짧으면 제외
                    return ""
            
            # 최종 정제 및 길이 제한 (3500자로 확장)
            text = text[:3500]
            print(f"      [DEBUG HTML] 최종 추출 성공: {len(text)}자")
            return text
        except Exception as e:
            print(f"      [HTML 추출 실패: {e}]")
            import traceback
            traceback.print_exc()
            return ""
    
    def _summarize_report(self, report: dict, idx: int, total: int) -> dict:
        """단일 리포트 요약 (gpt-4o-mini 사용)"""
        title = report["title"]
        company = report["company"]
        category = report["category"]
        pdf_url = report.get("pdf_url")
        url = report.get("url")
        
        # PDF 또는 HTML 텍스트 추출
        text = ""
        source_type = "없음"
        
        if pdf_url:
            text = self._extract_pdf_text(pdf_url)
            if text:
                source_type = "PDF"
        
        if not text and url:
            text = self._extract_html_text(url)
            if text:
                source_type = "HTML"
        
        # GPT 요약 (gpt-4o-mini)
        text_preview = text[:2000] if text else '[본문 없음]'
        
        # 디버그 로그 (상세) - ASCII로만 출력
        if text:
            text_safe = text[:60].encode('ascii', 'ignore').decode('ascii')
            print(f"      [{source_type}] {len(text)}자: {text_safe}...")
        else:
            title_safe = title[:40].encode('ascii', 'ignore').decode('ascii')
            print(f"\n[DIAG] {title_safe}")
            if pdf_url:
                print(f"   -> PDF URL: {pdf_url[:80]}")
            if url:
                print(f"   -> HTML URL: {url[:80]}")
            print(f"   -> 원인: PDF와 HTML 둘 다 시도했으나 본문 추출 실패")
        
        # 본문 없으면 제목과 카테고리 기반으로만 요약
        if not text:
            prompt = f"""아래 리포트 제목과 카테고리만 보고 핵심을 1문장으로 추정하라.
제목: {title}
증권사: {company}
카테고리: {category}
요약 (유추된 주요 내용 1문장):"""
        else:
            prompt = f"""아래 리포트를 읽고 핵심만 1문장으로 압축하라.
제목: {title}
증권사: {company}
본문: {text_preview}
요약 (기업명+투자포인트 포함):"""
        try:
            resp = client.chat.completions.create(
                model=LLM_SUMMARY,
                messages=[
                    {"role": "system", "content": "핵심만 1문장으로 요약"},
                    {"role": "user", "content": prompt}
                ]
            )
            summary = resp.choices[0].message.content.strip()
        except Exception as e:
            summary = f"[요약 실패: {e}]"
        
        title_safe = title[:35].encode('ascii', 'ignore').decode('ascii')
        company_safe = company.encode('ascii', 'ignore').decode('ascii')
        print(f"[OK] [{idx+1}/{total}] {title_safe}... ({company_safe})")
        return {"title": title, "company": company, "category": category, "summary": summary}
    
    def _run(self, reports_str: str) -> str:
        """전체 리포트 전수 요약 (병렬 처리)"""
        reports = eval(reports_str)
        total_reports = len(reports)
        print(f"\n[INFO] 총 {total_reports}개 리포트 전수 요약 시작 (병렬 처리)")
        
        summaries = []
        # 병렬 실행 (최대 8개 스레드)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self._summarize_report, r, i, total_reports): i
                for i, r in enumerate(reports)
            }
            for future in as_completed(futures):
                summaries.append(future.result())
                time.sleep(0.1)
        
        print(f"\n[OK] 총 {len(summaries)}개 리포트 요약 완료")
        return str(summaries)

# ----------------------------------------------------------
# 4️⃣ 최종 브리핑
# ----------------------------------------------------------
class FinalBriefingTool(BaseTool):
    name: str = "Final Briefing Tool"
    description: str = "각 리포트 요약을 종합해 투자 브리핑 작성"
    
    def _run(self, summaries_str: str, analysis_str: str) -> str:
        """최종 브리핑 생성"""
        summaries = eval(summaries_str)
        analysis = eval(analysis_str)
        
        # 카테고리별로 리포트 그룹화
        by_category = {}
        for s in summaries:
            cat = s.get('category', '기타')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(s)
        
        # 카테고리별 요약 정리
        category_summaries = []
        for cat in ['투자정보', '종목분석', '산업분석', '경제분석']:
            if cat in by_category:
                reports = by_category[cat]
                summary_texts = [f"- {r['summary']} ({r['company']})" for r in reports]
                category_summaries.append(f"\n### {cat} ({len(reports)}건)\n" + "\n".join(summary_texts))
        
        prompt = f"""위 리포트들을 카테고리별로 분석하여 투자자용 일일 브리핑을 작성하라.

**중요: 모든 리포트의 핵심 내용을 빠짐없이 포함해야 함. 하나의 리포트라도 놓치면 안 됨.**

{''.join(category_summaries)}

[키워드 분석]
{analysis.get("top_keywords", "N/A")}

---
**응답 형식:**

## 1. 카테고리별 요약
**각 리포트별로 명시:**
- 어떤 기업/산업을 다루는가
- 리포트의 핵심 평가/전망은 무엇인가
- 투자 의견은 무엇인가 (목표가 상향/하향, 매수/중립/매도)

1) 투자정보 리포트 요약 (모든 리포트 포함)
2) 종목분석 리포트 요약 (모든 리포트 포함)
3) 산업분석 리포트 요약 (모든 리포트 포함)
4) 경제분석 리포트 요약 (모든 리포트 포함)

## 2. 핵심 테마 (5~8개 종목/산업)
구체적 내용 반영

## 3. 투자 시사점 (3~4줄)
각 테마별 투자 포인트, 리스크, 기회

## 4. 주목 포인트 (3~5개)
실적 발표일정, 수주 공시, 주요 지표 발표일 등

**절대 금지:**
- "원하시면", "추가로 제공" 같은 질문
- 마무리 문구
- 리포트 일부만 언급하고 생략하는 것
위 형식만 작성"""
        
        try:
            resp = client.chat.completions.create(
                model=LLM_BRIEFING,
                messages=[
                    {"role": "system", "content": "20년차 금융 애널리스트. 각 리포트의 핵심을 정확히 추출하여 실무 투자자 관점에서 실질적인 인사이트를 제공하는 브리핑 작성. 불필요한 질문이나 마무리 문구는 절대 포함하지 않음."},
                    {"role": "user", "content": prompt}
                ]
            )
            body = resp.choices[0].message.content.strip()
        except Exception as e:
            body = f"[브리핑 생성 실패: {e}]"
        
        header = f"# {today_file} 일일 증권사 리포트 브리핑\n\n*총 {analysis['total_reports']}건 기반 / {today_display} 발행*\n\n"
        return header + body

# ----------------------------------------------------------
# 5️⃣ Notion 업로드
# ----------------------------------------------------------
class NotionUploadTool(BaseTool):
    name: str = "Notion Upload Tool"
    description: str = "최종 브리핑과 분석결과를 Notion DB에 업로드"
    
    def _run(self, briefing_text: str, analysis_str: str) -> str:
        """Notion에 업로드"""
        try:
            analysis = eval(analysis_str)
            total_reports = analysis.get("total_reports", 0)
            
            page_data = {
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": f"{today_file} 일일 브리핑"}}]},
                    "Date": {"date": {"start": today_file}},
                    "총 리포트 수": {"number": total_reports},
                    "Top Keywords": {"rich_text": [{"text": {"content": analysis.get("top_keywords", "")[:2000]}}]},
                    "Category Summary": {"rich_text": [{"text": {"content": str(analysis.get("category_summary", {}))[:2000]}}]},
                },
                "children": []
            }
            
            # 브리핑 본문을 children으로 추가
            for i in range(0, len(briefing_text), 1800):
                page_data["children"].append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": briefing_text[i:i+1800]}}]
                    }
                })
            
            res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=page_data)
            if not res.ok:
                return f"⚠️ Notion 업로드 실패: {res.status_code} - {res.text}"
            res.raise_for_status()
            parent_id = res.json().get("id", "")
            return f"[OK] Notion 업로드 완료 (Page ID: {parent_id})"
        except Exception as e:
            return f"⚠️ Notion 업로드 실패: {e}"

# ----------------------------------------------------------
# 6️⃣ 실행
# ----------------------------------------------------------
def run_daily_briefing():
    """전체 파이프라인 실행"""
    print(f"[START] {today_display} Daily Briefing 시작 (v9.0 - 전수 분석)")
    
    # 1. 리포트 수집
    print("\n[1/5] 리포트 수집 중...")
    naver_tool = NaverResearchScraperTool()
    hankyung_tool = HankyungScraperTool()
    naver_reports = eval(naver_tool._run())
    hankyung_reports = eval(hankyung_tool._run())
    all_reports = naver_reports + hankyung_reports
    
    if len(all_reports) == 0:
        print("[INFO] 리포트 없음")
        return "[INFO] 없음"
    
    print(f"\n[OK] 총 {len(all_reports)}개 리포트 수집 완료\n")
    
    # 2. 분석
    print("[2/5] 키워드 분석 중...")
    analyzer = PythonAnalyzerTool()
    analysis = eval(analyzer._run(str(all_reports)))
    print(f"   [OK] 키워드: {analysis['top_keywords'][:100]}...")
    
    # 3. 리포트별 요약
    print("\n[3/5] 리포트 요약 중...")
    summarizer = ReportSummarizerTool()
    summaries = eval(summarizer._run(str(analysis["reports"])))
    
    # 4. 브리핑 생성
    print("\n[4/5] 최종 브리핑 생성 중...")
    briefing_tool = FinalBriefingTool()
    briefing = briefing_tool._run(str(summaries), str(analysis))
    print(f"   [OK] 브리핑 생성 완료 ({len(briefing)} 자)")
    
    # 5. Notion 업로드
    print("\n[5/5] Notion 업로드 중...")
    notion_tool = NotionUploadTool()
    result = notion_tool._run(briefing, str(analysis))
    print(f"   {result}")
    
    print("\n[COMPLETE] 모든 작업 완료!")
    return briefing

if __name__ == "__main__":
    weekday = datetime.today().weekday()
    IS_TEST_MODE = False  # 프로덕션 모드 (주말 스킵)
    
    if weekday >= 5 and not IS_TEST_MODE:
        print(f"[SKIP] 주말 스킵 ({today_display})")
    else:
        if IS_TEST_MODE and weekday >= 5:
            print(f"\n[TEST MODE] 주말이지만 테스트 모드로 실행합니다.\n오늘: {today_display}")
        
        result = run_daily_briefing()
        
        print("\n" + "=" * 60)
        print("최종 브리핑 미리보기:")
        print("=" * 60)
        print(result[:800] + "..." if len(result) > 800 else result)
