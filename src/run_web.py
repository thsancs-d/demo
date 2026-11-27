"""Start the complete local workbench: python src/run_web.py [--port 8765]."""
import argparse
import uvicorn

from vlm_report import load_env
from web_app import create_app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='工程进度影像工作台')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    load_env()
    print(f'\n打开工作台：http://127.0.0.1:{args.port}\n', flush=True)
    uvicorn.run(create_app(), host='127.0.0.1', port=args.port)
