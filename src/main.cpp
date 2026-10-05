#include "StickyFn.h"
#include <M5Cardputer.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <SD.h>
#include <SPI.h>
#include <atomic>
#include "Protocol.h"
#include "Gate.h"
#include "OriginalDefaults.h"
#include "AdvLed.h"
#include "FactoryFrames.h"
#include <esp32s3/rom/miniz.h>
#include <USB.h>
#include <esp_system.h>
#include <USBHID.h>
#include "InputRouter.h"
#include "Voice.h"
#include "NetVoice.h"
#include "BleVoice.h"
#include "FirmwareVersion.h"
#include "Dashboard.h"

aha::Config config;
Preferences prefs;
BLECharacteristic *response, *keyboardReport;
BLEHIDDevice* hid;
std::atomic<bool> connected{false}, dropped{false}, overflow{false};
struct Packet { bool data; uint16_t size; uint8_t bytes[512]; };
QueueHandle_t incoming;
aha::Gate gate;
uint8_t ideState=0, effect=11;
bool sdReady=false, dirty=true;
aha::InputRouter inputRouter;
uint32_t lastStatus=0, lastDraw=0, uploadTime=0;

int padPrevious=-1;
uint64_t previousKeys=0;
uint8_t report[8]={};
uint8_t upload[4096]; uint16_t uploadExpected=0, uploadUsed=0; uint32_t uploadAddress=0;
aha::Key running; bool macroActive=false; uint8_t macroPos=0; uint32_t macroDue=0;
uint16_t frameBuffer[160*80];
uint16_t animationIndex=0; uint32_t animationTime=0;
uint32_t modeNoticeUntil=0, lastLight=0, displayedCRC=0;
uint16_t displayedFrame=0xffff;bool factoryDisplayed=false,ledReady=false;
aha::LightRGB currentLED{};
void modeNotice(unsigned duration){modeNoticeUntil=millis()+duration;animationIndex=0;animationTime=millis();dirty=true;}
const char* states[]={"Notification","Permission needed","Tool complete","Working","Session started","Stopped","Task complete","Prompt sent","Idle"};
const uint8_t hidMap[]={
 0x05,0x01,0x09,0x06,0xa1,0x01,0x85,0x01,
 0x05,0x07,0x19,0xe0,0x29,0xe7,0x15,0x00,0x25,0x01,0x75,0x01,0x95,0x08,0x81,0x02,
 0x95,0x01,0x75,0x08,0x81,0x01,
 0x95,0x05,0x75,0x01,0x05,0x08,0x19,0x01,0x29,0x05,0x91,0x02,
 0x95,0x01,0x75,0x03,0x91,0x01,
 0x95,0x06,0x75,0x08,0x15,0x00,0x26,0xff,0x00,0x05,0x07,0x19,0x00,0x2a,0xff,0x00,0x81,0x00,0xc0};
class USBKeyboard:public USBHIDDevice {
 public:
 USBHID usb;
 USBKeyboard(){usb.addDevice(this,sizeof(hidMap));}
 uint16_t _onGetDescriptor(uint8_t* dest) override {memcpy(dest,hidMap,sizeof(hidMap));return sizeof(hidMap);}
} usbKeyboard;
bool usedUSB=false, usbPending=false;
uint32_t pulseDue=0;
void sendReport(){
 bool useUSB=bool(USB);
 if(useUSB!=usedUSB){uint8_t zero[8]={};if(connected){keyboardReport->setValue(zero,8);keyboardReport->notify();}usedUSB=useUSB;}
 if(useUSB)usbPending=!usbKeyboard.usb.SendReport(1,report,8,10);
 else if(connected){keyboardReport->setValue(report,8);keyboardReport->notify();}
}
void release(){ memset(report,0,8);sendReport(); }
void key(uint8_t code,bool down){
 if(code>=0xe0&&code<=0xe7){if(down)report[0]|=1<<(code-0xe0);else report[0]&=~(1<<(code-0xe0));}
 else if(code){ if(down){for(int i=2;i<8;i++)if(report[i]==code)return;for(int i=2;i<8;i++)if(!report[i]){report[i]=code;break;}}else for(int i=2;i<8;i++)if(report[i]==code)report[i]=0; }
}
void reply(uint8_t cmd,const uint8_t* bytes,size_t size){
 uint8_t b[32]={0xaa,0xbb,cmd}; if(size>27)return;memcpy(b+3,bytes,size);b[size+3]=0xcc;b[size+4]=0xdd;
 response->setValue(b,size+5);if(connected)response->notify();
}
void ack(uint8_t cmd,uint8_t status=0){reply(cmd,&status,1);}
void status(){
 int bat=M5Cardputer.Power.getBatteryLevel(); uint8_t b[]={uint8_t(constrain(bat,0,100)),0,1,3,config.mode,effect,gate.value(),config.brightness};reply(0,b,8);hid->setBatteryLevel(b[0]);
}
void manual(){gate.reset();dirty=true;}
void cancel(){pulseDue=0;macroActive=false;release();}
class ServerCallbacks:public BLEServerCallbacks {
 void onConnect(BLEServer*) override {connected=true;}
 void onDisconnect(BLEServer*) override {connected=false;dropped=true;}
#ifdef AHA_VOICE_BLE_ONLY
 void onConnect(BLEServer*,esp_ble_gatts_cb_param_t* p) override {
  esp_ble_conn_update_params_t params{};memcpy(params.bda,p->connect.remote_bda,6);
  params.min_int=6;params.max_int=12;params.latency=0;params.timeout=400;
  esp_ble_gap_update_conn_params(&params);
  esp_ble_gap_set_pkt_data_len(p->connect.remote_bda,251);
 }
 void onDisconnect(BLEServer*,esp_ble_gatts_cb_param_t* p) override {disconnectBleVoice(p->disconnect.conn_id);}
#endif
};
class WriteCallbacks:public BLECharacteristicCallbacks {
 bool isData;
 public:explicit WriteCallbacks(bool data):isData(data){}
 void onWrite(BLECharacteristic* c) override {
  auto value=c->getValue();if(value.empty()||value.size()>512){overflow=true;return;}
  Packet p{};p.data=isData;p.size=value.size();memcpy(p.bytes,value.data(),p.size);
  if(xQueueSend(incoming,&p,0)!=pdTRUE)overflow=true;
 }
};
void defaults(){aha::originalDefaults(config);}
void command(const uint8_t* b,size_t size){
 if(!aha::frame(b,size))return;
 uint8_t cmd=b[2];const uint8_t* p=b+3;size_t n=size-5;
 if(!aha::valid(cmd,p,n)){ack(cmd,1);return;}
 switch(cmd){
 case 0:status();return;
 case 1:memset(config.name,0,22);memcpy(config.name,p,n);break;
 case 2:config.appearance=n==2?aha::le16(p):p[0];break;
 case 4:if(prefs.putBytes("config",&config,sizeof(config))!=sizeof(config)){ack(cmd,2);return;}break;
 case 0x73:{auto& k=config.keys[p[1]][p[2]];if(p[0]==0x75){memset(k.label,0,21);memcpy(k.label,p+3,n-3);}else{k.type=p[0];k.length=n-3;memcpy(k.data,p+3,n-3);}break;}
 case 0x80:
  if(!sdReady){ack(cmd,2);return;}
  uploadExpected=aha::le16(p+1);uploadAddress=aha::le32(p+3);uploadUsed=0;uploadTime=millis();break;
 case 0x82:{auto& pic=config.pictures[p[0]];pic.start=aha::le16(p+1);pic.count=aha::le16(p+3);pic.interval=aha::le16(p+5);animationIndex=0;break;}
 case 0x83:{auto pic=config.pictures[p[0]];uint8_t out[]={0,p[0],uint8_t(pic.start),uint8_t(pic.start>>8),uint8_t(pic.count),uint8_t(pic.count>>8),uint8_t(pic.interval),uint8_t(pic.interval>>8),70,0};reply(cmd,out,sizeof(out));return;}
 case 0x84:for(int i=0;i<9;i++)config.effects[p[0]][i]=p[i+1]<=16?p[i+1]:0;if(p[0]==config.mode)effect=config.effects[config.mode][ideState];break;
 case 0x85:config.brightness=p[0];break;
 case 0x90:ideState=p[0];effect=config.effects[config.mode][ideState];break;
 case 0x91:effect=p[0];break;
 case 0x92:cancel();manual();config.mode=p[0];modeNotice(1000);effect=config.effects[config.mode][ideState];break;
 }
 dirty=true;ack(cmd);
}
void data(const uint8_t* b,size_t n){
 if(!uploadExpected||n>size_t(uploadExpected-uploadUsed)){uploadExpected=0;ack(0x81,1);return;}
 memcpy(upload+uploadUsed,b,n);uploadUsed+=n;uploadTime=millis();
 if(uploadUsed!=uploadExpected)return;
 char path[40];snprintf(path,sizeof(path),"/ahakey/%lu.bin",(unsigned long)(uploadAddress/aha::Slot));
 // Each frame is independent. Never format the card or touch other directories.
 File f=SD.open(path,SD.exists(path)?"r+":"w+");
 bool ok=false;if(f){ok=f.seek(uploadAddress%aha::Slot)&&f.write(upload,uploadExpected)==uploadExpected;f.flush();f.close();}
 uploadExpected=0;ack(0x81,ok?0:2);
}
void startKey(int index){
 cancel();running=config.keys[config.mode][index];
 if(running.type==0x73){for(int i=0;i<running.length;i++)key(running.data[i],true);sendReport();pulseDue=millis()+40;}
 else {macroActive=true;macroPos=0;macroDue=millis();}
}
void tickMacro(){
 if(!macroActive||int32_t(millis()-macroDue)<0)return;
 if(macroPos>=running.length){cancel();return;}
 uint8_t a=running.data[macroPos++],p=running.data[macroPos++];
 switch(a){case 1:key(p,true);sendReport();break;case 2:key(p,false);sendReport();break;case 3:macroDue=millis()+uint32_t(p)*3;return;case 4:release();break;}
 macroDue=millis()+8;
}
void setupBLE(){
 BLEDevice::init(config.name);BLEDevice::setMTU(185);
 auto server=BLEDevice::createServer();server->setCallbacks(new ServerCallbacks());
 hid=new BLEHIDDevice(server);keyboardReport=hid->inputReport(1);hid->outputReport(1);
 hid->manufacturer()->setValue("AhaKey ADV community port");hid->pnp(2,0x303a,0x1001,0x0100);hid->hidInfo(0,1);
 hid->reportMap((uint8_t*)hidMap,sizeof(hidMap));
 auto info=server->getServiceByUUID(BLEUUID(uint16_t(0x180a)));
 if(info){info->createCharacteristic(BLEUUID(uint16_t(0x2a24)),BLECharacteristic::PROPERTY_READ)->setValue("Cardputer ADV");info->createCharacteristic(BLEUUID(uint16_t(0x2a26)),BLECharacteristic::PROPERTY_READ)->setValue(AHA_VERSION);}
 hid->startServices();
 auto svc=server->createService(BLEUUID(uint16_t(0x7340)));
 auto input=svc->createCharacteristic(BLEUUID(uint16_t(0x7341)),BLECharacteristic::PROPERTY_WRITE|BLECharacteristic::PROPERTY_WRITE_NR);input->setCallbacks(new WriteCallbacks(true));
 auto inf=svc->createCharacteristic(BLEUUID(uint16_t(0x7342)),BLECharacteristic::PROPERTY_READ);uint8_t zero[200]={};inf->setValue(zero,200);
 auto cmd=svc->createCharacteristic(BLEUUID(uint16_t(0x7343)),BLECharacteristic::PROPERTY_WRITE|BLECharacteristic::PROPERTY_WRITE_NR);cmd->setCallbacks(new WriteCallbacks(false));
 response=svc->createCharacteristic(BLEUUID(uint16_t(0x7344)),BLECharacteristic::PROPERTY_READ|BLECharacteristic::PROPERTY_NOTIFY);response->addDescriptor(new BLE2902());svc->start();
#ifdef AHA_VOICE_BLE_ONLY
 setupBleVoice(server);
#endif
 auto security=new BLESecurity();security->setAuthenticationMode(ESP_LE_AUTH_BOND);security->setCapability(ESP_IO_CAP_NONE);security->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK|ESP_BLE_ID_KEY_MASK);
 auto adv=BLEDevice::getAdvertising();adv->setAppearance(config.appearance);adv->addServiceUUID(svc->getUUID());adv->addServiceUUID(hid->hidService()->getUUID());adv->setScanResponse(true);adv->start();
}
void draw(){
 if(networkUiVisible())return;
 static bool wasDashboard=false;
 if(drawDashboard()){wasDashboard=true;return;}
 if(wasDashboard){M5Cardputer.Display.fillScreen(TFT_BLACK);wasDashboard=false;}
 auto& d=M5Cardputer.Display;
 bool notice=int32_t(modeNoticeUntil-millis())>0;
 static bool wasNotice=false;
 if(notice){
  d.fillScreen(TFT_CYAN);d.setTextSize(1);d.setTextColor(TFT_MAGENTA,TFT_CYAN);d.setCursor(8,8);
  d.printf("Mode %u   %d%%   %s",config.mode+1,constrain(M5Cardputer.Power.getBatteryLevel(),0,100),USB?"HID":connected?"OK":"ing");
  d.setTextColor(TFT_RED,TFT_CYAN);
  for(int i=0;i<4;i++){d.setCursor(8,30+i*22);d.printf("%s",config.keys[config.mode][i].label);}
  wasNotice=true;return;
 }
 if(wasNotice){d.fillScreen(TFT_BLACK);wasNotice=false;}
 bool loaded=false;auto pic=config.pictures[config.mode];
 if(pic.count&&sdReady){
  char path[40];snprintf(path,sizeof(path),"/ahakey/%u.bin",pic.start+animationIndex%pic.count);
  File f=SD.open(path,"r");if(f){loaded=f.read((uint8_t*)frameBuffer,sizeof(frameBuffer))==sizeof(frameBuffer);f.close();}
  factoryDisplayed=false;displayedFrame=pic.start+animationIndex%pic.count;
 }
 if(!loaded&&config.mode<3){
  unsigned index=config.mode==0?animationIndex%8:config.mode==1?8:9;
  const auto& f=aha::factoryFrames[index];
  // ROM decoder state exceeds the default Arduino loop stack: keep it in static RAM.
  static tinfl_decompressor decoder;tinfl_init(&decoder);size_t inputSize=f.size,outputSize=sizeof(frameBuffer);
  loaded=tinfl_decompress(&decoder,f.data,&inputSize,(uint8_t*)frameBuffer,(uint8_t*)frameBuffer,&outputSize,TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF)==TINFL_STATUS_DONE&&outputSize==sizeof(frameBuffer);
  factoryDisplayed=true;displayedFrame=index;
 }
 if(loaded){
  displayedCRC=aha::crc32((uint8_t*)frameBuffer,sizeof(frameBuffer));
  for(auto& pixel:frameBuffer)pixel=(pixel>>8)|(pixel<<8);
  // Original 160x80 aspect ratio, scaled 1.5x on ADV; black letterbox, no status dashboard.
  // frameBuffer contains native-endian RGB565; LGFX defaults to wire-endian.
  const bool previousSwap=d.getSwapBytes();d.setSwapBytes(true);
  uint16_t line[240];
  for(int y=0;y<120;y++){
   const uint16_t* src=frameBuffer+(y*2/3)*160;
   for(int x=0;x<240;x++)line[x]=src[x*2/3];
   d.pushImage(0,7+y,240,1,line);
  }
  d.setSwapBytes(previousSwap);
 }else{d.fillScreen(TFT_BLACK);displayedCRC=0;displayedFrame=0xffff;factoryDisplayed=false;}
 if(micRequested||micActive){d.fillRect(0,116,240,19,TFT_BLACK);d.setTextSize(1);d.setTextColor(TFT_WHITE,TFT_BLACK);d.setCursor(6,121);d.print(micActive?"REC":micError==1?"Connect voice companion":"Microphone...");}
}
void tickLights(){
 if(!ledReady||millis()-lastLight<50)return;lastLight=millis();
 aha::LightRGB pixels[8];aha::originalLightFrame(effect,config.brightness,pixels);
 if(!USB&&!connected){
  bool on=(millis()/50%16)<8;unsigned alpha=on?128:64;
  unsigned level=alpha*config.brightness>>8;
  currentLED={uint8_t((on?16:0)*level>>8),uint8_t((on?32:0)*level>>8),uint8_t((on?128:8)*level>>8)};
 }else if(int32_t(modeNoticeUntil-millis())>0){
  unsigned level=128*config.brightness>>8;currentLED={uint8_t(16*level>>8),uint8_t(32*level>>8),uint8_t(128*level>>8)};
 }else currentLED=pixels[3]; // ADV has one RGB LED: sample the original strip's central pixel.
 if(!writeAdvLed(currentLED.r,currentLED.g,currentLED.b))ledReady=false;
}
void reportDiagnostics(){
 reportVoice();
 if(micActive)return;
#ifdef AHA_RECOVERY_NO_WIFI
 Serial.println("AHA-RECOVERY wifi=disabled led=disabled settings=preserved");
#endif
 reportNetwork();
#ifdef AHA_VOICE_BLE_ONLY
 reportBleVoice();
#endif
 Serial.printf("AHA-NET enabled=%u state=%u phase=%u stack=%u reset=%u uptime=%lu\n",unsigned(networkEnabled.load()),unsigned(netState.load()),unsigned(netPhase.load()),unsigned(voiceStackFree.load()),unsigned(esp_reset_reason()),(unsigned long)millis());
 Serial.printf("AHA-INFO version=" AHA_VERSION " mode=%u effect=%u brightness=%u led=%u count=%u rgb=%u,%u,%u factory=%u frame=%u crc=%08lx heap=%u\n",config.mode,effect,config.brightness,ledReady,unsigned(M5.Led.getCount()),currentLED.r,currentLED.g,currentLED.b,factoryDisplayed,displayedFrame,(unsigned long)displayedCRC,ESP.getFreeHeap());
}
void setup(){
 auto cfg=M5.config();M5Cardputer.begin(cfg,true);M5Cardputer.Display.setRotation(1);
#ifdef AHA_RECOVERY_NO_WIFI
 M5Cardputer.Display.setBrightness(120);
#else
 M5Cardputer.Display.setBrightness(255);
#endif
Serial.begin(115200);USB.productName("AhaKey ADV");usbKeyboard.usb.begin();USB.begin();
 defaults();prefs.begin("ahakey-adv",false);aha::Config saved;
 if(prefs.getBytesLength("config")==sizeof(saved)&&prefs.getBytes("config",&saved,sizeof(saved))==sizeof(saved)&&aha::validConfig(saved))config=saved;
 aha::migratePrototypeDefaults(config);effect=config.effects[config.mode][ideState];
 SPI.begin(40,39,14,12);sdReady=SD.begin(12,SPI,25000000);if(sdReady)sdReady=SD.exists("/ahakey")||SD.mkdir("/ahakey");
 incoming=xQueueCreate(24,sizeof(Packet));if(!incoming){M5Cardputer.Display.print("Queue allocation failed");while(true)delay(1000);}

#ifndef AHA_RECOVERY_NO_WIFI
 M5.Led.setAutoDisplay(false);ledReady=beginAdvLed();if(ledReady){writeAdvLed(48,48,48);delay(1200);writeAdvLed(0,0,0);}
#else
 ledReady=false;
#endif
 M5Cardputer.Display.fillScreen(TFT_BLACK);
 setupBLE();beginVoice();
}
void loop(){
 M5Cardputer.update();
 if(dropped.exchange(false)){padPrevious=-1;manual();cancel();uploadExpected=0;xQueueReset(incoming);BLEDevice::startAdvertising();}
 if(overflow.exchange(false)){manual();cancel();uploadExpected=0;xQueueReset(incoming);ack(0x81,3);}
 pollVoiceHost();
 uint64_t currentKeys=0;
 for(auto pos:M5Cardputer.Keyboard.keyList())currentKeys|=aha::keyBit(pos.x,pos.y);
 static aha::StickyFn stickyFn;
 uint64_t physicalKeys=currentKeys;
 currentKeys=stickyFn.update(physicalKeys,millis(),M5Cardputer.BtnA.wasPressed());
 bool captured=networkUi(currentKeys);
 if(captured)stickyFn.reset(physicalKeys);
 // Latch G0's purpose at press time; changing Fn while held must never arm AUTO.
 static bool g0Voice=false,g0Gate=false,g0SawActive=false;
 static uint32_t g0Started=0;
 if(g0Voice){
  if(micActive)g0SawActive=true;
  if((g0SawActive&&!micActive)||micError>=2||uint32_t(millis()-g0Started)>=61000)g0Voice=false;
 }
 uint8_t previousGate=gate.value();
 if(M5Cardputer.BtnA.wasPressed()){
  g0Gate=!captured&&(currentKeys&aha::Fn);
  if(g0Gate){g0Voice=false;gate.press(millis());}
  else if(!captured){
   g0Voice=!g0Voice;
   if(g0Voice){g0SawActive=false;g0Started=millis();micError=0;manual();cancel();previousKeys=~uint64_t(0);}
  }
 }
 if(M5Cardputer.BtnA.wasReleased()||!M5Cardputer.BtnA.isPressed()){
  g0Gate=false;gate.release();
 }
 if(captured){g0Voice=false;g0Gate=false;gate.release();}
 gate.tick(millis(),connected);
 if(previousGate!=gate.value()){dirty=true;status();}
 static bool wasCaptured=false;
 if(captured){if(!wasCaptured){cancel();manual();}micRequested=false;previousKeys=~uint64_t(0);wasCaptured=true;}
 else {if(wasCaptured){M5Cardputer.Display.fillScreen(TFT_BLACK);dirty=true;}wasCaptured=false;
 auto routed=inputRouter.update(currentKeys);
 micRequested=routed.voice||g0Voice;
 if(routed.nextMode){cancel();manual();config.mode=(config.mode+1)%4;effect=config.effects[config.mode][ideState];modeNotice(1500);status();}
 if(currentKeys!=previousKeys){
  previousKeys=currentKeys;
  if(routed.shortcut!=padPrevious){
   cancel();padPrevious=routed.shortcut;
   if(padPrevious>=0){if(padPrevious==1||padPrevious==2)manual();startKey(padPrevious);}
  }
  if(padPrevious<0&&!macroActive){
   memset(report,0,8);
   // Build directly from physical positions to prevent Fn chord release leaking a digit/space.
   bool fn=routed.keys&aha::Fn;
   for(auto pos:M5Cardputer.Keyboard.keyList()){
    if(!(routed.keys&aha::keyBit(pos.x,pos.y)))continue;
    auto value=M5Cardputer.Keyboard.getKeyValue(pos);uint8_t raw=value.value_first;
    if(raw==0xff)continue;
    if(raw>=0x80&&raw<=0x82){key(0xe0+raw-0x80,true);continue;}
    if(pos.x==1&&pos.y==3){key(0xe3,true);continue;}
    uint8_t code=fn?aha::fnUsage(pos.x,pos.y):((pos.x==0&&pos.y==1)||(pos.x==13&&(pos.y==0||pos.y==2))?raw:_kb_asciimap[raw]);
    if(code&&code!=0xff)key(code,true);
   }
   sendReport();
  }
 }
 }
 // Route changes while no keys are moving still release the old destination.
 if(bool(USB)!=usedUSB){cancel();previousKeys=~uint64_t(0);}
 Packet packet;for(int i=0;i<8&&xQueueReceive(incoming,&packet,0)==pdTRUE;i++){if(packet.data)data(packet.bytes,packet.size);else command(packet.bytes,packet.size);}
 if(uploadExpected&&millis()-uploadTime>5000){uploadExpected=0;ack(0x81,4);}
 if(pulseDue&&int32_t(millis()-pulseDue)>=0){pulseDue=0;release();}
 if(usbPending&&USB&&usbKeyboard.usb.ready())usbPending=!usbKeyboard.usb.SendReport(1,report,8,10);
 tickMacro();tickLights();
 if(millis()-lastStatus>=1000){status();lastStatus=millis();dirty=true;}
 auto pic=config.pictures[config.mode];unsigned frames=pic.count?pic.count:config.mode==0?8:config.mode<3?1:0;
 unsigned interval=pic.count?pic.interval:100;
 if(frames>1&&millis()-animationTime>=interval){animationIndex=(animationIndex+1)%frames;animationTime=millis();dirty=true;}
 static bool previousMicUI=false;bool micUI=micRequested||micActive;if(previousMicUI!=micUI){previousMicUI=micUI;dirty=true;}
 static bool noticeActive=false;bool noticeNow=int32_t(modeNoticeUntil-millis())>0;
 if(noticeActive!=noticeNow){noticeActive=noticeNow;dirty=true;}
 if(dirty&&millis()-lastDraw>=50){draw();dirty=false;lastDraw=millis();}
 delay(2);
}
