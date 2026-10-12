"""Offline publisher: python -m backend.import_case assets/cases/case_001/v1/slice.json"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.application.catalog import import_case
from backend.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验并发布一个固定版本的案件定义。")
    parser.add_argument("path", type=Path, help="案件 JSON 文件")
    args = parser.parse_args(argv)
    engine = create_engine(str(Settings().database_url))
    try:
        result = import_case(sessionmaker(engine), args.path)
    except ValueError as error:
        print(f"导入失败：{error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    state = "已发布" if result.created else "已存在且内容一致，未修改"
    print(f"{result.case_id} {result.version} {state}（{result.content_hash[:12]}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
