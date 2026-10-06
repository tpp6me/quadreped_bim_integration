"""Inventory original recordings and derive contact sheets without changing source media."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('FIELDLINK_MEDIA_DIR', '/Users/praveen/Downloads/OneDrive_1_5-10-2026'))
OUT = ROOT / 'data'

def prepare(index):
    name = 'BV_Sample1.mp4' if index == 1 else f'BV SAMPLE {index}.mp4'
    path = SOURCE / name
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))
    stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    duration = float(probe['format']['duration'])
    folder = OUT / 'frames' / f'v{index:02}'
    folder.mkdir(parents=True, exist_ok=True)
    for seconds in range(0, int(duration), 5):
        target = folder / f'{seconds:03}.jpg'
        if not target.exists():
            subprocess.run(['ffmpeg','-v','error','-threads','1','-ss',str(seconds),'-i',str(path),'-frames:v','1','-vf','scale=480:-1','-y',str(target)],check=True)
    frames = sorted(folder.glob('*.jpg'))
    sheet = Image.new('RGB', (480*4, 298*((len(frames)+3)//4)), '#f4f3ed')
    draw = ImageDraw.Draw(sheet)
    for n, frame in enumerate(frames):
        x,y = (n%4)*480,(n//4)*298
        draw.text((x+8,y+7),f'{name} / {int(frame.stem):03}s', fill='black')
        sheet.paste(Image.open(frame),(x,y+26))
    (OUT/'contact-sheets').mkdir(exist_ok=True)
    sheet.save(OUT/'contact-sheets'/f'v{index:02}.jpg')
    digest = hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    print(f'Prepared {name}: {len(frames)} frames',flush=True)
    return {'id':f'v{index:02}','filename':name,'duration':round(duration,3),'width':stream['width'],'height':stream['height'],'fps':stream['r_frame_rate'],'sha256':digest,'bytes':path.stat().st_size,'captured_at':None,'capture_time_source':'unknown','recording_device':None,'chronology':'unverified','audio':any(s['codec_type']=='audio' for s in probe['streams']),'metadata':probe['format'].get('tags',{}),'thumbnail':f'/assets-data/frames/v{index:02}/060.jpg','url':f'/media/v{index:02}'}

if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        videos = list(pool.map(prepare,range(1,11)))
    (OUT/'media.json').write_text(json.dumps(videos,indent=2))
