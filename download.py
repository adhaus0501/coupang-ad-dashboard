"""
쿠팡 광고센터 자동 다운로드 스크립트
매일 08:00 KST에 GitHub Actions로 실행됩니다.
"""

import os
import time
import glob
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

COUPANG_ID = os.environ["COUPANG_ID"]
COUPANG_PW = os.environ["COUPANG_PW"]

# 다운로드할 기간: 어제 하루치 (일별 리포트)
yesterday = datetime.now() - timedelta(days=1)
date_str  = yesterday.strftime("%Y%m%d")   # e.g. 20260415
date_disp = yesterday.strftime("%Y.%m.%d") # e.g. 2026.04.15

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        # ── 1. 로그인 ──────────────────────────────────────────
        print("🔐 쿠팡 광고센터 로그인 중...")
        page.goto("https://ads.coupang.com", wait_until="networkidle")
        time.sleep(2)

        page.fill('input[name="username"], input[type="email"], #userId', COUPANG_ID)
        page.fill('input[name="password"], input[type="password"], #userPw', COUPANG_PW)
        page.click('button[type="submit"], .login-btn, #loginBtn')
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        print("✅ 로그인 완료")

        # ── 2. 리포트 메뉴 이동 ────────────────────────────────
        print("📊 리포트 페이지 이동 중...")
        # 쿠팡 광고센터 리포트 URL (실제 경로가 다를 경우 아래에서 조정)
        page.goto("https://ads.coupang.com/report/campaign", wait_until="networkidle")
        time.sleep(3)

        # 메뉴가 없으면 좌측 네비게이션에서 클릭
        try:
            page.click('a[href*="report"], .menu-report, [data-menu="report"]', timeout=5000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
        except Exception:
            pass  # 이미 리포트 페이지에 있는 경우

        # ── 3. 날짜 범위 설정 (어제 하루) ─────────────────────
        print(f"📅 날짜 설정: {date_disp}")
        try:
            # 날짜 피커 열기
            page.click('.date-picker, .date-range, [class*="datepicker"], [class*="DatePicker"]', timeout=5000)
            time.sleep(1)

            # 시작일 = 종료일 = 어제
            for selector in ['.start-date input', '.date-start input', 'input.start']:
                try:
                    page.fill(selector, date_disp, timeout=2000)
                    break
                except Exception:
                    pass

            for selector in ['.end-date input', '.date-end input', 'input.end']:
                try:
                    page.fill(selector, date_disp, timeout=2000)
                    break
                except Exception:
                    pass

            # 조회 버튼 클릭
            page.click('button:has-text("조회"), button:has-text("검색"), .btn-search', timeout=5000)
            page.wait_for_load_state("networkidle")
            time.sleep(3)
        except Exception as e:
            print(f"⚠️  날짜 설정 실패 (수동 확인 필요): {e}")

        # ── 4. 다운로드 ────────────────────────────────────────
        print("⬇️  파일 다운로드 중...")
        try:
            with page.expect_download(timeout=30000) as dl_info:
                page.click(
                    'button:has-text("다운로드"), button:has-text("엑셀"), '
                    '.btn-download, [class*="download"], a[download]',
                    timeout=10000
                )
            download = dl_info.value
            # 파일명 형식: A00172104_pa_total_campaign_YYYYMMDD_YYYYMMDD.xlsx
            save_path = os.path.join(OUTPUT_DIR, download.suggested_filename or f"report_{date_str}_{date_str}.xlsx")
            download.save_as(save_path)
            print(f"✅ 저장 완료: {save_path}")
        except Exception as e:
            print(f"❌ 다운로드 실패: {e}")
            # 스크린샷 저장 (디버깅용)
            page.screenshot(path="debug_screenshot.png")
            print("🖼  debug_screenshot.png 저장됨 (Actions Artifacts에서 확인)")
            raise

        browser.close()

if __name__ == "__main__":
    run()
