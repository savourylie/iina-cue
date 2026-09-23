"""Generate original, local synthetic speech; never fetch media or voices."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks/fixtures/generated"
OUT.mkdir(parents=True, exist_ok=True)
samples = {
    "en": ("Samantha (English (US))", "The train leaves at nine tomorrow morning. Please remember to bring your ticket. We will meet outside the station, next to the small coffee shop."),
    "zh": ("Meijia (Chinese (Taiwan))", "火車明天早上九點出發。請記得帶好你的車票。我們會在車站外面的小咖啡店旁邊見面。如果下雨，就改在大廳等候。"),
    "ja": ("Kyoko", "電車は明日の朝九時に出発します。切符を忘れないでください。駅の外にある小さな喫茶店の隣で会いましょう。雨が降ったら、ロビーで待ちます。"),
    "ko": ("Yuna", "기차는 내일 아침 아홉 시에 출발합니다. 표를 꼭 가져오세요. 역 밖에 있는 작은 커피숍 옆에서 만나요. 비가 오면 로비에서 기다리겠습니다."),
}
long_text = """Welcome to this local subtitle demonstration. Today we are going to plan a weekend trip, compare a few practical choices, and explain how we made the final decision. The purpose of this recording is to provide ordinary continuous speech for a software test. It is a synthetic voice reading an original script. It is not a recording of a real customer, and it should not be used as proof of recognition quality on natural conversations.

Our train leaves on Saturday morning at nine fifteen. We should reach the station at least twenty minutes early, because the entrance on the west side is closed for maintenance. Please use the east entrance, walk past the information desk, and follow the blue signs to platform three. Everyone should bring their own ticket and a bottle of water. There is a small shop inside the station, but we should not depend on it being open that early.

After arriving in the town, we will leave our bags at the hotel. The rooms may not be ready until the afternoon, so we need to keep anything important in our smaller backpacks. We can spend the morning walking around the market. There are several cafes near the river. One serves breakfast until eleven, while another has a quiet garden and opens at ten. If the weather is good, the garden would be a comfortable place to sit and discuss the rest of the day.

For lunch, we have two possible restaurants. The first is close to the museum and offers vegetarian meals. The second is farther away, but it has a covered terrace with a view of the hills. We do not need to decide immediately. We can check how everyone feels after the morning walk. If someone is tired, we should choose the closer restaurant and take a longer break. This is supposed to be a relaxing trip, not a competition to visit as many places as possible.

In the afternoon, the museum closes at five thirty. Its temporary exhibition is on the second floor, and the permanent collection is downstairs. The ticket includes both areas. We should ask whether photographs are allowed before taking any pictures. Later, we can walk back along the river, buy something simple for dinner, and return to the hotel. If it rains, the public bus stops directly across from the museum entrance. There is no need to hurry through the rain.

On Sunday morning, breakfast is served between seven and ten. We can leave the hotel around ten thirty and take the short walking trail behind the old library. The route is mostly flat, but comfortable shoes would still be useful. Before leaving town, remember to check the train schedule again. Small changes are possible, and checking the departure board is better than relying only on an old message. The return trip should take about ninety minutes.

That completes our plan. We have left enough time for meals, breaks, and unexpected changes. The most useful part of planning is understanding the choices, rather than trying to predict every detail. Keep the important information nearby, listen carefully when somebody suggests a change, and make sure everyone knows where to meet. Thank you for listening to this recording. The next step is to review the generated subtitles and compare their timing with the actual words in the audio."""
samples["en-long"] = (samples["en"][0], long_text)
manifest = []
for key, (voice, text) in samples.items():
    source=OUT/f"{key}.txt"; source.write_text(text)
    aiff=OUT/f"{key}.aiff"; wav=OUT/f"{key}.wav"
    subprocess.run(["/usr/bin/say", "-v", voice, "-r", "165", "-f", str(source), "-o", str(aiff)], check=True)
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-v", "error", "-i", str(aiff), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(wav)], check=True)
    if wav.stat().st_size < 16000: raise RuntimeError("Synthetic audio was empty")
    duration=float(subprocess.check_output(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(wav)]))
    manifest.append({"id":key,"voice":voice,"seconds":duration,"kind":"synthetic diagnostic, not held-out human speech"})
    print(key,duration,flush=True)
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
subprocess.run(["/opt/homebrew/bin/ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=0x182c3a:s=1280x720:r=24", "-i", str(OUT/"en-long.wav"), "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-metadata:s:a:0", "language=eng", "-y", str(OUT/"cue-smoke.mp4")],check=True)
