"""Extract exact source frames for the curated observations, preserving original offsets."""
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import store

source=Path(os.environ.get('FIELDLINK_MEDIA_DIR','/Users/praveen/Downloads/OneDrive_1_5-10-2026'))
store.seed()
for observation in store.all_records('observations'):
    index=int(observation['videoId'][1:])
    filename='BV_Sample1.mp4' if index==1 else f'BV SAMPLE {index}.mp4'
    for target,filters in [(store.DATA/'evidence'/f"{observation['id']}.jpg",[]),(store.DATA/'frames'/observation['videoId']/f"{observation['timestamp']:03}.jpg",['-vf','scale=480:-1'])]:
        target.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['ffmpeg','-v','error','-ss',str(observation['timestamp']),'-i',str(source/filename),'-frames:v','1','-q:v','2',*filters,'-y',str(target)],check=True)
print('Prepared exact evidence frames and thumbnails for all observations')
