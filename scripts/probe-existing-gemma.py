"""Diagnostic only: use an explicitly supplied, already-owned HF E2B snapshot.

Not a production backend selection and not the LiteRT/aligner benchmark.
Run with the existing dora environment; this installs/downloads nothing.
"""
import argparse
import json
import os
from pathlib import Path
import resource
import time
import wave

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
parser=argparse.ArgumentParser()
parser.add_argument('--model',required=True);parser.add_argument('--audio',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args()
with wave.open(args.audio) as check:
    if check.getnframes() < 1600: raise SystemExit('Audio fixture is empty or too short')
import numpy as np
import torch
from transformers import AutoProcessor,Gemma4ForConditionalGeneration
if not torch.backends.mps.is_available():raise SystemExit('MPS unavailable; no silent CPU fallback')
torch.set_num_threads(4)
t=time.monotonic()
model=Gemma4ForConditionalGeneration.from_pretrained(args.model,local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16).to('mps').eval()
processor=AutoProcessor.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
torch.mps.synchronize();load=time.monotonic()-t
with wave.open(args.audio) as f:
    assert f.getnchannels()==1 and f.getframerate()==16000 and f.getsampwidth()==2
    audio=np.frombuffer(f.readframes(f.getnframes()),dtype=np.int16).astype(np.float32)/32768
def generate(prompt,with_audio):
    content=[{'type':'text','text':prompt}]
    if with_audio:content.append({'type':'audio'})
    rendered=processor.apply_chat_template([{'role':'user','content':content}],add_generation_prompt=True,tokenize=False,enable_thinking=False)
    kw={'text':rendered,'return_tensors':'pt'}
    if with_audio:kw.update(audio=[audio],sampling_rate=16000)
    inputs=processor(**kw).to('mps')
    t=time.monotonic()
    with torch.inference_mode():output=model.generate(**inputs,max_new_tokens=160,do_sample=False)
    torch.mps.synchronize()
    result=processor.batch_decode(output[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
    return {'text':result,'elapsed_s':time.monotonic()-t}
results={'diagnostic':'existing Transformers E2B; not production LiteRT or complete pipeline',
         'model_revision':Path(args.model).name,'device':'mps','dtype':'bfloat16','load_s':load,'audio_seconds':len(audio)/16000}
results['transcription']=generate('Transcribe the following speech segment in its original language. Output only the spoken words.',True)
results['translation']=generate('Translate this subtitle into Traditional Chinese using Taiwan vocabulary. Output only the translation.\n'+results['transcription']['text'],False)
results['warm_transcription']=generate('Transcribe the following speech segment in its original language. Output only the spoken words.',True)
results['peak_process_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
