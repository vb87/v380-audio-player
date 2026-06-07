# V380 Audio Player
A fork of V380 Audio Player that introduces mic recording for older V380 cameras.

> [!NOTE]
> I've only tested this with V380 cameras that use Version 3, 31, and 32. It is very likely that it will fail on other versions. It will tell you what version your camera uses once you've successfully sent a login request. Having correct credentials is not required to get the version number.

# Building
Make sure you have Python 3.9 and [uv](https://github.com/astral-sh/uv) installed

1. Clone this repo
2. `cd` to wherever you have it
3. Run `uv run main.py` to install dependencies (if missing) and run the program

# Usage

## Playing audio on the camera speaker
- Place your audio files in a subfolder called `audio`. It should be in 16-bit 8khz Mono WAV format.
- Create a file `data.yaml` and populate it with your camera data. You can refer to `data.EXAMPLE.yaml` for the format.
- Run the program. You can select multiple cameras, and select an audio file to play.

```
uv run main.py
```

## Recording audio from the camera microphone
- Make sure `data.yaml` is set up with your camera credentials (see above).
- Run the receive script, select your camera and recording duration when prompted.

```
uv run receive-audio.py
```

The recording is saved as a timestamped WAV file (e.g. `my-camera_20250528_143022.wav`) in the current directory. It can be played by VLC or any standard media player.

> [!NOTE]
> Audio is captured via the proprietary TCP protocol on port 8800, not RTSP. The camera's RTSP stream does not carry audio — this script is the only way to access the microphone.

> [!NOTE]
> Tested on firmware `HwV380E12_WF3_PCARD_V50_20160217` (Version 3 cameras). The audio stream uses IMA ADPCM encoding at 8000 Hz mono.

# Getting Credentials
Run `uv run extract_creds.py` to find the specific credentials used for your camera. It's not actually the same as the one you use to login to the app itself, especially on Version 32. An easy way to do this is to install PCAPdroid and V380 on an Android phone.

1. Set V380 as a target app in PCAPdroid
2. Press "Ready" to start tracking
3. Open V380 and then open up your desired camera
4. Go back to PCAPdroid and stop the tracking
5. Find the request in the connections tab. It's on TCP port 8800, and make sure you're also connecting to the camera in LAN mode. In the payload tab, look at the first request and see if it starts with `8f 04`. If it does, that's the correct file. Press on the download icon and select `Raw bytes`.
6. On your PC, run `uv run extract_creds.py` and paste the location of that file.
7. It should print out the username and password. You can add these to `data.yaml`

# Acknowledgements
This program was made possible thanks to the following tools and resources. Do check them out if you want to dive into reverse engineering Android apps.
- [jadx](https://github.com/skylot/jadx/)
- [GDA](https://github.com/charles2gan/GDA-android-reversing-Tool/)
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra)
- [Frida](https://frida.re/)
- [apktool](https://apktool.org/)\
- https://cyberlinksecurity.ie/vulnerabilities-to-exploit-a-chinese-ip-camera/
- [frida-dexdump](https://github.com/hluwa/frida-dexdump)
- [prsyahmi/v380](https://github.com/prsyahmi/v380) — C++ tool that reverse engineered the port 8800 stream protocol
