#include "Dashboard.h"
#include "VoiceHealth.h"
#include <assert.h>
#include <string.h>
int main(){
 aha::Dashboard out;const uint8_t valid[]={2,75,255,1,2,3,'A','D','V'};
 assert(aha::decodeDashboard(valid,sizeof(valid),out));assert(!strcmp(out.title,"ADV"));
 for(size_t n=0;n<sizeof(valid);n++)assert(!aha::decodeDashboard(valid,n,out));
 uint8_t bad[sizeof(valid)];memcpy(bad,valid,sizeof(valid));bad[1]=101;
 assert(!aha::decodeDashboard(bad,sizeof(bad),out));assert(out.fiveHour==75);
 memcpy(bad,valid,sizeof(valid));bad[5]=255;assert(!aha::decodeDashboard(bad,sizeof(bad),out));
 memcpy(bad,valid,sizeof(valid));bad[6]='\n';assert(!aha::decodeDashboard(bad,sizeof(bad),out));
 memcpy(bad,valid,sizeof(valid));bad[3]=3;assert(!aha::decodeDashboard(bad,sizeof(bad),out));
 int16_t silent[640]={};aha::VoiceHealth health;
 for(int i=0;i<9;i++)assert(health.observe(silent,640));
 assert(!health.observe(silent,640));
 silent[20]=1;assert(health.observe(silent,640)); // quiet ADC noise is healthy
 silent[20]=0;for(int i=0;i<9;i++)assert(health.observe(silent,640));
 assert(!health.observe(silent,640));
}
