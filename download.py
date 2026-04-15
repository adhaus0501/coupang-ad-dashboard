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

        # 1. 로그인 페이지 접속
        print("로그인 페이지 접속...")
        page.goto("https://advertising.coupang.com/user/login", wait_until="networkidle")
        time.sleep(2)
        page.screenshot(path="debug_01_first_page.png")

        # 2. 페이지 HTML 전체 출력 (버튼 구조 파악용)
        html_snippet = page.evaluate("() => document.body.innerHTML.slice(0, 3000)")
        print(f"HTML 앞부분: {html_snippet}")

        # 3. 모든 클릭 가능한 요소 출력
        clickables = page.evaluate("""
            () => Array.from(document.querySelectorAll('button, a, [role="button"], [onclick]'))
                .map(el => ({
                    tag: el.tagName,
                    text: el.textContent.trim().slice(0, 50),
                    class: el.className.slice(0, 50),
                    href: el.href || ''
                }))
        """)
        print(f"클릭 가능 요소: {clickables}")

        # 4. #username이 바로 있으면 건너뜀, 없으면 모든 버튼 순서대로 시도
        if page.locator('#username').count() > 0:
            print("이미 로그인 폼 표시됨")
        else:
            print("로그인 폼 없음 - 버튼 클릭 시도...")
            # 페이지의 버튼을 하나씩 클릭해서 #username이 나올 때까지 시도
            btns = page.locator('button, a').all()
            print(f"총 {len(btns)}개 요소 발견")
            for i, btn in enumerate(btns):
                try:
                    txt = btn.text_content().strip()
                    print(f"  [{i}] 클릭 시도: '{txt}'")
                    btn.click(timeout=2000)
                    time.sleep(1)
                    if page.locator('#username').count() > 0:
                        print(f"  -> #username 발견! 성공")
                        break
                    # 클릭 후 페이지가 바뀌었으면 다시 대기
                    page.wait_for_load_state("networkidle")
                    time.sleep(1)
                    if page.locator('#username').count() > 0:
                        print(f"  -> #username 발견! 성공")
                        break
                except Exception as e:
                    print(f"  [{i}] 실패: {e}")
                    continue

        page.screenshot(path="debug_02_after_click.png")

        # 5. #username 대기 후 로그인
        print("#username 대기...")
        page.wait_for_selector('#username', state='visible', timeout=15000)
        page.fill('#username', COUPANG_ID)
        print("아이디 입력 완료")
        page.fill('#password', COUPANG_PW)
        print("비밀번호 입력 완료")
        page.click('#kc-login')
        print("로그인 버튼 클릭")

        page.wait_for_load_state("networkidle")
        time.sleep(3)
        page.screenshot(path="debug_03_after_login.png")
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
