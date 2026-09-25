# Install Cue

Cue adds local subtitles in IINA. This page is for someone installing Cue. It has no Terminal commands. Developer setup stays in [Development preview installation](install.md).

You need an Apple Silicon Mac, macOS 14.0 or later, and IINA 1.4 or later. Plan on about 16 GB of memory and about 8 GB of free disk space. The first-run download is about 3.8 GB and often takes 10 to 30 minutes, depending on your connection.

## Double-click the plugin

1. Get `Cue-0.1.0.iinaplgz`.
2. Double-click it.
3. When IINA asks, confirm the install.
4. Open IINA, then Settings, then Plugins, and enable Cue.
5. Open a video. In the Cue sidebar, press Download. Cue then fetches the helper and the speech models. You do not type a command.

## Install from GitHub

1. Open IINA.
2. Open Settings, then Plugins.
3. Choose Install from GitHub.
4. Enter `savourylie/iina-cue`.
5. Enable Cue.
6. Open a video. In the Cue sidebar, press Download.

## The permission warning

IINA can show a red warning that a plugin "can execute other programs or applications that can harm your computer". Cue asks for file-system access so it can read the video you opened and write subtitle files next to it. It connects only to Hugging Face, which serves the helper and the speech models, to GitHub, which keeps a backup copy of the helper, and to 127.0.0.1, where the local helper listens. The helper runtime is notarized by Apple. Cue does not use a microphone, and it does not send the video anywhere.

## Larger speech models

Cue listens with Gemma 4 E2B. Under Advanced in the Cue sidebar, Speech model offers two larger models. Each is a separate download, and Cue downloads one only when you press its Download button.

- Gemma 4 E4B: a 3.7 GB download that needs about 6.0 GB of disk space and 16 GB of memory. It hears difficult dialogue more accurately, and it is a little slower.
- Gemma 4 12B: a 6.9 GB download that needs about 12.9 GB of disk space and 24 GB of memory. It is experimental: it is the slowest, and in testing it missed more lines than E2B.

The disk space includes a cache the model writes the first time it runs. To switch models, turn off AI subtitles in every IINA window, then choose the model. Cue tries a short spoken clip with it first. If the clip does not work, Cue keeps the model you had. Remove deletes a model and its cache. Gemma 4 E2B stays installed.

## If something goes wrong

An unsupported Mac, including an Intel Mac or a system older than macOS 14.0, is refused before the download. The sidebar gives the reason. Cue does not start a download that the Mac cannot run.

If there is not enough free disk space, Cue names the number of bytes it needs and does not start. Free some space, then press Download again.

If the download stops, for example because IINA quit or the connection dropped, the sidebar offers Retry. Press it, and Cue continues from the bytes it already saved. You do not start from zero.

After the download, Cue tries a short spoken test clip before it calls itself ready. If that test fails, the sidebar gives the reason and offers Retry.

To remove Cue completely, quit IINA, open Settings, then Plugins, and remove Cue. Then delete the folder `~/Library/Application Support/Cue`. That folder holds the helper, the models, and the local subtitle cache.
