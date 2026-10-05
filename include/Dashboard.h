#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>
namespace aha {
struct Dashboard {
 uint8_t state=0,fiveHour=255,weekly=255,index=0,count=0;
 char title[29]={};
};
inline bool decodeDashboard(const uint8_t* data,size_t length,Dashboard& out){
 if(length<6||length>34||data[0]>5||data[4]>8||data[3]>data[4]||
    (data[4]&&data[3]==0)||data[5]>28||length!=size_t(6+data[5]))return false;
 if((data[1]>100&&data[1]!=255)||(data[2]>100&&data[2]!=255))return false;
 for(size_t i=6;i<length;i++)if(data[i]<32||data[i]>126)return false;
 Dashboard next;next.state=data[0];next.fiveHour=data[1];next.weekly=data[2];
 next.index=data[3];next.count=data[4];memcpy(next.title,data+6,data[5]);out=next;
 return true;
}
}
void receiveDashboard(const uint8_t* data,size_t length);
bool dashboardVisible();
bool drawDashboard();
