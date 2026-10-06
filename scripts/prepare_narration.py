"""Generate local synthetic narration and sentence-accurate captions with macOS say."""
import json
import os
from pathlib import Path
import subprocess
import wave

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/exports/narrated'
OUT.mkdir(parents=True,exist_ok=True)
VOICE=os.environ.get('FIELDLINK_VOICE','Samantha')
RATE=os.environ.get('FIELDLINK_SPEECH_RATE','165')
chapters=json.loads((ROOT/'scripts/narration.json').read_text())
rate=48000
for chapter in chapters:
    audio=bytearray(b'\0'*(int(rate*.35)*2))
    cues=[]
    for i,text in enumerate(chapter['sentences']):
        stem=OUT/f"{chapter['id']}-{i+1}"
        stem.with_suffix('.txt').write_text(text)
        subprocess.run(['say','-v',VOICE,'-r',RATE,'-f',str(stem.with_suffix('.txt')),'-o',str(stem.with_suffix('.aiff'))],check=True)
        subprocess.run(['ffmpeg','-v','error','-i',str(stem.with_suffix('.aiff')),'-ar',str(rate),'-ac','1','-c:a','pcm_s16le','-y',str(stem.with_suffix('.wav'))],check=True)
        with wave.open(str(stem.with_suffix('.wav')),'rb') as source:frames=source.readframes(source.getnframes())
        start=len(audio)/(rate*2);audio.extend(frames);end=len(audio)/(rate*2)
        cues.append({'start':start,'end':end,'text':text})
        audio.extend(b'\0'*(int(rate*.28)*2))
    audio.extend(b'\0'*(int(rate*.4)*2))
    raw=OUT/f"{chapter['id']}-raw.wav"
    with wave.open(str(raw),'wb') as target:target.setnchannels(1);target.setsampwidth(2);target.setframerate(rate);target.writeframes(audio)
    voice=OUT/f"{chapter['id']}.wav"
    subprocess.run(['ffmpeg','-v','error','-i',str(raw),'-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar',str(rate),'-ac','1','-y',str(voice)],check=True)
    chapter.update(duration=len(audio)/(rate*2),cues=cues,audio=str(voice),voice=VOICE,speechRate=int(RATE))
    print(f"{chapter['id']}: {chapter['duration']:.1f}s",flush=True)
(OUT/'narration-timing.json').write_text(json.dumps(chapters,indent=2))
print(f"Total narration: {sum(c['duration'] for c in chapters):.1f}s")
