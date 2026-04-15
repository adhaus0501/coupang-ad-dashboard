"""
쿠팡 광고센터 자동 다운로드 스크립트
- advertisers.json 에 등록된 계정 ID만 다운로드
- 매일 08:00 KST GitHub Actions 실행
"""

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
        print("❌ advertisers.json 없음"); return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # 구 형식 ["A001..."] 또는 신 형식 [{"name":..., "code":...}] 둘 다 지원
    result = []
    for item in data:
        if isinstance(item, str):
            result.append({"name": item, "code": item})
        elif isinstance(item, dict):
            result.append(item)
    print(f"📋 업체코드 {len(result)}개: {[a['code'] for a in result]}")
    return result

def run():
    advertisers = load_advertisers()
    if not advertisers:
        print("등록된 업체코드 없음 - 종료"); return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx  = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        # ── 1. 로그인 ──────────────────────────────────────────
        print("🔐 로그인 중...")
        page.goto("https://advertising.coupang.com/user/login", wait_until="networkidle")
        time.sleep(2)
        page.screenshot(path="debug_01_login.png")

        # 아이디 입력 (실제 셀렉터: id="username", name="username")
        page.fill('#username', COUPANG_ID, timeout=10000)
        print("✅ 아이디 입력 완료")

        # 비밀번호 입력 (실제 셀렉터: id="password", name="password")
        page.fill('#password', COUPANG_PW, timeout=10000)
        print("✅ 비밀번호 입력 완료")

        # 로그인 버튼 클릭 (실제 셀렉터: id="kc-login")
        page.click('#kc-login', timeout=10000)
        print("✅ 로그인 버튼 클릭")

        page.wait_for_load_state("networkidle")
        time.sleep(3)
        page.screenshot(path="debug_02_after_login.png")
        print("✅ 로그인 완료")

        # ── 2. 각 업체코드별 다운로드 ─────────────────────────
        for idx, adv in enumerate(advertisers):
            adv_id   = adv["code"]
            adv_name = adv.get("name", adv_id)
            print(f"\n[{idx+1}/{len(advertisers)}] {adv_name} ({adv_id}) 처리 중...")
            try:
                download_for(page, adv_id, adv_name, idx)
            except Exception as e:
                print(f"❌ {adv_name} 실패: {e}")
                page.screenshot(path=f"debug_error_{adv_id}.png")

        browser.close()
    print("\n✅ 전체 완료")


def download_for(page, adv_id, adv_name, idx):
    # ── 광고주 선택 페이지로 이동 ──────────────────────────────
    try:
        # 상단 계정전환 버튼 시도
        page.click('button:has-text("계정 전환"), button:has-text("광고주 변경"), '
                   '[class*="accountSwitch"], [class*="account-switch"]', timeout=4000)
        time.sleep(1)
    except PWTimeout:
        # 광고주 선택 페이지 직접 이동
        page.goto("https://advertising.coupang.com/advertiser/select", wait_until="networkidle")
        time.sleep(2)

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_01_select.png")

    # ── 해당 계정 ID 검색 후 클릭 ─────────────────────────────
    # 검색창 입력
    for sel in ['input[placeholder*="검색"]', 'input[placeholder*="광고주"]',
                '.advertiser-search input', '#advertiserSearch', 'input[type="search"]']:
        try:
            page.fill(sel, adv_id, timeout=3000)
            time.sleep(1)
            print(f"  ✅ 검색: {adv_id}")
            break
        except Exception:
            continue

    # 해당 ID 항목 클릭
    try:
        page.click(f'[data-id="{adv_id}"], li:has-text("{adv_id}"), '
                   f'td:has-text("{adv_id}"), div:has-text("{adv_id}") >> nth=0',
                   timeout=7000)
    except PWTimeout:
        print(f"  ⚠️  직접 클릭 실패 - 첫 번째 항목으로 진행")
        page.click('.advertiser-item:first-child, ul li:first-child, '
                   'table tbody tr:first-child', timeout=5000)

    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_02_home.png")

    # ── 광고보고서 → 매출 성장 광고 보고서 ────────────────────
    try:
        page.click('a:has-text("광고보고서"), a:has-text("광고 보고서"), '
                   'nav a:has-text("보고서"), [href*="report"]', timeout=6000)
        page.wait_for_load_state("networkidle"); time.sleep(1)
    except PWTimeout:
        page.goto("https://advertising.coupang.com/report/campaign",
                  wait_until="networkidle"); time.sleep(2)

    try:
        page.click('a:has-text("매출 성장 광고 보고서"), li:has-text("매출 성장"), '
                   '[href*="total_campaign"], [href*="pa_total"]', timeout=6000)
        page.wait_for_load_state("networkidle"); time.sleep(2)
    except PWTimeout:
        print("  ⚠️  매출 성장 보고서 메뉴 못 찾음")

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_03_report.png")

    # ── 기간 설정: 전일 ───────────────────────────────────────
    try:
        page.click('.date-picker, [class*="datePicker"], [class*="date-range"]',
                   timeout=4000); time.sleep(1)
        for sel in ['input[class*="start"]', 'input[name*="start"]',
                    '.date-input:first-child input']:
            try: page.fill(sel, date_disp, timeout=2000); break
            except Exception: pass
        for sel in ['input[class*="end"]', 'input[name*="end"]',
                    '.date-input:last-child input']:
            try: page.fill(sel, date_disp, timeout=2000); break
            except Exception: pass
        page.keyboard.press("Enter"); time.sleep(1)
    except Exception as e:
        print(f"  ⚠️  날짜 설정 실패: {e}")

    # ── 캠페인 전체 선택 ──────────────────────────────────────
    try:
        page.click('button:has-text("캠페인을 선택"), [placeholder*="캠페인"]',
                   timeout=6000); time.sleep(1)
        page.click('label:has-text("전체선택"), label:has-text("전체 선택"), '
                   '.select-all input', timeout=4000); time.sleep(1)
        page.click('button:has-text("확인")', timeout=4000); time.sleep(1)
        print("  ✅ 캠페인 전체 선택")
    except Exception as e:
        print(f"  ⚠️  캠페인 선택 실패: {e}")

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_04_campaign.png")

    # ── 보고서 만들기 ─────────────────────────────────────────
    try:
        page.click('button:has-text("보고서 만들기"), button:has-text("조회")',
                   timeout=6000)
        page.wait_for_load_state("networkidle"); time.sleep(5)
        print("  ✅ 보고서 생성")
    except Exception as e:
        print(f"  ⚠️  보고서 생성 실패: {e}")

    page.screenshot(path=f"debug_{idx:02d}_{adv_id}_05_done.png")

    # ── 다운로드 ──────────────────────────────────────────────
    with page.expect_download(timeout=30000) as dl_info:
        page.click('button:has-text("다운로드"), a:has-text("다운로드"), '
                   '[class*="download"]:visible', timeout=10000)
    dl = dl_info.value
    fname = dl.suggested_filename or f"{adv_id}_pa_total_campaign_{date_str}_{date_str}.xlsx"
    dl.save_as(os.path.join(OUTPUT_DIR, fname))
    print(f"  ✅ 저장: {fname}")


if __name__ == "__main__":
    run()
