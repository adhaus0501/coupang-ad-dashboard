import os, json, time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

COUPANG_ID = os.environ["COUPANG_ID"]
COUPANG_PW = os.environ["COUPANG_PW"]

yesterday  = datetime.now() - timedelta(days=1)
date_str   = yesterday.strftime("%Y%m%d")
date_disp  = yesterday.strftime("%Y.%m.%d")

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_advertisers():
    path = "advertisers.json"
    if not os.path.exists(path):
        print("advertisers.json 없음"); return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"name": item, "code": item})
        elif isinstance(item, dict):
            result.append(item)
    print(f"업체코드 {len(result)}개: {[a['code'] for a in result]}")
    return result

def run():
    advertisers = load_advertisers()
    if not advertisers:
        print("업체코드 없음"); return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx  = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        # 담당자 로그인 페이지 직접 URL로 접근
        # /user/login 은 선택 화면이므로 realms/coupang 경로로 직접 접근
        login_urls = [
            "https://advertising.coupang.com/user/login?userType=manager",
            "https://advertising.coupang.com/auth/realms/coupang/protocol/openid-connect/auth",
            "https://advertising.coupang.com/user/login#manager",
        ]

        print("로그인 시도 중...")

        # 먼저 기본 페이지 접속 후 URL 변화 추적
        page.goto("https://advertising.coupang.com/user/login", wait_until="networkidle")
        time.sleep(3)
        current_url = page.url
        print(f"현재 URL: {current_url}")
        page.screenshot(path="debug_01_initial.png")

        # 현재 페이지에서 모든 링크/버튼의 href와 onclick 확인
        elements_info = page.evaluate("""
            () => {
                const els = document.querySelectorAll('button, a, [role="button"]');
                return Array.from(els).map(el => ({
                    tag: el.tagName,
                    text: el.innerText?.trim() || el.textContent?.trim() || '',
                    href: el.href || el.getAttribute('href') || '',
                    class: el.className || '',
                    id: el.id || ''
                })).filter(e => e.text || e.href);
            }
        """)
        print(f"페이지 요소들: {elements_info}")

        # #username이 있으면 바로 로그인
        if page.locator('#username').count() > 0:
            print("로그인 폼 발견 - 바로 입력")
        else:
            # JS로 직접 클릭 이벤트 발생
            print("JS로 버튼 클릭 시도...")
            clicked = page.evaluate("""
                () => {
                    // 모든 버튼/링크 중 오른쪽에 있는 것 클릭 (로그인하기)
                    const btns = document.querySelectorAll('button, a, [role="button"]');
                    const arr = Array.from(btns);
                    // 마지막 버튼이 보통 "로그인하기"
                    if (arr.length > 0) {
                        const last = arr[arr.length - 1];
                        last.click();
                        return 'clicked: ' + (last.innerText || last.textContent || 'unknown');
                    }
                    return 'no buttons';
                }
            """)
            print(f"JS 클릭 결과: {clicked}")
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            current_url = page.url
            print(f"클릭 후 URL: {current_url}")
            page.screenshot(path="debug_02_after_click.png")

        # 그래도 없으면 URL에 파라미터 추가해서 직접 접근
        if page.locator('#username').count() == 0:
            print("다른 URL 시도...")
            for url in login_urls:
                print(f"접속: {url}")
                page.goto(url, wait_until="networkidle")
                time.sleep(2)
                if page.locator('#username').count() > 0:
                    print(f"#username 발견: {url}")
                    break
                print(f"URL: {page.url}")

        page.screenshot(path="debug_03_before_fill.png")

        # 최종 로그인 시도
        page.wait_for_selector('#username', state='visible', timeout=15000)
        page.fill('#username', COUPANG_ID)
        print("아이디 입력")
        page.fill('#password', COUPANG_PW)
        print("비밀번호 입력")
        page.click('#kc-login')
        print("로그인 버튼 클릭")

        page.wait_for_load_state("networkidle")
        time.sleep(3)
        page.screenshot(path="debug_04_after_login.png")
        print(f"로그인 후 URL: {page.url}")
        print("로그인 완료")

        for idx, adv in enumerate(advertisers):
            adv_id   = adv["code"]
            adv_name = adv.get("name", adv_id)
            print(f"\n[{idx+1}/{len(advertisers)}] {adv_name} ({adv_id}) 처리 중...")
            try:
                download_for(page, adv_id, adv_name, idx)
            except Exception as e:
                print(f"실패: {adv_name} - {e}")
                page.screenshot(path=f"debug_error_{adv_id}.png")

        browser.close()
    print("\n전체 완료")


def download_for(page, adv_id, adv_name, idx):
    try:
        page.click('button:has-text("계정 전환"), button:has-text("광고주 변경")', timeout=4000)
        time.sleep(1)
    except PWTimeout:
        page.goto("https://advertising.coupang.com/advertiser/select", wait_until="networkidle")
        time.sleep(2)

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_01_select.png")

    for sel in ['input[placeholder*="검색"]', 'input[placeholder*="광고주"]', '#advertiserSearch']:
        try:
            page.fill(sel, adv_id, timeout=3000); time.sleep(1)
            print(f"검색: {adv_id}"); break
        except Exception: continue

    try:
        page.click(f'li:has-text("{adv_id}"), td:has-text("{adv_id}")', timeout=7000)
    except PWTimeout:
        page.click('ul li:first-child, table tbody tr:first-child', timeout=5000)

    page.wait_for_load_state("networkidle"); time.sleep(2)
    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_02_home.png")

    try:
        page.click('a:has-text("광고보고서"), a:has-text("광고 보고서")', timeout=6000)
        page.wait_for_load_state("networkidle"); time.sleep(1)
    except PWTimeout:
        page.goto("https://advertising.coupang.com/report/campaign", wait_until="networkidle"); time.sleep(2)

    try:
        page.click('a:has-text("매출 성장 광고 보고서"), li:has-text("매출 성장")', timeout=6000)
        page.wait_for_load_state("networkidle"); time.sleep(2)
    except PWTimeout:
        print("매출 성장 보고서 메뉴 못 찾음")

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_03_report.png")

    try:
        page.click('.date-picker, [class*="datePicker"]', timeout=4000); time.sleep(1)
        for sel in ['input[class*="start"]', 'input[name*="start"]']:
            try: page.fill(sel, date_disp, timeout=2000); break
            except Exception: pass
        for sel in ['input[class*="end"]', 'input[name*="end"]']:
            try: page.fill(sel, date_disp, timeout=2000); break
            except Exception: pass
        page.keyboard.press("Enter"); time.sleep(1)
    except Exception as e:
        print(f"날짜 설정 실패: {e}")

    try:
        page.click('button:has-text("캠페인을 선택")', timeout=6000); time.sleep(1)
        page.click('label:has-text("전체선택"), label:has-text("전체 선택")', timeout=4000); time.sleep(1)
        page.click('button:has-text("확인")', timeout=4000); time.sleep(1)
        print("캠페인 전체 선택 완료")
    except Exception as e:
        print(f"캠페인 선택 실패: {e}")

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_04_campaign.png")

    try:
        page.click('button:has-text("보고서 만들기"), button:has-text("조회")', timeout=6000)
        page.wait_for_load_state("networkidle"); time.sleep(5)
        print("보고서 생성 완료")
    except Exception as e:
        print(f"보고서 생성 실패: {e}")

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_05_done.png")

    with page.expect_download(timeout=30000) as dl_info:
        page.click('button:has-text("다운로드"), a:has-text("다운로드")', timeout=10000)
    dl = dl_info.value
    fname = dl.suggested_filename or f"{adv_id}_pa_total_campaign_{date_str}_{date_str}.xlsx"
    dl.save_as(os.path.join(OUTPUT_DIR, fname))
    print(f"저장 완료: {fname}")


if __name__ == "__main__":
    run()
