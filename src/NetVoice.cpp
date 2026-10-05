#ifdef AHA_VOICE_BLE_ONLY
#include <Arduino.h>
#include "NetVoice.h"
std::atomic<bool> networkEnabled{false};
std::atomic<unsigned> netPhase{0},voiceStackFree{0},netState{0};
void beginNetwork(){}
void enableNetwork(){}
void pollNetwork(bool){}
bool networkReady(){return false;}
bool sendNetwork(const uint8_t*,size_t){return false;}
NetConfig getNetworkConfig(){return NetConfig{};}
bool saveNetworkConfig(const NetConfig&){return false;}
void reportNetwork(){Serial.println("AHA-WIFI disabled (Bluetooth firmware); saved settings preserved");}
#else
#include <WiFi.h>
#include <Preferences.h>
#include <mbedtls/md.h>
#include <sys/socket.h>
#include "NetVoice.h"
std::atomic<bool> networkEnabled{true};
std::atomic<unsigned> netPhase{0},voiceStackFree{0};
static std::atomic<unsigned> disconnectReason{0};
static std::atomic<unsigned> sendError{0},sendWait{0},sendPartial{0},dropReason{0};
void reportNetwork(){
 Serial.printf("AHA-TCP drop=%u errno=%u wait=%u partial=%u\n",unsigned(dropReason.load()),unsigned(sendError.load()),unsigned(sendWait.load()),unsigned(sendPartial.load()));
 auto c=getNetworkConfig();
 Serial.printf("AHA-WIFI status=%u reason=%u ip=%s host=%s ssid=%s\n",unsigned(WiFi.status()),unsigned(disconnectReason.load()),WiFi.localIP().toString().c_str(),c.host,c.ssid);
}
void enableNetwork(){networkEnabled=true;}
std::atomic<unsigned> netState{0}; // 0 off, 1 wifi, 2 PC/auth, 3 ready, 4 auth error
static NetConfig settings;
static SemaphoreHandle_t configMutex;
static uint32_t revision=0;
static WiFiClient client;
static bool authenticated=false;
static uint32_t heartbeat=0,connectedAt=0,nextTry=0,wifiTry=0,applied=~0u;
static NetConfig current;
static char line[128],nonce[33];static unsigned used=0;
void beginNetwork(){
 WiFi.onEvent([](WiFiEvent_t event,WiFiEventInfo_t info){if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED)disconnectReason=info.wifi_sta_disconnected.reason;});
 configMutex=xSemaphoreCreateMutex();
 Preferences p;p.begin("ahakey-net",true);NetConfig c;
 if(p.getBytesLength("config")==sizeof(c)&&p.getBytes("config",&c,sizeof(c))==sizeof(c)&&validNet(c))settings=c;
 p.end();
}
NetConfig getNetworkConfig(){xSemaphoreTake(configMutex,portMAX_DELAY);auto c=settings;xSemaphoreGive(configMutex);return c;}
bool saveNetworkConfig(const NetConfig& c){
 if(!validNet(c))return false;
 Preferences p;if(!p.begin("ahakey-net",false))return false;bool ok=p.putBytes("config",&c,sizeof(c))==sizeof(c);p.end();
 if(ok){xSemaphoreTake(configMutex,portMAX_DELAY);settings=c;revision++;xSemaphoreGive(configMutex);}return ok;
}
static void drop(){client.stop();authenticated=false;heartbeat=0;used=0;nonce[0]=0;nextTry=millis()+3000;}
static bool sendBounded(const uint8_t* p,size_t n){
 uint32_t start=millis();size_t sent=0;
 // BLE coexistence/modem sleep can stall a writable TCP socket beyond 30 ms.
 // Bound retries below the heartbeat deadline instead of dropping healthy sessions.
 while(sent<n&&client.connected()&&millis()-start<1000){
  int result=send(client.fd(),p+sent,n-sent,MSG_DONTWAIT);
  if(result>0)sent+=result;else if(result<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)break;else vTaskDelay(1);
 }
 if(sent!=n){sendError=errno;sendWait=millis()-start;sendPartial=sent;dropReason=1;drop();return false;}return true;
}
static void proof(const char* role,char out[65]){
 char message[48];snprintf(message,sizeof(message),"%s:%s",role,nonce);uint8_t digest[32];
 mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),(const uint8_t*)current.token,16,(const uint8_t*)message,strlen(message),digest);
 for(int i=0;i<32;i++)sprintf(out+i*2,"%02x",digest[i]);
}
void pollNetwork(bool reconnect){
#ifdef AHA_RECOVERY_NO_WIFI
 netState=0;return;
#endif
 if(!networkEnabled)return;
 voiceStackFree=uxTaskGetStackHighWaterMark(nullptr);
 xSemaphoreTake(configMutex,portMAX_DELAY);uint32_t rev=revision;NetConfig cfg=settings;xSemaphoreGive(configMutex);
 if(rev!=applied){netPhase=1;drop();current=cfg;applied=rev;WiFi.persistent(false);WiFi.disconnect(false,false);
  if(current.ssid[0]){netPhase=2;if(!WiFi.mode(WIFI_STA)){netState=5;networkEnabled=false;return;}netPhase=3;// ESP32-S3 BLE coexistence requires modem sleep; WIFI_PS_NONE causes PANIC.
   WiFi.setSleep(WIFI_PS_MIN_MODEM);netPhase=5;WiFi.begin(current.ssid,current.password);netPhase=4;wifiTry=millis();}else WiFi.mode(WIFI_OFF);
 }
 if(!current.ssid[0]){netState=0;return;}
 if(WiFi.status()!=WL_CONNECTED){if(client.connected()){dropReason=2;drop();}netState=1;if(millis()-wifiTry>15000){WiFi.reconnect();wifiTry=millis();}return;}
 if(!client.connected()){
  authenticated=false;netState=2;if(!reconnect||int32_t(millis()-nextTry)<0)return;
  IPAddress ip;ip.fromString(current.host);nextTry=millis()+3000;
  if(!client.connect(ip,7345,200))return;
  // Coalesce 10 ms audio frames; avoid exhausting Wi-Fi queues during modem sleep.
  client.setNoDelay(false);connectedAt=millis();used=0;nonce[0]=0;
 }
 for(int i=0;i<256&&client.available();i++){
  char c=client.read();
  if(c=='\n'){
   line[used]=0;used=0;
   if(!authenticated&&!strncmp(line,"AHA-CHALLENGE ",14)&&strlen(line)==46){
    memcpy(nonce,line+14,32);nonce[32]=0;char digest[65],answer[80];proof("client",digest);snprintf(answer,sizeof(answer),"AHA-AUTH %s\n",digest);sendBounded((uint8_t*)answer,strlen(answer));
   }else if(!authenticated&&nonce[0]&&!strncmp(line,"AHA-OK ",7)){
    char expected[65];proof("server",expected);
    if(strlen(line+7)==64&&!strcmp(expected,line+7)){authenticated=true;heartbeat=millis();netState=3;}else{drop();netState=4;return;}
   }else if(authenticated&&!strcmp(line,"AHA-MIC"))heartbeat=millis();
  }else if(c!='\r'){if(used<sizeof(line)-1)line[used++]=c;else{drop();return;}}
 }
 if((!authenticated&&millis()-connectedAt>2500)||(authenticated&&millis()-heartbeat>2500)){dropReason=3;drop();netState=2;}
}
bool networkReady(){return authenticated&&client.connected()&&WiFi.status()==WL_CONNECTED&&millis()-heartbeat<2500;}
bool sendNetwork(const uint8_t* p,size_t n){return networkReady()&&sendBounded(p,n);}
#endif
