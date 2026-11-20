"""Configuration and local-service diagnostic; never prints API credentials."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app import config

def main():
    out = {"python": sys.version.split()[0], "model": config.MODEL, "api_configured": config.model_configured(),
           "base_url": config.BASE_URL, "embedding_model": config.EMBEDDING_MODEL}
    try:
        if not config.model_configured():
            raise ValueError("Model is not configured")
        with httpx.Client(timeout=20) as c:
            response = c.get(config.BASE_URL + '/models', headers={'Authorization': 'Bearer ' + config.API_KEY})
            out['model_api_status'] = response.status_code
            if response.is_success:
                out['configured_model_available'] = config.MODEL in [m['id'] for m in response.json()['data']]
    except Exception as e:
        out['model_api_error_type'] = type(e).__name__
    try:
        out['local_service'] = httpx.get(f'http://127.0.0.1:{config.PORT}/api/health',timeout=3).json()
    except Exception:
        out['local_service'] = 'not running'
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
