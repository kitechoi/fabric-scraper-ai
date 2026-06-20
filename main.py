"""
CLI 진입점 - 개발/테스트용
사용: python3 main.py <URL> [--seller 판매처] [--date YYYY-MM-DD] [--force]
"""
import sys
import json
import argparse
from pipeline import collect_fabric_data, DuplicateURLError

def main():
    parser = argparse.ArgumentParser(description="원단 정보 수집")
    parser.add_argument("url", help="상품 URL")
    parser.add_argument("--seller", default=None, help="판매처")
    parser.add_argument("--date",   default=None, help="구입일 (YYYY-MM-DD)")
    parser.add_argument("--force",  action="store_true", help="중복이어도 재수집")
    args = parser.parse_args()

    print(f"[pipeline] URL: {args.url}")
    try:
        info, row_id = collect_fabric_data(
            args.url,
            seller=args.seller,
            purchase_date=args.date,
            force=args.force,
        )
    except DuplicateURLError as e:
        print(f"\n⚠️  {e}")
        print("재수집하려면 --force 옵션을 추가하세요.")
        sys.exit(0)

    print("\n===== 추출 결과 =====")
    print(json.dumps(info.model_dump(), indent=2, ensure_ascii=False))
    print(f"\n저장 완료 (id={row_id})")

if __name__ == "__main__":
    main()
