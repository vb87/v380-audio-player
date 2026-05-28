## 0.2.0 (2026-05-28)

### Feat

- add receive-audio.py to record audio from camera microphone
- audio captured via port 8800 proprietary protocol, decoded from IMA ADPCM to WAV
- select camera and recording duration interactively
- output saved as timestamped WAV file playable in any media player

## 0.1.0 (2025-12-12)

### Feat

- add logging to file and scoped logs in console
- add multiple camera selection

### Fix

- replace IMA ADPCM implementation with pyami module
- properly close sockets
- catch exceptions from threads
- run mkdir instead of touch for audio folder

### Refactor

- renamed session to handle
- add type hints

## 0.0.1 (2025-12-11)
