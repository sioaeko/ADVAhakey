#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
namespace aha {
constexpr uint32_t Slot = 28672, MaxSlots = 290;
struct Key { uint8_t type=0x73, length=1, data[98]={0x6d}; char label[21]="Voice"; };
struct Picture { uint16_t start=0, count=0, interval=100; };
struct Config {
 uint32_t magic=0x41484131;
 char name[22]="AhaKey ADV";
 uint8_t mode=0, brightness=70;
 uint16_t appearance=961;
 Key keys[4][4]; Picture pictures[4]; uint8_t effects[4][9] = {};
};
inline uint16_t le16(const uint8_t* p) { return p[0] | uint16_t(p[1])<<8; }
inline uint32_t le32(const uint8_t* p) { return le16(p) | uint32_t(le16(p+2))<<16; }
inline bool frame(const uint8_t* p,size_t n) {return n>=5 && n<=106 && p[0]==0xaa && p[1]==0xbb && p[n-2]==0xcc && p[n-1]==0xdd;}
inline bool valid(uint8_t cmd,const uint8_t* p,size_t n) {
 switch(cmd) {
 case 0: case 4: return n==0;
 case 1: if(n<1||n>21)return false; for(size_t i=0;i<n;i++)if(!p[i])return false; return true;
 case 2:return n==1||n==2;
 case 0x73:
  if(n<3||p[1]>3||p[2]>3)return false;
  if(p[0]==0x75)return n<=23;
  if(p[0]==0x73)return n<=101;
  if(p[0]!=0x74||n>101||(n-3)%2)return false;
  for(size_t i=3;i<n;i+=2)if(p[i]>4)return false;
  return true;
 case 0x80:return n==7 && p[0]==0 && le16(p+1)>0 && le16(p+1)<=4096 && le32(p+3)%4096==0 && le32(p+3)<Slot*MaxSlots && le16(p+1)<=Slot*MaxSlots-le32(p+3);
 case 0x82:return n==7&&p[0]<4&&le16(p+1)>=10&&le16(p+3)<=70&&le16(p+1)+le16(p+3)<=MaxSlots&&le16(p+5)>=16;
 case 0x83:case 0x92:return n==1&&p[0]<4;
 case 0x84:return n==10&&p[0]<4;
 case 0x85:return n==1&&p[0]>=1&&p[0]<=100;
 case 0x90:return n==1&&p[0]<=8;
 case 0x91:return n==1&&p[0]<=16;
 default:return false;
 }
}
inline bool validConfig(const Config& c) {
 if(c.magic!=0x41484131||c.mode>3||c.brightness<1||c.brightness>100||!memchr(c.name,0,22))return false;
 for(int m=0;m<4;m++) {
  auto p=c.pictures[m]; if(p.count>70||p.start+p.count>MaxSlots||p.interval<16)return false;
  for(auto& k:c.keys[m]) {
   if(!memchr(k.label,0,21)||k.length>98||(k.type!=0x73&&k.type!=0x74))return false;
   if(k.type==0x74) {if(k.length%2)return false;for(int i=0;i<k.length;i+=2)if(k.data[i]>4)return false;}
  }
 }
 return true;
}
}
