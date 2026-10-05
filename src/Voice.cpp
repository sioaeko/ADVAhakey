#include <M5Cardputer.h>
#include <Arduino.h>
#include "Voice.h"
#include "InputRouter.h"
#include "NetVoice.h"
#include "BleVoice.h"
#include "VoiceAdpcm.h"
static bool wifiSession=false;
std::atomic<bool> micRequested{false},micActive{false};
std::atomic<uint32_t> micHeartbeat{0};
std::atomic<unsigned> micLevel{0},micError{0};
static uint32_t session=0,sequence=0;
static std::atomic<unsigned> audioPackets{0};
static std::atomic<unsigned> failureStage{0};
static int adpcmIndex=0;
#ifdef AHA_VOICE_BLE_ONLY
static constexpr unsigned CaptureSamples=640; // 40 ms, above DMA/task scheduling bursts.
static constexpr const char* WirelessName="ble";
#else
static constexpr unsigned CaptureSamples=160;
static constexpr const char* WirelessName="wifi";
#endif
void reportVoice(){if(!micActive||wifiSession)Serial.printf("AHA-VOICE requested=%u active=%u transport=%s error=%u stage=%u level=%u packets=%u\n",unsigned(micRequested.load()),unsigned(micActive.load()),wifiSession?WirelessName:"usb",unsigned(micError.load()),unsigned(failureStage.load()),unsigned(micLevel.load()),unsigned(audioPackets.load()));}
// AVP1 | type:u8 session:u32 seq:u32 length:u16 | payload | crc32(header+payload)
static bool emit(uint8_t type,const uint8_t* data=nullptr,uint16_t n=0){
 uint8_t packet[339];memcpy(packet,"AVP1",4);packet[4]=type;
 memcpy(packet+5,&session,4);memcpy(packet+9,&sequence,4);memcpy(packet+13,&n,2);
 if(n)memcpy(packet+15,data,n);uint32_t crc=aha::crc32(packet+4,11+n);memcpy(packet+15+n,&crc,4);sequence++;
#ifdef AHA_VOICE_BLE_ONLY
 bool sent=wifiSession?sendBleVoice(packet,19+n):(Serial && Serial.write(packet,19+n)==size_t(19+n));
#else
 bool sent=wifiSession?sendNetwork(packet,19+n):(Serial && Serial.write(packet,19+n)==size_t(19+n));
#endif
 if(sent&&(type==2||type==5))audioPackets++;return sent;
}
static bool usbLive(){uint32_t h=micHeartbeat.load();return h&&uint32_t(millis()-h)<2500&&Serial;}
static bool emitSamples(const int16_t* samples){
#ifdef AHA_VOICE_BLE_ONLY
 if(wifiSession){
  uint8_t block[163];
  for(unsigned offset=0;offset<CaptureSamples;offset+=320){aha::encodeVoiceAdpcm(samples+offset,block,adpcmIndex);if(!emit(5,block,sizeof(block)))return false;}
  return true;
 }
#endif
 for(unsigned offset=0;offset<CaptureSamples;offset+=160)if(!emit(2,(const uint8_t*)(samples+offset),320))return false;
 return true;
}
static bool live(){if(wifiSession){
#ifdef AHA_VOICE_BLE_ONLY
 return bleVoiceReady();
#else
 pollNetwork(false);return networkReady();
#endif
 }return usbLive();}
static void voiceTask(void*){
 int16_t samples[2][CaptureSamples];
 for(;;){
  pollNetwork();
  if(!micRequested){vTaskDelay(pdMS_TO_TICKS(5));continue;}
  wifiSession=!usbLive();
  if(!live()){micError=1;vTaskDelay(pdMS_TO_TICKS(20));continue;}
#ifdef AHA_VOICE_BLE_ONLY
  if(wifiSession&&!startBleVoice()){micError=3;micRequested=false;continue;}
#endif
  M5Cardputer.Speaker.end();
  if(!M5Cardputer.Mic.begin()){micError=2;micRequested=false;continue;}
  session=esp_random();sequence=0;audioPackets=0;adpcmIndex=0;failureStage=0;micError=0;uint32_t started=millis();
  bool ok=emit(1);micActive=ok;
  if(ok)ok=M5Cardputer.Mic.record(samples[0],CaptureSamples,16000)&&M5Cardputer.Mic.record(samples[1],CaptureSamples,16000);
  if(!ok)failureStage=1;
  unsigned index=0;
  while(ok&&micRequested&&live()&&millis()-started<60000){
   uint32_t waitStart=millis();
   while(M5Cardputer.Mic.isRecording()>1&&millis()-waitStart<100) vTaskDelay(1);
   if(M5Cardputer.Mic.isRecording()>1){failureStage=2;ok=false;break;}
#ifdef AHA_VOICE_BLE_ONLY
   // If both buffers emptied, capture has already stalled. Reject this take
   // instead of presenting discontinuous audio as a complete recording.
   if(wifiSession&&!M5Cardputer.Mic.isRecording()){failureStage=3;ok=false;break;}
#endif
   auto buf=samples[index];unsigned peak=0;for(unsigned i=0;i<CaptureSamples;i++){unsigned a=abs(int(buf[i]));if(a>peak)peak=a;}micLevel=peak;
   ok=emitSamples(buf);
   if(!ok)failureStage=4;
   if(ok){ok=M5Cardputer.Mic.record(buf,CaptureSamples,16000);if(!ok)failureStage=5;}
   index^=1;
  }
  // Flush the two queued buffers on a clean release, preserving word endings.
  if(ok&&live()){
   uint32_t drainStart=millis();
   while(M5Cardputer.Mic.isRecording()&&millis()-drainStart<100)vTaskDelay(1);
   if(M5Cardputer.Mic.isRecording()){ok=false;failureStage=6;}
   else{ok=emitSamples(samples[index])&&emitSamples(samples[index^1]);if(!ok)failureStage=7;}
  }
  M5Cardputer.Mic.end();
  bool success=ok&&live();bool ended=emit(success?3:4);success=success&&ended;
#ifdef AHA_VOICE_BLE_ONLY
  if(wifiSession){bool flushed=finishBleVoice();success=success&&flushed;}
#endif
  micActive=false;micLevel=0;
  if(!success){micError=3;if(!failureStage)failureStage=8;}
  // Require releasing PTT after timeout/failure; never restart while held.
  while(micRequested)vTaskDelay(pdMS_TO_TICKS(5));
 }
}
void beginVoice(){
 beginNetwork();
 Serial.setTxTimeoutMs(20);
 if(xTaskCreatePinnedToCore(voiceTask,"ahakey-mic",12288,nullptr,1,nullptr,0)!=pdPASS)micError=4;
}
extern void reportDiagnostics();
void pollVoiceHost(){
 static char line[24];static unsigned used=0;
 for(int count=0;count<64&&Serial.available();count++){
  char c=Serial.read();if(c=='\n'){line[used]=0;if(!strcmp(line,"AHA-MIC"))micHeartbeat=millis();else if(!strcmp(line,"AHA-INFO"))reportDiagnostics();else if(!strcmp(line,"AHA-WIFI-ON"))enableNetwork();used=0;}
  else if(c!='\r'){if(used<sizeof(line)-1)line[used++]=c;else used=0;}
 }
}
