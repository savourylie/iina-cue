#!/usr/bin/env python3
"""Explicit generated-fixture diagnostic; no private media discovery."""
from dataclasses import asdict
import json
from pathlib import Path
import time
from cue.backend import Backend
from cue.bootstrap import models_root
from cue.core import assemble,validate_units,srt,CueError
import soundfile as sf
root=Path(__file__).resolve().parents[1]
backend=Backend(models_root())
rows=[]
out=root/'benchmarks/results/languages.json'
try:
    t=time.monotonic();backend.load();load=time.monotonic()-t
    for lang in ('en','zh','ja','ko'):
        wav=root/f'benchmarks/fixtures/generated/{lang}.wav'
        row={'language':lang,'fixture':'macOS synthetic voice, original script','duration_s':sf.info(wav).duration}
        try:
            t=time.monotonic();text=backend.transcribe(wav);row['asr_s']=time.monotonic()-t;row['transcript']=text
            try: row['auto_lid']=backend.language(text,'auto')
            except CueError as e: row['auto_lid']={'status':'error','code':e.code}
            t=time.monotonic();units=backend.align(wav,text,lang);validate_units(units,round(row['duration_s']*1000),text);row['align_s']=time.monotonic()-t
            cues=assemble(units,0,0,round(row['duration_s']*1000),lang)
            t=time.monotonic();translated=backend.translate(cues,'zh-TW' if lang!='zh' else 'en',lang);row['translation_s']=time.monotonic()-t
            row.update(status='pass_pipeline_only',units=[asdict(u) for u in units],source=[asdict(c) for c in cues],translated=[asdict(c) for c in translated])
            (out.parent/f'{lang}.srt').write_text(srt(translated))
        except Exception as e: row.update(status='failed',error=str(e),code=getattr(e,'code',type(e).__name__))
        rows.append(row);out.write_text(json.dumps({'load_s':load,'quality_acceptance':'not_established_by_synthetic_speech','samples':rows},ensure_ascii=False,indent=2));print(lang,row['status'],flush=True)
finally:backend.close()
