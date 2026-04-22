import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent


def load_config(config_path: str = None) -> dict:
    path = Path(config_path or ROOT / 'config.yaml')
    if not path.exists():
        raise FileNotFoundError(f'Config file not found: {path}')

    with path.open('r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError('Invalid config format, expected YAML mapping.')

    model_cfg = config.get('model', {})
    api_key_env = model_cfg.get('dashscope_api_key_env', 'DASHSCOPE_API_KEY')
    if os.getenv(api_key_env):
        model_cfg['api_key'] = os.getenv(api_key_env)
    else:
        model_cfg['api_key'] = 'sk-f01ac7185e714813b873e686e2baf183'
    config['model'] = model_cfg

    config['knowledge_dir'] = str((ROOT / config.get('knowledge_dir', 'library')).resolve())
    if 'watch' in config and isinstance(config['watch'], dict):
        config['watch']['paths'] = [str((ROOT / p).resolve()) for p in config['watch'].get('paths', [])]

    return config
