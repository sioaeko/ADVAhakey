# AhaKey ADV

M5Stack **Cardputer ADV**를 USB/Bluetooth 키보드, AhaKey 호환 단축키 패드, 내장 마이크 음성 입력기로 사용하는 비공식 커뮤니티 펌웨어입니다.

Unofficial Cardputer ADV firmware with USB/BLE keyboard, AhaKey-compatible shortcuts and a Windows speech companion. Bluetooth microphone transport is **experimental**.

> **현재 상태:** 일반 USB/Wi-Fi 빌드는 `1.3.8`, Bluetooth 전용 빌드는 `1.4.2-ble`입니다. BLE 전용 빌드의 부팅·연결·MTU 185·Wi-Fi 비활성화는 기기에서 확인했습니다. 최종 ADPCM 버전의 실제 녹음 완료, 케이블 없는 사용, 녹음 중 동시 타이핑은 아직 검증하지 않았습니다. 완성된 Bluetooth 마이크 제품으로 배포하는 버전이 아닙니다.

## 기능과 조작

- USB가 연결되면 USB 키보드, 케이블이 없으면 페어링된 BLE 키보드로 입력합니다.
- 숫자 1–4를 포함해 기본 키는 일반 키보드처럼 동작합니다.
- Fn을 누른 채 조합하거나, Fn을 눌렀다 놓고 5초 이내에 다음 키를 누를 수 있습니다.
- 마이크 음성은 PC에서 Whisper로 인식합니다. PC 보조 프로그램이 필요하며 표준 Bluetooth 헤드셋이나 USB 오디오 장치로 등록되지 않습니다.

| 조작 | 기능 |
|---|---|
| G0 한 번 / 다시 한 번 | 녹음 시작 / 종료. 최대 60초 |
| Fn+Space 누르기 / 놓기 | 누르는 동안 녹음 |
| Fn+1 | 원본 AhaKey PC 앱의 Record 단축키(F18) |
| Fn+2 | Enter / 승인 |
| Fn+3 | 프로필별 거부 동작 |
| Fn+4 | Backspace |
| Fn+Tab | 단축키 프로필 전환 |
| Fn 다음 G0 짧게 | MANUAL 모드 |
| Fn 다음 G0 1.5초 | BLE 연결 중 AUTO 모드 활성화 |

G0 녹음 시작, 부팅, BLE 연결 해제 및 프로필 변경은 AUTO를 해제합니다. 승인·거부 기능은 현재 앱에 키를 보내는 동작이며 IDE의 승인 API에 직접 연결되지 않습니다.

원본 AhaKey의 기본 화면과 LED 효과를 이식했습니다. SD의 `/ahakey/` 사용자 이미지와 NVS에 저장된 키 설정도 지원합니다. 원본 앱 연동에는 BLE 서비스 `0x7340`을 사용합니다.

## Windows 음성 수신기

**Python 3.12**를 권장합니다. 테스트의 표준 ADPCM 비교 도구인 `audioop` 때문에 현재 검증 환경도 Python 3.12입니다.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r tools/requirements-voice.txt
```

Bluetooth 전용 펌웨어를 설치한 ADV를 Windows에서 `AhaKey ADV` 키보드로 페어링한 뒤 실행합니다.

```powershell
.\start-voice-bluetooth.cmd
```

`Bluetooth audio ready`가 표시되면 텍스트 입력창을 클릭하고 G0로 녹음을 시작/종료합니다. 시작한 창에서 포커스가 바뀌면 자동 입력을 생략합니다. **Enter/메시지 전송 키는 누르지 않습니다.** 같은 창 안에서 다른 입력칸으로 옮겨가는 것은 구분하지 못합니다.

실행 파일은 `large-v3-turbo`, 한국어, CPU int8, 8개 스레드를 기본값으로 사용합니다. 최초 실행은 모델 다운로드가 필요합니다. 이후 모델이 캐시되어 있으면 인터넷 없이 로컬 인식할 수 있습니다. 별도 모델 폴더를 쓰려면 `AHAKEY_MODEL` 환경변수에 경로를 지정합니다.

```powershell
$env:AHAKEY_MODEL = 'D:\models\faster-whisper-large-v3-turbo'
.\start-voice-bluetooth.cmd
```

여러 ADV가 페어링됐거나 이름을 바꿨다면 `--ble-address AA:BB:CC:DD:EE:FF`로 **본인의 장치 주소**를 지정합니다. 녹음만 확인하고 싶다면 모델 없이 실행할 수 있습니다.

```powershell
.venv/Scripts/python.exe tools/voice_companion.py --ble --record-only
```

완료된 녹음과 인식 결과는 `recordings/`에 저장됩니다. 녹음 파일·텍스트·Wi-Fi 연결 코드는 Git에서 제외됩니다.

### USB / Wi-Fi

일반 펌웨어에서 USB 시리얼 또는 Wi-Fi를 선택할 수 있습니다. `COM_PORT`는 실제 ADV 포트로 바꿉니다.

```powershell
.venv/Scripts/python.exe tools/voice_companion.py --port COM_PORT --language ko --type
.\start-voice.cmd
```

Wi-Fi에서는 ADV의 Fn+W에 2.4GHz Wi-Fi 이름·비밀번호, PC IPv4와 수신기에 표시되는 16자리 연결 코드를 입력합니다. 같은 LAN에서 PC의 TCP 7345 수신이 가능해야 합니다. Bluetooth 전용 빌드는 Wi-Fi와 Fn+W 설정 화면을 사용하지 않으며 기존 Wi-Fi 설정은 보존합니다.

### 선택 기능: Codex 받아쓰기 브리지

```powershell
.venv/Scripts/python.exe -m pip install -r tools/requirements-bridge.txt
.\start-codex-mic-bluetooth.cmd
```

별도로 설치한 [VB-CABLE](https://vb-audio.com/Cable/)의 `CABLE Input` 출력과 Codex의 `CABLE Output` 입력을 사용합니다. 드라이버는 이 저장소에 포함하지 않습니다. 이 경로는 로컬 Whisper를 거치지 않고 오디오를 전달하므로 Codex 서비스 사용에는 인터넷이 필요합니다.

현재 창의 Codex 받아쓰기 단축키를 이용하는 실험 기능입니다. 실시간 음성 채팅 연결 API가 아니며, 앱 버전이나 사용자의 수동 토글에 따라 상태가 어긋날 수 있습니다. 일반 수신기와 동시에 실행하지 마십시오.

## 펌웨어 빌드

대상은 **ESP32-S3 / 8MB flash의 Cardputer ADV**입니다. 다른 Cardputer나 원본 AhaKey-X1용이 아닙니다.

```powershell
py -3.12 -m pip install platformio==6.1.19
pio run -e cardputer-adv-ble
pio run -e cardputer-adv
```

빌드 결과는 `.pio/build/<환경>/firmware.bin`입니다. M5Cardputer 1.1.1, M5Unified 0.2.21, M5GFX 0.2.28과 espressif32 7.0.1을 고정합니다.

**빌드와 설치는 별개입니다.** 저장소의 `partitions.csv`는 독립 설치용 레이아웃입니다. 이미 Launcher나 다른 앱이 설치된 기기에 일반 PlatformIO upload 또는 factory 이미지를 기록하면 기존 파티션과 앱이 교체될 수 있습니다. 전체 백업, 실제 파티션 테이블 및 앱 슬롯 용량을 확인한 후 해당 부트로더의 앱 설치 절차를 사용해야 합니다. 이 소스 공개본에는 특정 개인 기기에 맞춘 플래시 스크립트나 사전 빌드 이미지를 포함하지 않습니다.

## 테스트

Windows에서는 Visual Studio C++ Build Tools, CMake와 위 Python 환경이 필요합니다.

```powershell
.venv/Scripts/python.exe tools/test_host.py
```

이 명령은 CMake 빌드, C++ 프로토콜 테스트와 Python 테스트를 실행합니다. 실제 장치에 연결하거나 펌웨어를 기록하지 않습니다. 테스트는 PCM/ADPCM 프레임, CRC/순서 오류, BLE 재연결·버퍼 제한, 입력 포커스 및 키 동작을 다룹니다. 테스트 통과가 실제 마이크 품질이나 배터리 사용 시간을 증명하지는 않습니다.

## 라이선스와 출처

[Apache-2.0](LICENSE). [NOTICE](NOTICE)에 원본 저장소·커밋과 이식한 파일을 명시했습니다. 원본 프로젝트: [AhakeyAI/desktop](https://github.com/AhakeyAI/desktop). AhaKey, M5Stack 및 OpenAI가 배포하거나 보증하는 공식 제품이 아닙니다.

더 자세한 Bluetooth 구조와 검증 한계는 [BLUETOOTH.md](BLUETOOTH.md)를 참고하십시오.
