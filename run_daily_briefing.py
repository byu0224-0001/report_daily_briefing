# ==========================================================
# v7-Final: CrewAI Daily Briefing (브리핑 복원 + Notion 자동 업로드)
# CrewAI 1.1.0+ 호환 버전
# ==========================================================
import os, re, time, fitz, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool

# ----------------------------------------------------------
# 0️⃣ 환경 설정
# ----------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
LLM_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
NOTION_HEADERS = {"Authorization": f"Bearer {NOTION_API_KEY}",
                  "Notion-Version": "2022-06-28",
                  "Content-Type": "application/json"}

today_display = datetime.now().strftime("%Y.%m.%d")
today_file = datetime.now().strftime("%Y-%m-%d")

# ----------------------------------------------------------
# 1️⃣ 네이버 / 한경 리포트 수집 Tool
# ----------------------------------------------------------
class NaverResearchScraperTool(BaseTool):
    name: str = "Naver Research Scraper"
    description: str = "네이버 금융 리서치 리포트 수집"
    
    def _run(self) -> str:
        """네이버 리서치 리포트 수집"""
        base_url = "https://finance.naver.com/research/"
        categories = {"투자정보": "invest_list.naver",
                      "종목분석": "company_list.naver",
                      "산업분석": "industry_list.naver",
                      "경제분석": "economy_list.naver"}
        reports = []
        for cat, path in categories.items():
            try:
                res = requests.get(base_url + path, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                for row in soup.select("table.type_1 tbody tr"):
                    cols = row.find_all("td")
                    if len(cols) < 4: continue
                    date = cols[3].get_text(strip=True)
                    if date != today_display: continue
                    title_tag = cols[1].find("a")
                    if not title_tag: continue
                    detail_url = "https://finance.naver.com" + title_tag["href"]
                    company = cols[2].get_text(strip=True)
                    pdf_url = None
                    try:
                        d_soup = BeautifulSoup(requests.get(detail_url, headers=HEADERS).text, "html.parser")
                        pdf_btn = d_soup.find("a", string=re.compile("리포트보기"))
                        if pdf_btn: pdf_url = "https://finance.naver.com" + pdf_btn["href"]
                    except: pass
                    reports.append({"source": "네이버", "category": cat, "title": title_tag.get_text(strip=True),
                                    "company": company, "date": date, "url": detail_url, "pdf_url": pdf_url})
                time.sleep(1)
            except Exception as e:
                print(f"⚠️ 네이버 {cat} 수집 실패: {e}")
        return str(reports)

class HankyungScraperTool(BaseTool):
    name: str = "Hankyung Consensus Scraper"
    description: str = "한경컨센서스 리포트 수집"
    
    def _run(self) -> str:
        """한경컨센서스 리포트 수집"""
        url = "https://consensus.hankyung.com/analysis/list"
        reports = []
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            for row in soup.select("table tbody tr"):
                cols = row.find_all("td")
                if len(cols) < 4: continue
                date = cols[3].get_text(strip=True).replace("-", ".")
                if date != today_display: continue
                title_tag = cols[0].find("a")
                pdf_tag = row.find("a", href=re.compile(r"\.pdf$"))
                pdf_url = "https://consensus.hankyung.com" + pdf_tag["href"] if pdf_tag else None
                reports.append({"source": "한경컨센서스", "category": cols[2].get_text(strip=True),
                                "title": title_tag.get_text(strip=True), "company": cols[1].get_text(strip=True),
                                "date": date, "url": "https://consensus.hankyung.com" + title_tag["href"],
                                "pdf_url": pdf_url})
                time.sleep(1)
        except Exception as e:
            print(f"⚠️ 한경 수집 실패: {e}")
        return str(reports)

# ----------------------------------------------------------
# 2️⃣ Python Analyzer Tool
# ----------------------------------------------------------
class PythonAnalyzerTool(BaseTool):
    name: str = "Python Analyzer Tool"
    description: str = "리포트 제목 기반 키워드/카테고리 분석"
    
    def _run(self, reports_str: str) -> str:
        """키워드 및 카테고리 분석"""
        try:
            reports = eval(reports_str)
            df = pd.DataFrame(reports).drop_duplicates(subset=["title", "company"])
            words = sum([re.findall(r"[가-힣A-Za-z0-9]{2,12}", t) for t in df["title"]], [])
            stop = {"리포트", "분석", "전망", "투자", "경제", "산업", "이슈"}
            counter = Counter([w for w in words if w not in stop])
            result = {
                "top_keywords": ", ".join([f"{k}({v}회)" for k, v in counter.most_common(7)]),
                "category_summary": df["category"].value_counts().to_dict()
            }
            return str(result)
        except Exception as e:
            return f"분석 실패: {e}"

# ----------------------------------------------------------
# 3️⃣ Report Summarizer Tool
# ----------------------------------------------------------
class ReportSummarizerTool(BaseTool):
    name: str = "Report Summarizer Tool"
    description: str = "PDF 리포트 2~3줄 요약"
    
    def _run(self, reports_str: str) -> str:
        """리포트 요약"""
        try:
            reports = eval(reports_str)
            summaries = []
            for r in reports[:5]:  # 최대 5개만 테스트
                title, company, category, pdf_url = r["title"], r["company"], r["category"], r.get("pdf_url")
                text = ""
                if pdf_url:
                    try:
                        res = requests.get(pdf_url, headers=HEADERS, timeout=15)
                        with open("temp.pdf", "wb") as f: f.write(res.content)
                        with fitz.open("temp.pdf") as pdf:
                            for page in pdf: text += page.get_text()
                        os.remove("temp.pdf")
                    except Exception as e: 
                        text = f"[PDF 추출 실패: {e}]"
                
                prompt = f"""
당신은 20년차 금융 애널리스트입니다.
{company}의 '{title}' 리포트를 2~3줄로 요약하세요.
사실만 남기고 전망/예측은 제외합니다.
본문:
{text[:5000]}
"""
                try:
                    resp = client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=[{"role": "system", "content": "사실 기반 요약만 수행."},
                                  {"role": "user", "content": prompt}],
                        temperature=0.0)
                    summary = resp.choices[0].message.content.strip()
                except Exception as e:
                    summary = f"[요약 실패: {e}]"
                
                summaries.append({"category": category, "title": title,
                                  "company": company, "summary": summary})
                time.sleep(1)
            return str(summaries)
        except Exception as e:
            return f"요약 실패: {e}"

# ----------------------------------------------------------
# 4️⃣ Final Briefing Tool
# ----------------------------------------------------------
class FinalBriefingTool(BaseTool):
    name: str = "Final Briefing Tool"
    description: str = "분석 결과와 요약 리스트를 종합해 일일 브리핑 텍스트 작성"
    
    def _run(self, summaries_str: str, analysis_str: str) -> str:
        """최종 브리핑 생성"""
        try:
            summaries = eval(summaries_str)
            analysis = eval(analysis_str)
            
            summary_texts = [f"[{s['category']}] {s['title']} — {s['summary']} ({s['company']})"
                             for s in summaries]
            prompt = f"""
[오늘의 키워드]
{analysis.get("top_keywords", "N/A")}
[카테고리별 비중]
{analysis.get("category_summary", {})}

[요약문 리스트]
{chr(10).join(summary_texts)}

---
위 데이터를 바탕으로 투자 스터디용 '일일 브리핑'을 작성하시오.
1) 핵심 테마 TOP 3~5
2) 거시경제 요약
3) 주요 종목 및 산업별 요약
"""
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "system", "content": "20년차 리서치 애널리스트로 사실 기반 브리핑 작성"},
                          {"role": "user", "content": prompt}],
                temperature=0.0)
            body = resp.choices[0].message.content.strip()
            header = f"# {today_file} 일일 증권사 리포트 브리핑\n\n*총 {len(summaries)}건 기반 / {today_display} 발행*\n\n"
            return header + body
        except Exception as e:
            return f"브리핑 생성 실패: {e}"

# ----------------------------------------------------------
# 5️⃣ Notion Upload Tool
# ----------------------------------------------------------
class NotionUploadTool(BaseTool):
    name: str = "Notion Upload Tool"
    description: str = "최종 브리핑과 분석결과를 Notion DB에 업로드"
    
    def _run(self, briefing_text: str, analysis_str: str) -> str:
        """Notion에 업로드"""
        try:
            analysis = eval(analysis_str)
            page_data = {
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Date": {"date": {"start": today_file}},
                    "Top Keywords": {"rich_text": [{"text": {"content": analysis.get("top_keywords", "")[:2000]}}]},
                    "Category Summary": {"rich_text": [{"text": {"content": str(analysis.get("category_summary", {}))[:2000]}}]},
                    "Name": {"title": [{"text": {"content": f"{today_file} 일일 브리핑"}}]}
                }
            }
            res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=page_data)
            res.raise_for_status()
            parent_id = res.json()["id"]
            
            children = []
            for i in range(0, len(briefing_text), 2000):
                children.append({"object": "block", "type": "paragraph",
                                 "paragraph": {"rich_text": [{"type": "text", "text": {"content": briefing_text[i:i+2000]}}]}})
            
            res_blocks = requests.patch(f"https://api.notion.com/v1/blocks/{parent_id}/children",
                                        headers=NOTION_HEADERS, json={"children": children})
            res_blocks.raise_for_status()
            return f"✅ Notion 업로드 완료 (Page ID: {parent_id})"
        except Exception as e:
            return f"⚠️ Notion 업로드 실패: {e}"

# ----------------------------------------------------------
# 6️⃣ 간소화된 실행 함수
# ----------------------------------------------------------
def run_daily_briefing():
    """전체 파이프라인 실행"""
    print(f"[START] {today_display} Daily Briefing 시작 (v7-Final)")
    
    # 1. 리포트 수집
    print("\n[1/5] 리포트 수집 중...")
    naver_tool = NaverResearchScraperTool()
    hankyung_tool = HankyungScraperTool()
    naver_reports = eval(naver_tool._run())
    hankyung_reports = eval(hankyung_tool._run())
    all_reports = naver_reports + hankyung_reports
    print(f"   [OK] 총 {len(all_reports)}개 리포트 수집 완료")
    
    # 2. 키워드 분석
    print("\n[2/5] 키워드 분석 중...")
    analyzer = PythonAnalyzerTool()
    analysis = eval(analyzer._run(str(all_reports)))
    print(f"   [OK] 키워드: {analysis['top_keywords']}")
    
    # 3. 리포트 요약
    print("\n[3/5] 리포트 요약 중...")
    summarizer = ReportSummarizerTool()
    summaries = eval(summarizer._run(str(all_reports)))
    print(f"   [OK] {len(summaries)}개 리포트 요약 완료")
    
    # 4. 최종 브리핑 생성
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
    try:
        result = run_daily_briefing()
        print("\n" + "="*60)
        print("최종 브리핑 미리보기:")
        print("="*60)
        print(result[:500] + "..." if len(result) > 500 else result)
    except Exception as e:
        print(f"\n[ERROR] 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
