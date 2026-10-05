#ifdef AHA_VOICE_BLE_ONLY
#include "BleVoice.h"
#include <Arduino.h>
#include <BLEServer.h>
#include <BLEDevice.h>
#include <BLE2902.h>
#include <esp_gatt_common_api.h>
#include <atomic>
#include "Dashboard.h"
#include "Voice.h"

// Private service; the existing HID and AhaKey configuration services keep their UUIDs.
static constexpr const char* serviceUuid="c0a17340-7d8e-4a15-9f4a-2b0c73a10000";
static constexpr const char* audioUuid="c0a17341-7d8e-4a15-9f4a-2b0c73a10000";
static constexpr const char* controlUuid="c0a17342-7d8e-4a15-9f4a-2b0c73a10000";
static BLEServer* server;
static BLECharacteristic* audio;
static BLE2902* subscription;
static std::atomic<unsigned> interfaceId{ESP_GATT_IF_NONE};
static std::atomic<uint32_t> heartbeat{0},owner{0},epoch{0};
static uint32_t recordingEpoch=0; // Owned by the microphone task.
static std::atomic<unsigned> connection{0xffff},mtu{23},pending{0},overruns{0},failures{0},sent{0},highWater{0};
static std::atomic<unsigned> txError{0},txOffset{0},txCredits{0};
static std::atomic<bool> faulty{false};
struct Frame {uint32_t epoch;uint16_t length;uint8_t bytes[339];};
static QueueHandle_t frames;

bool bleVoiceReady(){
 return frames&&owner&&connection!=0xffff&&mtu>=185&&subscription->getNotifications()&&uint32_t(millis()-heartbeat.load())<2500;
}
class Control:public BLECharacteristicCallbacks {
 void onWrite(BLECharacteristic* c,esp_ble_gatts_cb_param_t* p) override {
  auto data=c->getValue();if(data.size()<8)return;
  uint32_t token;memcpy(&token,data.data()+4,4);if(!token)return;
  bool same=owner==token&&connection==p->write.conn_id;
  if(!memcmp(data.data(),"AVD1",4)){
   if(same&&uint32_t(millis()-heartbeat.load())<2500)receiveDashboard((const uint8_t*)data.data()+8,data.size()-8);
   return;
  }
  if(data.size()!=8)return;
  if(!memcmp(data.data(),"AVH0",4)) {if(same){owner=0;faulty=true;epoch++;}return;}
  if(memcmp(data.data(),"AVH1",4))return;
  if(owner&&!same&&uint32_t(millis()-heartbeat.load())<2500)return;
  // Windows must pair/encrypt before this write is accepted by GATT permissions.
  // A random per-process lease prevents two companions sharing one physical link.
  if(!same){epoch++;faulty=true;}
  connection=p->write.conn_id;mtu=server->getPeerMTU(p->write.conn_id);
  owner=token;heartbeat=millis();
 }
 void onRead(BLECharacteristic* c,esp_ble_gatts_cb_param_t*) override {
  uint8_t value[12];memcpy(value,"AVS1",4);uint32_t token=owner.load();
  uint16_t negotiated=mtu.load(),flags=(bleVoiceReady()?1:0)|2|(micError.load()<<8);
  memcpy(value+4,&token,4);memcpy(value+8,&negotiated,2);memcpy(value+10,&flags,2);c->setValue(value,sizeof(value));
 }
};
void disconnectBleVoice(uint16_t id){if(connection==id){owner=0;connection=0xffff;mtu=23;faulty=true;epoch++;}}

static bool sendFrame(Frame& frame){
 size_t offset=0;bool abort=frame.bytes[4]==4;uint32_t started=millis();
 while(offset<frame.length){
  if(frame.epoch!=epoch||!bleVoiceReady()||(!abort&&faulty))return false;
  if(millis()-started>=500){txError=1;txOffset=offset;return false;}
  auto id=uint16_t(connection.load());
  // Leave controller capacity for keyboard reports while audio is flowing.
  unsigned credits=esp_ble_get_cur_sendable_packets_num(id);txCredits=credits;
  if(credits<=1){vTaskDelay(1);continue;}
  size_t length=std::min(size_t(mtu.load()-3),size_t(frame.length-offset));
  auto result=esp_ble_gatts_send_indicate(esp_gatt_if_t(interfaceId.load()),id,audio->getHandle(),length,frame.bytes+offset,false);
  if(result!=ESP_OK){txError=result;txOffset=offset;return false;} // Never duplicate ambiguous sends.
  offset+=length;
 }
 return true;
}
static void sender(void*){
 Frame frame;
 for(;;){
  if(xQueueReceive(frames,&frame,portMAX_DELAY)!=pdTRUE)continue;
  if(frame.epoch==epoch){
   if(sendFrame(frame))sent++;
   else{faulty=true;failures++;}
  }
  pending--;
 }
}
void setupBleVoice(BLEServer* s){
 server=s;
 BLEDevice::setCustomGattsHandler([](esp_gatts_cb_event_t event,esp_gatt_if_t id,esp_ble_gatts_cb_param_t*){
  if(event==ESP_GATTS_CONNECT_EVT)interfaceId=id;
 });
 auto service=server->createService(BLEUUID(serviceUuid));
 audio=service->createCharacteristic(audioUuid,BLECharacteristic::PROPERTY_NOTIFY);
 subscription=new BLE2902();
 subscription->setAccessPermissions(esp_gatt_perm_t(ESP_GATT_PERM_READ_ENCRYPTED|ESP_GATT_PERM_WRITE_ENCRYPTED));
 audio->addDescriptor(subscription);
 auto control=service->createCharacteristic(controlUuid,BLECharacteristic::PROPERTY_READ|BLECharacteristic::PROPERTY_WRITE);
 control->setAccessPermissions(esp_gatt_perm_t(ESP_GATT_PERM_READ_ENCRYPTED|ESP_GATT_PERM_WRITE_ENCRYPTED));
 control->setCallbacks(new Control());service->start();
 frames=xQueueCreate(64,sizeof(Frame));
 if(frames&&xTaskCreatePinnedToCore(sender,"ahakey-ble-tx",4096,nullptr,1,nullptr,0)!=pdPASS){vQueueDelete(frames);frames=nullptr;}
}
bool startBleVoice(){
 uint32_t start=millis();while(pending&&millis()-start<1500)vTaskDelay(1);
 if(pending||!bleVoiceReady())return false;
 recordingEpoch=++epoch;faulty=false;sent=0;highWater=0;txError=0;txOffset=0;return true;
}
bool sendBleVoice(const uint8_t* data,size_t length){
 if(length<19||length>339||recordingEpoch!=epoch||!bleVoiceReady()||(faulty&&data[4]!=4))return false;
 Frame frame;frame.epoch=recordingEpoch;frame.length=length;memcpy(frame.bytes,data,length);
 auto depth=++pending;
 if(xQueueSend(frames,&frame,0)!=pdTRUE){pending--;overruns++;faulty=true;return false;}
 if(depth>highWater)highWater=depth;return true;
}
bool finishBleVoice(){
 uint32_t start=millis();while(pending&&millis()-start<1500)vTaskDelay(1);
 if(pending){faulty=true;epoch++;}
 return !pending&&!faulty&&recordingEpoch==epoch&&bleVoiceReady();
}
void reportBleVoice(){
 Serial.printf("AHA-BLE ready=%u mtu=%u pending=%u high=%u overruns=%u failures=%u sent=%u wifi=disabled\n",bleVoiceReady(),unsigned(mtu.load()),unsigned(pending.load()),unsigned(highWater.load()),unsigned(overruns.load()),unsigned(failures.load()),unsigned(sent.load()));
 Serial.printf("AHA-BLE-TX error=%u offset=%u credits=%u codec=ima-adpcm\n",unsigned(txError.load()),unsigned(txOffset.load()),unsigned(txCredits.load()));
}
#endif
