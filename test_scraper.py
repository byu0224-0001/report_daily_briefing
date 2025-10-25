"""
네이버 금융 페이지 구조 확인 테스트
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 네이버 투자정보 페이지 테스트
url = "https://finance.naver.com/research/invest_list.naver"
print(f"테스트 URL: {url}\n")

try:
    res = requests.get(url, headers=HEADERS, timeout=10)
    print(f"응답 코드: {res.status_code}")
    print(f"응답 크기: {len(res.text)} bytes\n")
    
    soup = BeautifulSoup(res.text, "html.parser")
    
    # 여러 선택자 시도
    selectors = [
        "table.type_1 tbody tr",
        "table tbody tr",
        "table tr",
        ".type_1 tr",
        "tr"
    ]
    
    for selector in selectors:
        rows = soup.select(selector)
        print(f"선택자 '{selector}': {len(rows)}개 발견")
        if len(rows) > 0 and len(rows) < 100:
            # 첫 번째 row 샘플
            first_row = rows[0]
            cols = first_row.find_all("td")
            print(f"  첫 번째 row의 td 개수: {len(cols)}")
            if len(cols) > 0:
                print(f"  첫 번째 td 내용: {cols[0].get_text(strip=True)[:50]}")
            print()
    
    # iframe 찾기
    print("\n" + "="*60)
    print("iframe 검색:")
    print("="*60)
    iframes = soup.find_all("iframe")
    print(f"총 {len(iframes)}개 iframe 발견")
    for i, iframe in enumerate(iframes, 1):
        src = iframe.get("src", "N/A")
        print(f"{i}. {src}")
    
    # HTML 일부 저장
    print("\n" + "="*60)
    print("HTML 샘플 (처음 3000자):")
    print("="*60)
    print(res.text[:3000])
    
except Exception as e:
    print(f"에러 발생: {e}")
    import traceback
    traceback.print_exc()

