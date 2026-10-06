"""Download public model weights once. Site images never leave this computer."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ['HF_HOME']=str(ROOT/'data/models/.cache')
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
from huggingface_hub import snapshot_download

registry={}
for name,repo,revision in [('detector','IDEA-Research/grounding-dino-tiny','a2bb814dd30d776dcf7e30523b00659f4f141c71'),('segmenter','facebook/sam2.1-hiera-tiny','de431c4043854a71d8101e17995dfe596bf101a5')]:
    destination=ROOT/'data/models'/name
    print(f'Downloading {repo} @ {revision}',flush=True)
    snapshot_download(repo_id=repo,revision=revision,local_dir=destination,max_workers=2,
        allow_patterns=['*.json','*.txt','*.model','*.safetensors','README.md','LICENSE*'])
    registry[name]={'repo':repo,'revision':revision,'directory':name}
(ROOT/'data/models/registry.json').write_text(json.dumps(registry,indent=2)+'\n')
print('Models ready for offline detection and segmentation.',flush=True)
