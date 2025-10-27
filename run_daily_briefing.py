# ==========================================================
# CrewAI Daily Briefing v11.2 (통합 개선 안정화 버전 - 사실 기반 정리 강화)
# Phase 1 (긴급): PDF 필터 강화, 신한투자 HTML 검증, 인코딩 수정
# Phase 2 (구조): Mobile UA 전역화, meta refresh 추적(재시도 제한), iframe JS 처리
# Phase 3 (최적화): PDF 캐싱, 중복 제거, 로깅 개선
# v11.1: PDF URL whitelist 검증, HTML fallback 강화, 인코딩 순서 수정
# v11.2: LLM 추론 최소화, 리포트 원문 정보 중심 정리로 변경
# ==========================================================
import sys
import os  # 인코딩 설정 전에 먼저 import
import hashlib  # Phase 3: PDF 캐싱용
import logging  # Phase 3: 로깅 개선용
import json  # Phase 3: 캐시 저장용

# Windows Unicode 인코딩 강제 설정 (Phase 1)
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"  # 추가 UTF-8 강제
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import re, time, fitz, requests, pandas as pd
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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin  # v10.4: URL 정규화

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

# 프로덕션 모드: 오늘 날짜만 수집
TEST_MODE_RECENT_DAYS = False  # True: 최근 3일 (테스트), False: 오늘만 (프로덕션)
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
# 🌐 Selenium 설정 (Phase 2: Mobile UA 전역 적용)
# ----------------------------------------------------------
# Phase 2: Mobile User-Agent 전역 적용 (신한투자 JS 페이지 대응)
MOBILE_USER_AGENT = ("Mozilla/5.0 (Linux; Android 10; SM-G973F) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Mobile Safari/537.36")

def create_selenium_driver(force_mobile=False):
    """Selenium 드라이버 생성 (Phase 2: Mobile UA 옵션)"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Phase 2: Mobile UA 조건부 적용
    if force_mobile:
        chrome_options.add_argument(f"user-agent={MOBILE_USER_AGENT}")
        print(f"      [DEBUG] Mobile User-Agent 적용")
    else:
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
                    
                    # v10.7: 블랙리스트 방식으로 변경 (금지된 패턴만 차단)
                    # 종목분석은 /item/ 허용 (종목 페이지로 링크가 가더라도 PDF는 첨부 컬럼에 있음)
                    excluded_patterns = ["/chart/", "/quote/", "/news/"]  # /item/, /frgn/ 제거
                    if cat != "종목분석":  # 종목분석이 아니면 /item/도 차단
                        excluded_patterns.append("/item/")
                        excluded_patterns.append("/frgn/")

                    if any(pattern in href for pattern in excluded_patterns):
                        # 종목/차트 페이지는 스킵하되 로그 출력
                        if i < 3:  # 처음 3개만 디버그 출력
                            print(f"      [DEBUG] 금지된 URL 패턴 감지, 스킵: {href[:60]}...")
                        continue
                    
                    # v10.8: 종목분석 카테고리 필터 제거
                    # (종목분석은 /item/ 링크를 허용하고, PDF는 첨부 컬럼에서 직접 찾음)

                    # v10.4: URL 정규화 (urljoin으로 절대 경로 강제 변환)
                    detail_url = urljoin("https://finance.naver.com", href)
                    
                    # PDF URL 추출: 목록에서 직접 찾기 (V9.3 방식)
                    pdf_url = None
                    try:
                        # 모든 컬럼 순회하며 PDF 링크 찾기
                        for col_idx, col in enumerate(cols):
                            # 1. <a> 태그에서 href 찾기
                            pdf_link = col.find("a", href=re.compile(r"\.pdf|download|filekey|attach|report|view", re.IGNORECASE))
                            if pdf_link:
                                href = pdf_link.get("href", "")
                                if href:
                                    pdf_url = urljoin("https://finance.naver.com", href)
                                    print(f"      [DEBUG PDF] 첨부 링크 발견 (컬럼 {col_idx})")
                                    print(f"      [DEBUG PDF] 목록에서 PDF 링크 발견: {pdf_url[:80]}...")
                                    break
                            
                            # 2. 이미지 alt/title에서 PDF 확인
                            img = col.find("img")
                            if img and ("pdf" in (img.get("alt", "") + img.get("title", "")).lower()):
                                # 부모 <a> 찾기
                                parent_a = col.find("a")
                                if parent_a:
                                    href = parent_a.get("href", "")
                                    if href:
                                        pdf_url = urljoin("https://finance.naver.com", href)
                                        print(f"      [DEBUG PDF] 첨부 이미지 발견 (컬럼 {col_idx})")
                                        print(f"      [DEBUG PDF] 목록에서 PDF 링크 발견: {pdf_url[:80]}...")
                                        break
                            
                            # 3. svg 아이콘 확인
                            svg = col.find("svg")
                            if svg:
                                parent_a = col.find("a")
                                if parent_a:
                                    href = parent_a.get("href", "")
                                    if href and (".pdf" in href.lower() or "download" in href.lower() or "filekey" in href.lower()):
                                        pdf_url = urljoin("https://finance.naver.com", href)
                                        print(f"      [DEBUG PDF] 첨부 아이콘 발견 (컬럼 {col_idx})")
                                        print(f"      [DEBUG PDF] 목록에서 PDF 링크 발견: {pdf_url[:80]}...")
                                        break
                        
                        # 신한투자증권 리포트 체크: PDF가 없으면 상세 페이지 본문만 사용
                        if not pdf_url and "신한" in company:
                            # v10.7: URL 유효성 체크 후 리포트 수집 (스킵 제거)
                            if not detail_url or ("read.naver" not in detail_url and "/research/" not in detail_url):
                                print(f"      [INFO] 신한투자증권 리포트: URL 유효하지 않음 (PDF/HTML 모두 시도)")
                            else:
                                print(f"      [INFO] 신한투자증권 리포트: 상세 페이지 본문만 사용 (PDF URL 없음)")
                            print(f"      [WARN] PDF URL 없음: {title_tag.get_text(strip=True)[:30]}...")
                        
                        # PDF가 없는 경우 상세 페이지에서 추가 시도
                        if not pdf_url:
                            try:
                                d_res = requests.get(detail_url, headers=HEADERS, timeout=5)
                                d_soup = BeautifulSoup(d_res.text, "html.parser")
                                
                                # 다양한 패턴 시도
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
                                    print(f"      [DEBUG PDF] 상세 페이지에서 PDF 발견: {pdf_url[:80]}...")
                            except:
                                pass
                    except Exception as e:
                        pdf_url = None
                    
                    # v11.1: PDF가 없으면 detail_url을 HTML 소스로 사용 (HTML fallback)
                    # URL 유효성 검사
                    valid_url = detail_url
                    if not detail_url or not detail_url.startswith("http"):
                        valid_url = None
                    
                    # PDF가 없는 경우, HTML URL로 사용 (신한투자 등 HTML 리포트 대응)
                    if not pdf_url:
                        # detail_url을 HTML URL로 사용
                        if detail_url and ("read.naver" in detail_url or "/research/" in detail_url):
                            valid_url = detail_url
                        elif valid_url and "/item/" in valid_url:
                            # /item/은 종목 페이지이므로 제외
                            valid_url = None
                    else:
                        # PDF가 있으면 /item/ 패턴 제외
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
        """PDF 본문 추출 (v11.1: PDF URL whitelist 검증 강화)"""
        try:
            # PDF URL 유효성 검증
            if not pdf_url or not isinstance(pdf_url, str):
                return ""
            
            # v11.1: PDF URL whitelist 기반 검증 (먼저 whitelist 확인)
            valid_pdf_patterns = [
                r'stock\.pstatic\.net/stock-research/.*\.pdf',
                r'pstatic\.net/stock-research/.*\.pdf',
            ]
            is_valid = any(re.search(p, pdf_url) for p in valid_pdf_patterns)
            if not is_valid:
                print(f"      [DEBUG PDF] whitelist 불일치, PDF로 인정 불가: {pdf_url[:80]}")
                return ""  # whitelist에 없으면 PDF가 아님
            
            # Phase 1 (v11.0): 종목/차트 페이지 강력 차단 (URL 패턴으로 선차단)
            invalid_patterns = [
                r'/(item|chart|quote|news|frgn)/',       # 기존 패턴
                r'finance\.naver\.com/item/',            # 네이버 종목 페이지
                r'\.frgn\.naver',                        # 외국인 페이지
                r'/item/frgn',                           # 종목 외국인 페이지
            ]
            
            for pattern in invalid_patterns:
                if re.search(pattern, pdf_url, re.I):
                    print(f"      [DEBUG PDF] 금지된 URL 패턴 감지: {pdf_url[:80]}")
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
                
                # v10.5: 보정 실패한 .p, .pd는 차단
                if pdf_url.endswith(".p") or pdf_url.endswith(".pd"):
                    print(f"      [DEBUG PDF] 보정 실패, 잘린 확장자 차단: {pdf_url[:80]}")
                    return ""
                
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
    
    def _extract_html_text(self, url: str, company: str = "") -> str:
        """PDF가 없을 경우 HTML 본문 크롤링 (Selenium으로 JS 렌더링된 페이지) - v10.0"""
        try:
            print(f"      [DEBUG HTML] URL: {url[:80]}")
            # Selenium으로 JS 렌더링된 본문 가져오기
            driver = create_selenium_driver()
            driver.implicitly_wait(5)  # 대기 시간 증가
            driver.get(url)
            time.sleep(3)  # JS 로딩 대기
            
            # v10.4: 404 에러 페이지 감지 강화 (다중 인코딩)
            page_title = driver.title
            page_size = len(driver.page_source)
            print(f"      [DEBUG HTML] 페이지 타이틀: {page_title}")
            print(f"      [DEBUG HTML] 페이지 크기: {page_size} 자")
            
            # 다중 인코딩 검사 (EUC-KR + UTF-8)
            page_raw = driver.page_source
            try:
                page_euckr = page_raw.encode('euc-kr', errors='ignore').decode('euc-kr', errors='ignore')
            except:
                page_euckr = page_raw
            
            # v10.9: 404 감지 단순화 (과도한 필터링 제거)
            is_404 = any(keyword in page_raw for keyword in [
                "페이지를 찾을 수 없습니다",
                "찾으시는 모든 정보",
                "404 Not Found"
            ]) or ("404" in page_title and "네이버" in page_title)
            
            # Phase 2 (v11.0): meta refresh 추적 + 재시도 제한 (무한 루프 방지)
            redirect_count = 0
            max_redirects = 3
            visited_urls = set()  # 무한 루프 방지: 방문한 URL 저장
            
            while not is_404 and redirect_count < max_redirects:
                try:
                    current_url = driver.current_url
                    
                    # 무한 루프 감지: 같은 URL을 다시 방문하면 중단
                    if current_url in visited_urls:
                        print(f"      [DEBUG HTML] 무한 루프 감지 (동일 URL 재방문): {current_url[:80]}")
                        break
                    visited_urls.add(current_url)
                    
                    soup_page = BeautifulSoup(driver.page_source[:10000], "html.parser")
                    meta_refresh = soup_page.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
                    
                    if meta_refresh and "url=" in meta_refresh.get("content", "").lower():
                        content = meta_refresh.get("content", "")
                        redirect_url_match = re.search(r'url=([^";\s]+)', content, re.I)
                        
                        if redirect_url_match:
                            redirect_url = redirect_url_match.group(1).strip()
                            if not redirect_url.startswith("http"):
                                redirect_url = urljoin(current_url, redirect_url)
                            
                            # 다음 URL이 이미 방문한 URL이면 중단 (무한 루프 방지)
                            if redirect_url in visited_urls:
                                print(f"      [DEBUG HTML] 무한 루프 감지 (이미 방문한 URL): {redirect_url[:80]}")
                                break
                            
                            print(f"      [DEBUG HTML] meta refresh {redirect_count+1}회: {redirect_url[:80]}")
                            driver.get(redirect_url)
                            time.sleep(2)
                            redirect_count += 1
                            continue
                    
                    # meta refresh 없으면 루프 종료
                    break
                    
                except Exception as redirect_e:
                    print(f"      [DEBUG HTML] 리다이렉트 오류: {str(redirect_e)[:50]}")
                    break
            
            if is_404:
                print(f"      [ERROR] 404 에러 페이지 감지: {url}")
                # 404 페이지 디버깅 저장
                if "신한" in company:
                    html_content = driver.page_source
                    if not os.path.exists("debug_html"):
                        os.makedirs("debug_html")
                    safe_company = re.sub(r'[^\w\s-]', '', company)[:20]
                    debug_file = f"debug_html/404_{safe_company}_{int(time.time())}.html"
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    print(f"      [DEBUG HTML] 404 페이지 저장: {debug_file}")
                driver.quit()
                return ""
            
            # === v10.4: 디버그 HTML 저장 (신한투자 전용, 정상 페이지만) ===
            if "신한" in company:
                html_content = driver.page_source
                if not os.path.exists("debug_html"):
                    os.makedirs("debug_html")
                safe_company = re.sub(r'[^\w\s-]', '', company)[:20]
                debug_file = f"debug_html/ok_{safe_company}_{int(time.time())}.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"      [DEBUG HTML] 정상 페이지 저장: {debug_file}")
                print(f"      [DEBUG HTML] 페이지 크기: {len(html_content)} 자")
            
            # 신한투자 특화 선택자 처리 (나중에 사용)
            if False:  # 임시 비활성화
                print(f"      [DEBUG HTML] 신한투자증권 리포트 감지 (company: {company})")
                content_selectors = [
                    # 신한투자 특화 선택자 (우선순위 높게)
                    "div.view_cont",      # 신한투자 본문 컨테이너
                    "td.view_cont",       # 신한투자 테이블 셀
                    "div.article_content", # 기사 본문
                    "div.content_body",   # 본문 영역
                    "div#content_detail", # 상세 본문 ID
                    "div.report_view",    # 리포트 뷰
                    "div.article_view",   # 기사 뷰
                    # 네이버 표준 선택자
                    "td.view_cnt",
                    "div.view_cnt",
                    "td.view_content",
                    "table.view",
                    "div.view_con",
                    # 일반 선택자
                    "div.report-content",
                    "div.report-body",
                    "div.viewer-content",
                    "div.article-content",
                    "td.content",
                    "div.content",
                    "#articleBody",
                    "article"
                ] + content_selectors
            
            # iframe이 있는 경우 내부 문서 접근 (v10.0: 다중 방법 탐색)
            html = None
            try:
                # v10.0: 다중 방법으로 iframe 탐색
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                
                # 방법 2: XPath로 iframe 찾기
                if not iframes:
                    iframes = driver.find_elements(By.XPATH, "//iframe")
                
                # 방법 3: CSS 선택자로 iframe 찾기
                if not iframes:
                    iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[id*='view'], iframe[src]")
                
                # 방법 4: frame 태그도 찾기
                if not iframes:
                    iframes = driver.find_elements(By.TAG_NAME, "frame")
                
                print(f"      [DEBUG HTML] iframe 탐색 완료: {len(iframes)}개 발견")
                
                if iframes:
                    print(f"      [DEBUG HTML] iframe {len(iframes)}개 발견")
                    
                    # iframe 순회하며 본문 찾기
                    for idx, frame in enumerate(iframes):
                        try:
                            # v10.9: 신한투자 iframe 직접 접근 + Mobile UA 적용
                            src = frame.get_attribute("src")
                            if src and "shinhaninvest" in src.lower():
                                print(f"      [DEBUG HTML] 신한 iframe src 감지: {src[:80]}")
                                
                                # Mobile User-Agent로 전환
                                mobile_ua = ("Mozilla/5.0 (Linux; Android 10; SM-G973F) "
                                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                                           "Chrome/124.0.0.0 Mobile Safari/537.36")
                                driver.execute_cdp_cmd("Network.setUserAgentOverride", 
                                                      {"userAgent": mobile_ua})
                                print(f"      [DEBUG HTML] Mobile UA 적용")
                                
                                driver.get(src)  # iframe src로 직접 이동
                                time.sleep(2)
                                html = driver.page_source
                                if len(html) > 1000:
                                    break
                                
                                # 원래 페이지로 복귀
                                driver.execute_cdp_cmd("Network.setUserAgentOverride", 
                                                      {"userAgent": HEADERS['User-Agent']})
                                driver.back()
                                time.sleep(1)
                                continue
                            
                            # 기존 프레임 전환 방식 (fallback)
                            driver.switch_to.frame(frame)
                            time.sleep(2)  # iframe 렌더링 대기 (1초 → 2초)
                            
                            # 내부 iframe 확인 (이중 구조)
                            inner_iframes = driver.find_elements("tag name", "iframe")
                            if inner_iframes:
                                print(f"      [DEBUG HTML] 내부 iframe {len(inner_iframes)}개 발견")
                                for inner_idx, inner_frame in enumerate(inner_iframes):
                                    try:
                                        driver.switch_to.frame(inner_frame)
                                        time.sleep(2)  # 내부 iframe 렌더링 대기
                                        
                                        # iframe 내부 HTML 가져오기
                                        candidate_html = driver.page_source
                                        
                                        # 본문 유효성 검사
                                        if len(candidate_html) > 1000:
                                            # 본문 키워드 확인
                                            if any(keyword in candidate_html for keyword in ["경쟁사", "이익률", "매출", "전망", "증권", "리포트"]):
                                                print(f"      [DEBUG HTML] 내부 iframe #{inner_idx} 본문 확인: {len(candidate_html)}자")
                                                html = candidate_html
                                                break
                                        
                                        driver.switch_to.parent_frame()
                                    except Exception as inner_e:
                                        print(f"      [DEBUG HTML] 내부 iframe #{inner_idx} 전환 실패: {str(inner_e)[:50]}")
                                        try:
                                            driver.switch_to.parent_frame()
                                        except:
                                            pass
                                        continue
                            
                            # 내부 iframe에서 본문 못 찾았으면 외부 iframe에서 시도
                            if not html or len(html) < 1000:
                                candidate_html = driver.page_source
                                if len(candidate_html) > 1000:
                                    if any(keyword in candidate_html for keyword in ["경쟁사", "이익률", "매출", "전망", "증권", "리포트"]):
                                        print(f"      [DEBUG HTML] 외부 iframe #{idx} 본문 확인: {len(candidate_html)}자")
                                        html = candidate_html
                            
                            # 성공하면 탈출
                            if html and len(html) > 1000:
                                driver.switch_to.default_content()
                                break
                            
                            # 기본 프레임으로 복귀
                            driver.switch_to.default_content()
                            
                        except Exception as frame_e:
                            print(f"      [DEBUG HTML] iframe #{idx} 전환 실패: {str(frame_e)[:50]}")
                            try:
                                driver.switch_to.default_content()
                            except:
                                pass
                            continue
                    
                    # iframe 전환 실패 시 기본 페이지 사용
                    if not html or len(html) < 1000:
                        driver.switch_to.default_content()
                        html = driver.page_source
                        print(f"      [DEBUG HTML] iframe 실패, 기본 페이지 사용: {len(html)}자")
                else:
                    html = driver.page_source
                    print(f"      [DEBUG HTML] iframe 없음, 기본 페이지 사용: {len(html)}자")
                    
            except Exception as iframe_error:
                print(f"      [DEBUG HTML] iframe 처리 오류: {str(iframe_error)[:50]}")
                try:
                    driver.switch_to.default_content()
                except:
                    pass
                html = driver.page_source
            
            driver.quit()
            
            soup = BeautifulSoup(html, "html.parser")
            
            # 네이버 리포트 페이지 구조에 맞춰 본문 추출
            # 주요 섹션 선택자들 (확장 버전)
            content_selectors = [
                "td.view_cnt",         # 네이버 리포트 본문 컨테이너 (핵심 선택자)
                "div.view_cnt",        # div 형태의 본문 컨테이너
                "td.view_content",     # 테이블 셀 본문 (경제/산업 분석 우선)
                "table.view",          # 테이블 뷰
                "div.view_con",        # 네이버 리포트 본문
                "div.tb_view",         # 테이블 형식 추가
                "div.article_view", 
                "div.article_view_con",
                "section.article",     # 섹션 기반 본문
                "div#articleBody",     # 본문 영역 ID
                "div#wrap_view",       # 뷰 래퍼
                "div#wrapContent",     # 컨텐츠 래퍼
                "div#contentArea",     # 컨텐츠 영역
                "div.article_body",    # 기사 본문
                "div.end_body",        # 본문 끝 부분
                "div.tb_type1",        # 테이블 형식
                "div.tb_cont",         # 테이블 컨텐츠
                "div.board_view",      # 게시판 형식
                "article",
                "div.content",
                "#content"
            ]
            
            # 신한투자증권 전용 선택자 추가 (company 파라미터 사용)
            if "신한" in company:
                print(f"      [DEBUG HTML] 신한투자증권 리포트 감지 (company: {company})")
                content_selectors = [
                    # 신한투자 특화 선택자 (우선순위 높게)
                    "div.view_cont",      # NEW: 신한투자 본문 컨테이너
                    "td.view_cont",       # NEW: 신한투자 테이블 셀
                    "div.article_content", # NEW: 기사 본문
                    "div.content_body",   # NEW: 본문 영역
                    "div#content_detail", # NEW: 상세 본문 ID
                    "div.report_view",    # NEW: 리포트 뷰
                    "div.article_view",   # NEW: 기사 뷰
                    # 네이버 표준 선택자
                    "td.view_cnt",
                    "div.view_cnt",
                    "td.view_content",
                    "table.view",
                    "div.view_con",
                    # 일반 선택자
                    "div.report-content",
                    "div.report-body",
                    "div.viewer-content",
                    "div.article-content",
                    "td.content",
                    "div.content",
                    "#articleBody",
                    "article"
                ] + content_selectors
            
            # v10.5: 빠른 선택자 기반 추출 (우선 시도)
            text = ""
            print(f"      [DEBUG HTML] 선택자 {len(content_selectors)}개 중 매칭 시도...")
            for idx, selector in enumerate(content_selectors[:5]):  # 처음 5개만 빠르게 시도
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(separator="\n").strip()
                    if len(text) > 100:
                        print(f"      [DEBUG HTML] OK 선택자 #{idx+1} '{selector}' 매칭 성공: {len(text)}자")
                        break
                    else:
                        text = ""  # 계속 시도
                else:
                    if idx < 3:
                        print(f"      [DEBUG HTML] FAIL 선택자 #{idx+1} '{selector}' 매칭 실패")
            
            # 선택자 실패 시 클래스 기반 검색 (v10.5 신규)
            if not text or len(text) < 100:
                print(f"      [DEBUG HTML] 선택자 실패, 클래스 기반 검색으로 fallback")
                text_blocks = soup.find_all(["td", "div"], class_=re.compile(r"view|content|article|report", re.I))
                texts = [t.get_text(strip=True) for t in text_blocks if len(t.get_text(strip=True)) > 100]
                if texts:
                    text = max(texts, key=len)
                    print(f"      [DEBUG HTML] 클래스 기반 검색 성공: {len(text)}자")
            
            # 위 선택자로 못 찾으면 전체 본문에서 불필요한 부분 제거
            if not text or len(text) < 100:  # 200자 → 100자로 완화
                if text:
                    print(f"      [DEBUG HTML] 선택자로 추출했지만 {len(text)}자밖에 안 됨, fallback 시도")
                else:
                    print(f"      [DEBUG HTML] 선택자 매칭 완전 실패, fallback 시도")
                # 스크립트, 스타일 제거
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n").strip()
                print(f"      [DEBUG HTML] fallback step1: 전체 텍스트 추출 → {len(text)}자")
                
                # 여전히 짧으면 모든 태그에서 가장 긴 텍스트 찾기 (개선)
                if not text or len(text) < 100:
                    print(f"      [DEBUG HTML] fallback step2: 전체 태그 중 가장 긴 텍스트 검색...")
                    longest_text = ""
                    longest_len = 0
                    
                    for tag in soup.find_all(["p", "td", "div", "article", "section", "span"]):
                        tag_text = tag.get_text(separator=" ").strip()
                        # 광고/네비게이션 패턴 필터링
                        if (len(tag_text) > longest_len and 
                            len(tag_text) >= 100 and 
                            not re.search(r"목록|조회|신한투자증권 리서치 탐색기|네이버|삭제|오류|주식거래", tag_text, re.IGNORECASE)):
                            longest_text = tag_text
                            longest_len = len(tag_text)
                    
                    if longest_text and longest_len >= 100:
                        text = longest_text
                        print(f"      [DEBUG HTML] fallback step2: 가장 긴 텍스트 발견 - {len(text)}자")
                    elif longest_text and longest_len >= 50 and "신한" in company:
                        # 신한투자는 50자 이상도 허용
                        text = longest_text
                        print(f"      [DEBUG HTML] fallback step2: 신한투자 본문 추출 - {len(text)}자")
                    else:
                        print(f"      [DEBUG HTML] fallback 실패: 최대 {longest_len}자만 발견됨")
            
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
            
            # 유효한 본문인지 판단 (신한투자는 50자, 일반은 100자 이상)
            min_length = 50 if "신한" in company else 100
            if len(text) < min_length:
                print(f"      [DEBUG HTML] 본문이 너무 짧음: {len(text)}자 (최소: {min_length}자)")
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
        
        # v10.5: 진단 로그 추가
        print(f"[TRACE] {idx+1}/{total} | {company} | {title[:40]}... | URLs: PDF={'O' if pdf_url else 'X'}, HTML={'O' if url else 'X'}")
        
        # PDF 또는 HTML 텍스트 추출
        text = ""
        source_type = "없음"
        
        if pdf_url:
            text = self._extract_pdf_text(pdf_url)
            if text:
                source_type = "PDF"
        
        if not text and url:
            text = self._extract_html_text(url, company=company)
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
        # v10.5: 병렬 실행 (HTML/iframe 접근은 부하 큼 → 워커 수 축소)
        with ThreadPoolExecutor(max_workers=4) as executor:
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
        
        prompt = f"""위 리포트 내용을 **정확하게 정리**하라. 모든 정보는 리포트 원문에서 추출한 내용만 사용하라.

**금지 사항:**
- LLM의 추론, 해석, 결론 도출
- "매수 권고" 등의 액션 제안
- 목표가/현재가 비교로 수익률 계산
- "30% 비중" 등의 비중 제안
- "매수가/익절가/손절가" 등 LLM 재창조

**필수: 리포트 원문 정보만 기록**

{''.join(category_summaries)}

[키워드 분석]
{analysis.get("top_keywords", "N/A")}

---
**응답 형식:**

## 1. 종목 분석 (종목별 정리)

### [종목명] (증권사: OO증권)
- **투자의견**: [BUY/SELL/HOLD 등 리포트 원문]
- **목표가**: [수치] ([상향/하향/유지] - 리포트에 명시된 경우만)
- **핵심 전망**:
  1. [리포트 원문 내용 그대로]
  2. [리포트 원문 내용 그대로]
  3. [추가 내용]
- **리스크 요인**: [리포트에 명시된 리스크만 그대로]

[모든 종목 동일 형식으로 나열]

---

## 2. 산업 분석 (산업별 정리)

### [산업명] (증권사: OO증권, OO증권 외 다수)
- **업황 전망**: [리포트 원문 내용]
- **핵심 이슈**:
  1. [리포트 원문 내용]
  2. [리포트 원문 내용]
- **증권사 의견**:
  - OO증권: "[증권사 원문 그대로]"
  - OO증권: "[증권사 원문 그대로]"

[모든 산업 동일 형식]

---

## 3. 거시·시장 전망 (전문가 의견 정리)

### 코스피 전망
- **OO증권**: [리포트 원문 내용 그대로]
- **OO증권**: [리포트 원문 내용 그대로]

### 환율·금리 전망
- **OO증권**: [리포트 원문 내용 그대로]
- **OO증권**: [리포트 원문 내용 그대로]

### 기타 거시 이슈
- [리포트 원문 내용 그대로 나열]

---

## 4. 중요 일정·체크포인트 (리포트 캘린더)

### 실적 발표 예정
- [종목명]: [리포트 원문 내용]

### 이벤트 일정
- [이벤트명]: [리포트 원문 내용]

### 주요 지표 발표일
- [지표명]: [리포트 원문 내용]

---

**작성 규칙:**
- 모든 정보는 리포트 원문에서 직접 추출
- "증권사: OO증권" 표기 필수
- 목표가, 투자의견 등 구체적 수치 그대로 기록
- LLM 추론/해석 금지, 사실 나열만
- "원하시면", "추가로 제공" 같은 질문 금지
- 마무리 문구 금지"""
        
        try:
            resp = client.chat.completions.create(
                model=LLM_BRIEFING,
                messages=[
                    {"role": "system", "content": "증권사 리포트 정보 정리 전문가. 리포트 원문 내용을 정확하게 정리만 한다. 추론, 해석, 결론 도출 금지. 모든 정보는 리포트 원문에서 직접 추출한 사실만 나열. 불필요한 질문이나 마무리 문구는 절대 포함하지 않음."},
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
# 6️⃣ 실행 (Phase 3: PDF 캐싱 추가)
# ----------------------------------------------------------
def load_pdf_cache():
    """Phase 3: PDF 캐시 로드"""
    cache_file = "pdf_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_pdf_cache(cache):
    """Phase 3: PDF 캐시 저장"""
    cache_file = "pdf_cache.json"
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 캐시 저장 실패: {e}")

def run_daily_briefing():
    """전체 파이프라인 실행 (Phase 3: PDF 캐싱 적용)"""
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    print(f"[START] {today_display} Daily Briefing 시작 (v11.2 - 사실 기반 정리)")
    
    # Phase 3: PDF 캐시 로드
    pdf_cache = load_pdf_cache()
    print(f"[INFO] PDF 캐시 로드: {len(pdf_cache)}건 저장됨")
    
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
    
    # 평일(0-4)에만 실행, 주말(5-6)은 스킵
    if weekday >= 5:
        print(f"[SKIP] 주말 스킵 - {today_display} ({'토요일' if weekday == 5 else '일요일'})")
    else:
        result = run_daily_briefing()
        
        print("\n" + "=" * 60)
        print("최종 브리핑 미리보기:")
        print("=" * 60)
        print(result[:800] + "..." if len(result) > 800 else result)
