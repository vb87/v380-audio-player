# V380 Audio Player
Play audio on your V380 camera because why not

> [!NOTE]
> I've only tested this with V380 cameras that use Version 3, 31, and 32. It is very likely that it will fail on other versions. It will tell you what version your camera uses once you've successfully sent a login request. Having correct credentials is not required to get the version number.

# Building
Make sure you have Python 3.9 and [uv](https://github.com/astral-sh/uv) installed

1. Clone this repo
2. `cd` to wherever you have it
3. Run `uv run main.py` to install dependencies (if missing) and run the program

# Usage
- Place your audio files in a subfolder called `audio`. It should be in 8khz Mono WAV format.
- Create a file `data.yaml` and populate it with your camera data. You can refer to `data.EXAMPLE.yaml` for the format.

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
- [apktool](https://apktool.org/)
- https://cyberlinksecurity.ie/vulnerabilities-to-exploit-a-chinese-ip-camera/

