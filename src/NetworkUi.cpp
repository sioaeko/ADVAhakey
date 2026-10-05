#ifdef AHA_VOICE_BLE_ONLY
#include <stdint.h>
bool networkUiVisible(){return false;}
bool networkUi(uint64_t){return false;}
#else
#include <M5Cardputer.h>
#include "NetVoice.h"
#include "InputRouter.h"
#include "Voice.h"
static bool showing=false,waiting=false,swallow=false;
static uint64_t previous=0;static int field=0;static NetConfig editing;
static const char* error="";
bool networkUiVisible(){return showing;}
static void render(){
 auto& d=M5Cardputer.Display;d.fillScreen(0x1082);d.setTextSize(1);d.setTextColor(0xffff,0x1082);d.setCursor(6,5);d.print("WIRELESS VOICE  Fn+Esc:cancel");
 const char* names[]={"WiFi name","Password","PC IPv4","Pair code"};
 const char* values[]={editing.ssid,editing.password,editing.host,editing.token};
 for(int i=0;i<4;i++){d.setCursor(6,25+i*20);d.printf("%c %s: ",i==field?'>':' ',names[i]);String value=values[i];if(i==1){value="";for(size_t j=0;j<strlen(values[i]);j++)value+='*';}if(value.length()>17)value=value.substring(value.length()-17);d.print(value);}
 d.setCursor(6,111);d.print(error[0]?error:"Enter:next/save Tab:previous");d.setCursor(6,124);d.printf("WiFi/PC state: %u",unsigned(netState));
}
bool networkUi(uint64_t raw){
 uint64_t pressed=raw&~previous;bool open=(raw&aha::Fn)&&(pressed&aha::keyBit(2,1));previous=raw;
 if(!showing){if(swallow){if(!raw)swallow=false;return true;}if(!open)return false;showing=true;waiting=true;field=0;editing=getNetworkConfig();error="";micRequested=false;render();return true;}
 if(waiting){if(!raw)waiting=false;return true;}
 if((raw&aha::Fn)&&(pressed&aha::keyBit(0,0))){showing=false;swallow=true;return true;}
 if(pressed&aha::Tab){field=(field+3)%4;error="";}
 else if(pressed&aha::keyBit(13,2)){
  if(field<3)field++;
  else if(saveNetworkConfig(editing)){showing=false;swallow=true;return true;}else error="Check IP/code or storage";
 }else{
  char* values[]={editing.ssid,editing.password,editing.host,editing.token};size_t limits[]={32,64,15,16};char* dest=values[field];size_t n=strlen(dest);
  if(pressed&aha::keyBit(13,0)){if(n)dest[--n]=0;}
  else for(auto pos:M5Cardputer.Keyboard.keyList()){
   if(!(pressed&aha::keyBit(pos.x,pos.y)))continue;
   auto value=M5Cardputer.Keyboard.getKeyValue(pos);unsigned char c=(raw&aha::keyBit(1,2))?value.value_second:value.value_first;
   if(c>=32&&c<127&&!(pos.x==0&&pos.y==1)&&!(pos.x==13&&pos.y==2)&&n<limits[field]){if(field==3&&c>='A'&&c<='F')c+=32;dest[n++]=c;dest[n]=0;}
  }
 }
 static uint32_t last=0;if(pressed||millis()-last>500){render();last=millis();}return true;
}
#endif
