#include "Dashboard.h"
#include "Voice.h"
#include <M5Cardputer.h>
#include <freertos/FreeRTOS.h>
static portMUX_TYPE dashboardMux=portMUX_INITIALIZER_UNLOCKED;
static aha::Dashboard dashboard;
static uint32_t receivedAt=0;
static bool received=false;
void receiveDashboard(const uint8_t* data,size_t length){
 aha::Dashboard next;if(!aha::decodeDashboard(data,length,next))return;
 portENTER_CRITICAL(&dashboardMux);dashboard=next;receivedAt=millis();received=true;portEXIT_CRITICAL(&dashboardMux);
}
static bool snapshot(aha::Dashboard& out){
 portENTER_CRITICAL(&dashboardMux);out=dashboard;
 bool valid=received&&uint32_t(millis()-receivedAt)<10000&&out.title[0];
 portEXIT_CRITICAL(&dashboardMux);return valid;
}
bool dashboardVisible(){aha::Dashboard value;return snapshot(value);}
bool drawDashboard(){
 aha::Dashboard value;if(!snapshot(value))return false;
 auto& d=M5Cardputer.Display;
 constexpr uint16_t bg=0x1083,muted=0xa554,accent=0x5ef9;
 const char* states[]={"UNKNOWN","IDLE","WORKING","NEEDS INPUT","COMPLETE","STOPPED"};
 const uint16_t colors[]={muted,muted,accent,0xfdad,0x87b1,0xfbad};
 d.fillScreen(bg);d.setTextSize(1);d.setTextColor(accent,bg);d.setCursor(10,8);d.print("AHAKEY / CODEX");
 d.setTextColor(muted,bg);d.setCursor(199,8);d.printf("%u/%u",value.index,value.count);
 d.drawFastHLine(10,23,220,0x2945);
 d.setTextColor(TFT_WHITE,bg);d.setCursor(10,34);d.print(value.title);
 d.setTextSize(2);d.setTextColor(colors[value.state],bg);d.setCursor(10,53);d.print(states[value.state]);
 d.setTextSize(1);d.setTextColor(muted,bg);d.setCursor(10,83);d.print("REMAINING");
 d.setCursor(10,98);if(value.fiveHour==255)d.print("5h --");else d.printf("5h %u%%",value.fiveHour);
 d.setCursor(104,98);if(value.weekly==255)d.print("7d --");else d.printf("7d %u%%",value.weekly);
 d.drawFastHLine(10,114,220,0x2945);d.setCursor(10,123);
 if(micActive){d.setTextColor(0xfbad,bg);d.print("REC  /  G0 to finish");}
 else if(micError){d.setTextColor(0xfdad,bg);d.printf("MIC ERR %u / tap G0 to retry",unsigned(micError.load()));}
 else d.print("G0: Record   Keyboard ready");
 return true;
}
